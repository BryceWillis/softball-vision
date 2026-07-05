"""Detect exportable events from parsed overlay states."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from sidelinehd_extractor.constants import (
    BATTER_SOURCE_BATTER_CARD,
    BATTER_SOURCE_LINEUP_NUMBER,
    BATTER_SOURCE_LINEUP_STRIP,
    LINEUP_SOURCE_HIGHLIGHT,
    LINEUP_STRIP_CONFIDENCE_KEY,
)
from sidelinehd_extractor.models import Event, EventType, HalfInning, OverlayState, Roster
from sidelinehd_extractor.processing import write_jsonl

CONFIRMED_ORDER_SOURCES = frozenset({"name", "number", "lineup_number"})
MIN_BATTING_ORDER_SEED = 3


@dataclass(frozen=True)
class EventDetectionResult:
    """Summary of an event detection run."""

    input_path: Path
    output_path: Path
    event_count: int


@dataclass(frozen=True)
class BattingHalfInference:
    """Audit details for automatic roster batting-half inference."""

    inferred_half: Optional[HalfInning]
    top_at_bats: int
    top_roster_matches: int
    bottom_at_bats: int
    bottom_roster_matches: int
    warning: Optional[str] = None

    @property
    def message(self) -> str:
        top = f"{self.top_roster_matches}/{self.top_at_bats}"
        bottom = f"{self.bottom_roster_matches}/{self.bottom_at_bats}"
        if self.inferred_half is None:
            reason = self.warning or "keeping both halves"
            return (
                "Inferred batting half: both "
                f"({top} roster-name matches in top, {bottom} in bottom; {reason})"
            )
        return (
            f"Inferred batting half: {self.inferred_half.value} "
            f"({top} roster-name matches in top, {bottom} in bottom)"
        )


def load_states(path: Path) -> List[OverlayState]:
    """Load overlay states from a JSONL file."""

    states = []
    with path.expanduser().open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            states.append(
                OverlayState(
                    timestamp_seconds=float(row["timestamp_seconds"]),
                    inning=row.get("inning"),
                    half=HalfInning(row["half"]) if row.get("half") else None,
                    balls=row.get("balls"),
                    strikes=row.get("strikes"),
                    outs=row.get("outs"),
                    home_score=row.get("home_score"),
                    away_score=row.get("away_score"),
                    batter_number=row.get("batter_number"),
                    batting_team=row.get("batting_team"),
                    confidence=row.get("confidence"),
                    source_sample_ids=row.get("source_sample_ids") or [],
                    metadata=row.get("metadata") or {},
                )
            )
    return states


def load_events(path: Path) -> List[Event]:
    """Load events from a JSONL file."""

    events = []
    with path.expanduser().open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            events.append(
                Event(
                    event_type=EventType(row["event_type"]),
                    timestamp_seconds=float(row["timestamp_seconds"]),
                    label=str(row["label"]),
                    inning=row.get("inning"),
                    half=HalfInning(row["half"]) if row.get("half") else None,
                    player_number=row.get("player_number"),
                    player_name=row.get("player_name"),
                    metadata=row.get("metadata") or {},
                )
            )
    return events


def detect_events(
    states: Iterable[OverlayState],
    roster: Optional[Roster] = None,
    batting_half: Optional[HalfInning] = None,
    min_at_bat_spacing_seconds: float = 45.0,
    min_at_bat_spacing_roster_confirmed_seconds: float = 20.0,
    batter_confirmation_window: int = 4,
    min_batter_observations: int = 2,
    half_inning_confirmation_window: int = 12,
    min_half_inning_observations: int = 4,
    min_game_final_observations: int = 3,
) -> List[Event]:
    """Detect half-inning and at-bat starts from parsed overlay states."""

    ordered_states = sorted(states, key=lambda item: item.timestamp_seconds)
    if roster is not None:
        ordered_states = _enrich_states_digit_runs(ordered_states, roster)
    events = []
    starts_at_zero = bool(ordered_states) and ordered_states[0].timestamp_seconds <= 0
    last_half_key: Optional[Tuple[int, HalfInning]] = None
    last_batter_number = None
    last_batter_name = None
    last_at_bat_timestamp = None
    name_to_number = {}

    for index, state in enumerate(ordered_states):
        half_key = _half_key(state)
        if (
            half_key is not None
            and half_key != last_half_key
            and _is_valid_half_inning_progression(last_half_key, half_key)
            and _confirmed_half_key(
                ordered_states,
                index,
                half_key,
                half_inning_confirmation_window,
                min_half_inning_observations,
                require_activity_signal=last_half_key is None and starts_at_zero,
            )
        ):
            inning, half = half_key
            chapter_timestamp_seconds = state.timestamp_seconds
            away_score, home_score = _score_snapshot(
                ordered_states,
                index,
                half_inning_confirmation_window,
                half_key=half_key,
            )
            if last_half_key is None and starts_at_zero:
                active_timestamp_seconds = _game_active_timestamp(
                    ordered_states,
                    index,
                    half_key,
                    half_inning_confirmation_window,
                )
                if active_timestamp_seconds is not None:
                    chapter_timestamp_seconds = active_timestamp_seconds
            events.append(
                Event(
                    event_type=EventType.HALF_INNING_START,
                    timestamp_seconds=chapter_timestamp_seconds,
                    label=format_half_inning_label(inning, half),
                    inning=inning,
                    half=half,
                    metadata={
                        "source": "state_change",
                        "away_score": away_score,
                        "home_score": home_score,
                    },
                )
            )
            last_half_key = half_key

        player_name = player_name_for_state(state, roster)
        roster_batter_number = player_number_for_state(state, player_name, roster)
        roster_match_source = roster_match_source_for_state(state, roster)
        effective_batter_number = _effective_batter_number(
            roster_batter_number,
            player_name,
            name_to_number,
        )
        at_bat_spacing_seconds = _at_bat_spacing_for_roster_match(
            roster_match_source,
            min_at_bat_spacing_seconds,
            min_at_bat_spacing_roster_confirmed_seconds,
        )

        if (
            _is_plausible_batter_identity(state, effective_batter_number, player_name)
            and _is_plausible_batter_source(state, player_name, roster)
            and _is_selected_batting_half(state, batting_half)
            and _has_minimum_at_bat_spacing(
                state.timestamp_seconds,
                last_at_bat_timestamp,
                at_bat_spacing_seconds,
            )
            and effective_batter_number != last_batter_number
            and not _same_batter_name(player_name, last_batter_name)
            and _confirmed_batter_identity(
                ordered_states,
                index,
                effective_batter_number,
                player_name,
                roster,
                name_to_number,
                batter_confirmation_window,
                min_batter_observations,
            )
        ):
            events.append(
                Event(
                    event_type=EventType.AT_BAT_START,
                    timestamp_seconds=state.timestamp_seconds,
                    label=format_at_bat_label(effective_batter_number, player_name),
                    inning=state.inning,
                    half=state.half,
                    player_number=effective_batter_number,
                    player_name=player_name,
                    metadata={
                        "balls": state.balls,
                        "strikes": state.strikes,
                        "source": "batter_number_change",
                        "ocr_player_number": state.batter_number,
                        "batter_card_name": state.metadata.get("batter_name"),
                        "roster_match_source": roster_match_source,
                        "batter_number_source": state.metadata.get("batter_number_source"),
                        LINEUP_STRIP_CONFIDENCE_KEY: state.metadata.get(
                            LINEUP_STRIP_CONFIDENCE_KEY
                        ),
                        "batter_number_disagreement": state.metadata.get(
                            "batter_number_disagreement"
                        ),
                    },
                )
            )
            last_batter_number = effective_batter_number
            last_batter_name = player_name
            last_at_bat_timestamp = state.timestamp_seconds
            if player_name and effective_batter_number:
                name_to_number[_normalize_name(player_name)] = effective_batter_number

    final_event = _detect_game_final(ordered_states, min_game_final_observations)
    if final_event is not None:
        events.append(final_event)

    return sorted(events, key=lambda item: item.timestamp_seconds)


def detect_events_file(
    states_path: Path,
    output_path: Optional[Path] = None,
    roster: Optional[Roster] = None,
    batting_half: Optional[HalfInning] = None,
    min_at_bat_spacing_seconds: float = 45.0,
    min_at_bat_spacing_roster_confirmed_seconds: float = 20.0,
    min_game_final_observations: int = 3,
    order_validation: bool = True,
) -> EventDetectionResult:
    """Detect events from a states JSONL file and write events JSONL."""

    source = states_path.expanduser()
    destination = output_path.expanduser() if output_path else source.parent / "events.jsonl"
    events = detect_events(
        load_states(source),
        roster=roster,
        batting_half=batting_half,
        min_at_bat_spacing_seconds=min_at_bat_spacing_seconds,
        min_at_bat_spacing_roster_confirmed_seconds=min_at_bat_spacing_roster_confirmed_seconds,
        min_game_final_observations=min_game_final_observations,
    )
    if roster is not None and order_validation:
        events = validate_batting_order(events, roster=roster)
    write_jsonl(destination, events)
    return EventDetectionResult(input_path=source, output_path=destination, event_count=len(events))


def infer_batting_cycle(events: List[Event]) -> List[str]:
    """Return ordered player numbers from the first qualifying seed half-inning."""

    cycle, _seed_half = _infer_seed_info(events)
    return cycle


def validate_batting_order(
    events: List[Event],
    roster: Optional[Roster] = None,
    tolerance: int = 2,
) -> List[Event]:
    """Flag batting-order anomalies and synthesize reviewable inferred events."""

    cycle, seed_half = _infer_seed_info(events)
    if len(cycle) < MIN_BATTING_ORDER_SEED or seed_half is None:
        return list(events)

    cycle_len = len(cycle)
    number_to_name = _player_name_lookup(events, roster, cycle)
    cycle_pos = 0
    prev_ts: Optional[float] = None
    at_seed_half_start = False
    result: List[Event] = []

    for event in events:
        if event.event_type == EventType.HALF_INNING_START and event.half == seed_half:
            prev_ts = event.timestamp_seconds
            at_seed_half_start = True
            result.append(event)
            continue

        if (
            event.event_type != EventType.AT_BAT_START
            or event.half != seed_half
            or not event.player_number
        ):
            result.append(event)
            continue

        player_number = event.player_number
        if player_number not in cycle:
            if _roster_has_number(roster, player_number):
                result.append(event)
            else:
                result.append(_with_order_flag(event, "possible-substitute"))
            prev_ts = event.timestamp_seconds
            at_seed_half_start = False
            continue

        actual_pos = cycle.index(player_number)
        forward_skip = (actual_pos - cycle_pos) % cycle_len
        if forward_skip <= tolerance:
            if forward_skip > 0 and prev_ts is not None and not at_seed_half_start:
                gap = event.timestamp_seconds - prev_ts
                for index in range(forward_skip):
                    skipped_pos = (cycle_pos + index) % cycle_len
                    skipped_number = cycle[skipped_pos]
                    timestamp_seconds = prev_ts + gap * (index + 1) / (forward_skip + 1)
                    result.append(
                        Event(
                            event_type=EventType.AT_BAT_START,
                            timestamp_seconds=timestamp_seconds,
                            label=format_at_bat_label(
                                skipped_number,
                                number_to_name.get(skipped_number),
                            ),
                            inning=event.inning,
                            half=event.half,
                            player_number=skipped_number,
                            player_name=number_to_name.get(skipped_number),
                            metadata={
                                "source": "batting_order",
                                "roster_match_source": "batting_order",
                                "order_flags": ["inferred-missing"],
                            },
                        )
                    )
            result.append(event)
            cycle_pos = (actual_pos + 1) % cycle_len
        else:
            result.append(_with_order_flag(event, "out-of-order-candidate"))
            cycle_pos = (actual_pos + 1) % cycle_len
        prev_ts = event.timestamp_seconds
        at_seed_half_start = False

    return sorted(result, key=lambda item: item.timestamp_seconds)


def _infer_seed_info(events: List[Event]) -> Tuple[List[str], Optional[HalfInning]]:
    """Return the inferred batting cycle and the half that supplied it."""

    groups: Dict[Tuple[int, HalfInning], List[str]] = defaultdict(list)
    for event in events:
        if (
            event.event_type == EventType.AT_BAT_START
            and event.inning is not None
            and event.half is not None
            and event.player_number
            and event.metadata.get("roster_match_source") in CONFIRMED_ORDER_SOURCES
        ):
            groups[(event.inning, event.half)].append(event.player_number)

    for key in sorted(groups.keys(), key=_half_inning_sort_key):
        players = list(dict.fromkeys(groups[key]))
        if len(players) >= MIN_BATTING_ORDER_SEED:
            return players, key[1]
    return [], None


def _half_inning_sort_key(key: Tuple[int, HalfInning]) -> Tuple[int, int]:
    inning, half = key
    half_index = 0 if half == HalfInning.TOP else 1
    return inning, half_index


def _player_name_lookup(
    events: List[Event],
    roster: Optional[Roster],
    cycle: List[str],
) -> Dict[str, str]:
    number_to_name: Dict[str, str] = {}
    for event in events:
        if event.event_type == EventType.AT_BAT_START and event.player_number and event.player_name:
            number_to_name[event.player_number] = event.player_name
    if roster is not None:
        for number in cycle:
            if number not in number_to_name:
                roster_name = roster.name_for_number(number)
                if roster_name:
                    number_to_name[number] = roster_name
    return number_to_name


def _roster_has_number(roster: Optional[Roster], number: str) -> bool:
    if roster is None:
        return False
    normalized = str(number).strip().lstrip("#")
    return any(player.number.strip().lstrip("#") == normalized for player in roster.players)


def _with_order_flag(event: Event, flag: str) -> Event:
    flags = list(event.metadata.get("order_flags") or [])
    if flag not in flags:
        flags.append(flag)
    return replace(event, metadata={**event.metadata, "order_flags": flags})


def infer_batting_half(
    events: Iterable[Event],
    roster: Optional[Roster],
) -> BattingHalfInference:
    """Infer which half contains the rostered team's named batter cards."""

    counts = {
        HalfInning.TOP: {"total": 0, "matches": 0},
        HalfInning.BOTTOM: {"total": 0, "matches": 0},
    }

    for event in events:
        if event.event_type != EventType.AT_BAT_START or event.half not in counts:
            continue
        counts[event.half]["total"] += 1
        if roster is not None and _event_has_roster_name_match(event):
            counts[event.half]["matches"] += 1

    top_matches = counts[HalfInning.TOP]["matches"]
    bottom_matches = counts[HalfInning.BOTTOM]["matches"]
    if roster is None:
        warning = "no roster provided"
        inferred_half = None
    elif top_matches == 0 and bottom_matches == 0:
        warning = "no roster-name matches found"
        inferred_half = None
    elif top_matches == bottom_matches:
        warning = "ambiguous roster-name match counts"
        inferred_half = None
    else:
        warning = None
        inferred_half = HalfInning.TOP if top_matches > bottom_matches else HalfInning.BOTTOM

    return BattingHalfInference(
        inferred_half=inferred_half,
        top_at_bats=counts[HalfInning.TOP]["total"],
        top_roster_matches=top_matches,
        bottom_at_bats=counts[HalfInning.BOTTOM]["total"],
        bottom_roster_matches=bottom_matches,
        warning=warning,
    )


def filter_at_bats_to_half(events: Iterable[Event], half: Optional[HalfInning]) -> List[Event]:
    """Return all chapter events and only at-bats from ``half`` when provided."""

    if half is None:
        return list(events)
    return [
        event
        for event in events
        if event.event_type != EventType.AT_BAT_START or event.half == half
    ]


def format_half_inning_label(inning: int, half: HalfInning) -> str:
    """Return a YouTube-friendly half-inning label."""

    prefix = "Top" if half == HalfInning.TOP else "Bottom"
    return f"{prefix} {inning}"


def format_at_bat_label(player_number: str, player_name: Optional[str] = None) -> str:
    """Return a YouTube-friendly at-bat label."""

    if player_name:
        return f"{player_name} (#{player_number})"
    return f"#{player_number}"


def player_name_for_state(state: OverlayState, roster: Optional[Roster] = None) -> Optional[str]:
    """Prefer roster names, then OCR batter-card names."""

    batter_name = state.metadata.get("batter_name")
    if roster is not None and batter_name:
        jersey_number = _jersey_number_from_text(str(batter_name))
        if jersey_number:
            roster_name = roster.name_for_number(jersey_number)
            if roster_name:
                return roster_name
        roster_number = roster.number_for_name(str(batter_name))
        if roster_number:
            roster_name = roster.name_for_number(roster_number)
            if roster_name:
                return roster_name
    if roster is not None:
        lineup_number = _preferred_lineup_number_for_state(state, roster)
        if lineup_number:
            roster_name = roster.name_for_number(lineup_number)
            if roster_name:
                return roster_name
    if roster is not None and state.batter_number:
        roster_name = roster.name_for_number(state.batter_number)
        if roster_name:
            return roster_name
    if not batter_name:
        return None
    return str(batter_name)


def player_number_for_state(
    state: OverlayState, player_name: Optional[str], roster: Optional[Roster]
) -> Optional[str]:
    """Prefer roster number by OCR name, then OCR number."""

    if roster is not None:
        lineup_number = _preferred_lineup_number_for_state(state, roster)
        if lineup_number:
            return lineup_number
    if roster is not None and player_name:
        roster_number = roster.number_for_name(player_name)
        if roster_number:
            return roster_number
    return state.batter_number


def roster_match_source_for_state(
    state: OverlayState,
    roster: Optional[Roster],
) -> Optional[str]:
    """Return how this state matched the roster, preferring named card OCR."""

    if roster is None:
        return None
    batter_name = state.metadata.get("batter_name")
    if batter_name and roster.number_for_name(str(batter_name)):
        return "name"
    if _preferred_lineup_number_for_state(state, roster):
        return "lineup_number"
    if state.batter_number and roster.name_for_number(state.batter_number):
        source = state.metadata.get("batter_number_source")
        if source in {BATTER_SOURCE_LINEUP_NUMBER, BATTER_SOURCE_LINEUP_STRIP}:
            return "lineup_number"
        return "number"
    return None


def _half_key(state: OverlayState) -> Optional[Tuple[int, HalfInning]]:
    if state.inning is None or state.half is None:
        return None
    return state.inning, state.half


def _score_snapshot(
    states: List[OverlayState],
    start_index: int,
    window: int,
    half_key: Optional[Tuple[int, HalfInning]] = None,
) -> Tuple[Optional[int], Optional[int]]:
    """Return the first complete away/home score pair in the confirmation window."""

    for state in states[start_index : start_index + window]:
        if half_key is not None and _half_key(state) != half_key:
            continue
        if state.away_score is not None and state.home_score is not None:
            return state.away_score, state.home_score
    return None, None


def _detect_game_final(
    states: List[OverlayState],
    min_observations: int = 3,
) -> Optional[Event]:
    """Return a final marker after a stable run of FINAL scorebug reads."""

    run_start_index = None
    run_length = 0
    for index, state in enumerate(states):
        if _game_status(state) == "final":
            if run_start_index is None:
                run_start_index = index
            run_length += 1
            if run_length >= min_observations:
                run_start = states[run_start_index]
                away_score, home_score = _score_snapshot(states, run_start_index, run_length)
                return Event(
                    event_type=EventType.GAME_FINAL,
                    timestamp_seconds=run_start.timestamp_seconds,
                    label="Final",
                    metadata={
                        "source": "game_status",
                        "away_score": away_score,
                        "home_score": home_score,
                    },
                )
        else:
            run_start_index = None
            run_length = 0
    return None


def _is_valid_half_inning_progression(
    previous: Optional[Tuple[int, HalfInning]],
    current: Tuple[int, HalfInning],
) -> bool:
    if previous is None:
        return True

    previous_inning, previous_half = previous
    current_inning, current_half = current

    if current_inning < previous_inning:
        return False
    if current_inning == previous_inning:
        return previous_half == HalfInning.TOP and current_half == HalfInning.BOTTOM
    if current_inning == previous_inning + 1:
        return current_half == HalfInning.TOP
    return False


def _is_plausible_batter_state(state: OverlayState) -> bool:
    if not state.batter_number:
        return False
    if not state.batter_number.isdigit():
        return False
    if len(state.batter_number) > 2:
        return False
    batter_name = state.metadata.get("batter_name")
    if batter_name is not None and not _looks_like_player_name(str(batter_name)):
        return False
    return True


def _is_plausible_batter_identity(
    state: OverlayState,
    effective_batter_number: Optional[str],
    player_name: Optional[str],
) -> bool:
    if not effective_batter_number:
        return False
    if not effective_batter_number.isdigit():
        return False
    if len(effective_batter_number) > 2:
        return False
    if player_name and _looks_like_player_name(player_name):
        return True
    if state.batter_number:
        return _is_plausible_batter_state(state)
    if not player_name:
        return False
    return _looks_like_player_name(player_name)


def _is_plausible_batter_source(
    state: OverlayState,
    player_name: Optional[str],
    roster: Optional[Roster],
) -> bool:
    """Reject weak unrostered batter sources when a roster is present."""

    source = state.metadata.get("batter_number_source")
    if source == BATTER_SOURCE_LINEUP_STRIP:
        if not _lineup_is_highlight_confirmed(state):
            return False
        if roster is None:
            return True
        return _has_roster_match_for_state(state, roster)
    if source == BATTER_SOURCE_BATTER_CARD and roster is not None:
        if state.batter_number and not _has_roster_match_for_state(state, roster):
            return False
    if roster is None:
        return True
    return True


def _is_selected_batting_half(state: OverlayState, batting_half: Optional[HalfInning]) -> bool:
    if batting_half is None:
        return True
    return state.half == batting_half


def _has_roster_match_for_state(state: OverlayState, roster: Roster) -> bool:
    batter_name = state.metadata.get("batter_name")
    return bool(
        (state.batter_number and roster.name_for_number(state.batter_number))
        or _active_lineup_number_for_state(state, roster)
        or (
            batter_name
            and _jersey_number_from_text(str(batter_name))
            and roster.name_for_number(_jersey_number_from_text(str(batter_name)))
        )
        or (batter_name and roster.number_for_name(str(batter_name)))
    )


def _lineup_is_highlight_confirmed(state: OverlayState) -> bool:
    """Return true when lineup-strip OCR came from the highlighted chip."""

    return _metadata_is_highlight_confirmed(state.metadata)


def _metadata_is_highlight_confirmed(metadata: dict) -> bool:
    """Return true when metadata says lineup OCR came from the highlighted chip."""

    return metadata.get(LINEUP_STRIP_CONFIDENCE_KEY) == LINEUP_SOURCE_HIGHLIGHT


def _preferred_lineup_number_for_state(
    state: OverlayState,
    roster: Roster,
) -> Optional[str]:
    """Return active lineup number when it should override a weak card number."""

    source = state.metadata.get("batter_number_source")
    lineup_number = _active_lineup_number_for_state(state, roster)
    if not lineup_number:
        return None
    if source == BATTER_SOURCE_LINEUP_STRIP:
        return lineup_number
    if source != BATTER_SOURCE_BATTER_CARD:
        return None
    batter_name = state.metadata.get("batter_name")
    if batter_name and roster.number_for_name(str(batter_name)):
        return None
    if batter_name and _jersey_number_from_text(str(batter_name)):
        return None
    return lineup_number


def _active_lineup_number_for_state(
    state: OverlayState,
    roster: Roster,
) -> Optional[str]:
    for key in ("lineup_strip_number", "lineup_batter_number"):
        value = state.metadata.get(key)
        if value and roster.name_for_number(str(value)):
            return str(value)
    disagreement = state.metadata.get("batter_number_disagreement")
    if disagreement:
        match = re.search(r"(?:^|\s)lineup=([0-9]{1,2})(?:\s|$)", str(disagreement))
        if match and roster.name_for_number(match.group(1)):
            return match.group(1)
    return None


def _has_minimum_at_bat_spacing(
    timestamp_seconds: float,
    previous_timestamp_seconds: Optional[float],
    minimum_seconds: float,
) -> bool:
    if previous_timestamp_seconds is None:
        return True
    return timestamp_seconds - previous_timestamp_seconds >= minimum_seconds


def _at_bat_spacing_for_roster_match(
    roster_match_source: Optional[str],
    min_spacing_seconds: float,
    min_spacing_roster_confirmed_seconds: float,
) -> float:
    """Return the spacing floor for a candidate at-bat based on signal strength."""

    if roster_match_source in {"name", "number", "lineup_number"}:
        return min_spacing_roster_confirmed_seconds
    return min_spacing_seconds


def _enrich_states_digit_runs(
    states: List[OverlayState],
    roster: Roster,
) -> List[OverlayState]:
    """Resolve unambiguous fused lineup-strip digit runs before event detection."""

    enriched = []
    for state in states:
        if (
            state.metadata.get("batter_number_source") == BATTER_SOURCE_LINEUP_STRIP
            and _lineup_is_highlight_confirmed(state)
            and state.batter_number
            and len(state.batter_number) > 2
        ):
            resolved = _resolve_lineup_digit_run(state.batter_number, roster)
            if resolved:
                metadata = dict(state.metadata)
                metadata["batter_number_digit_run_original"] = state.batter_number
                state = replace(state, batter_number=resolved, metadata=metadata)
        enriched.append(state)
    return enriched


def _resolve_lineup_digit_run(text: str, roster: Roster) -> Optional[str]:
    """Find a single rostered number within a fused OCR digit run."""

    digits = re.sub(r"\D", "", text)
    if len(digits) <= 2:
        return None
    candidates = set()
    for length in (1, 2):
        for start in range(len(digits) - length + 1):
            candidate = digits[start : start + length]
            if candidate.lstrip("0") and roster.name_for_number(candidate):
                candidates.add(candidate)
    return next(iter(candidates)) if len(candidates) == 1 else None


def _jersey_number_from_text(value: str) -> Optional[str]:
    match = re.search(r"#\s*(\d{1,2})\b", value)
    if not match:
        return None
    return match.group(1)


def _looks_like_player_name(value: str) -> bool:
    text = value.strip()
    if not text:
        return True
    letters = sum(1 for character in text if character.isalpha())
    return letters >= 3


def _same_batter_name(current_name: Optional[str], previous_name: Optional[str]) -> bool:
    if not current_name or not previous_name:
        return False
    current = _normalize_name(current_name)
    previous = _normalize_name(previous_name)
    if not current or not previous:
        return False
    if current == previous:
        return True
    return SequenceMatcher(None, current, previous).ratio() >= 0.82


def _normalize_name(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalpha())


def _effective_batter_number(
    batter_number: Optional[str],
    player_name: Optional[str],
    name_to_number: dict,
) -> Optional[str]:
    if not batter_number:
        return None
    if not player_name:
        return batter_number
    normalized_name = _normalize_name(player_name)
    if not normalized_name:
        return batter_number
    return name_to_number.get(normalized_name, batter_number)


def _confirmed_batter_number(
    states: List[OverlayState],
    start_index: int,
    batter_number: str,
    window: int,
    minimum: int,
) -> bool:
    observations = 0
    for state in states[start_index : start_index + window]:
        if state.batter_number == batter_number and _is_plausible_batter_state(state):
            observations += 1
    return observations >= minimum


def _confirmed_batter_identity(
    states: List[OverlayState],
    start_index: int,
    effective_batter_number: str,
    player_name: Optional[str],
    roster: Optional[Roster],
    name_to_number: dict,
    window: int,
    minimum: int,
) -> bool:
    observations = 0
    for state in states[start_index : start_index + window]:
        observed_name = player_name_for_state(state, roster)
        identity_state = state
        observed_number = _effective_batter_number(
            player_number_for_state(state, observed_name, roster),
            observed_name,
            name_to_number,
        )
        if (
            observed_number != effective_batter_number
            and roster is not None
            and state.batter_number
            and len(state.batter_number) > 2
        ):
            resolved_number = _resolve_lineup_digit_run(state.batter_number, roster)
            if resolved_number:
                observed_number = _effective_batter_number(
                    resolved_number,
                    observed_name,
                    name_to_number,
                )
                identity_state = replace(state, batter_number=resolved_number)
        if (
            observed_number == effective_batter_number
            and _is_plausible_batter_identity(identity_state, observed_number, observed_name)
            and (
                not player_name
                or not observed_name
                or _same_batter_name(observed_name, player_name)
            )
        ):
            observations += 1
    return observations >= minimum


def _confirmed_half_key(
    states: List[OverlayState],
    start_index: int,
    half_key: Tuple[int, HalfInning],
    window: int,
    minimum: int,
    require_activity_signal: bool = False,
) -> bool:
    observations = 0
    window_states = states[start_index : start_index + window]
    for state in window_states:
        if _half_key(state) == half_key:
            observations += 1
    if len(window_states) < minimum:
        confirmed = len(window_states) >= 2 and observations == len(window_states)
    else:
        confirmed = observations >= minimum
    if not confirmed:
        return False
    if require_activity_signal:
        return _window_has_game_active_signal(window_states, half_key)
    return True


def _window_has_game_active_signal(
    window_states: List[OverlayState],
    half_key: Tuple[int, HalfInning],
) -> bool:
    """Return true when a stable half-inning window shows real game activity."""

    return _game_active_timestamp(window_states, 0, half_key, len(window_states)) is not None


def _game_active_timestamp(
    states: List[OverlayState],
    start_index: int,
    half_key: Tuple[int, HalfInning],
    window: int,
) -> Optional[float]:
    """Return the first timestamp that shows a live game state."""

    previous_batter_number: Optional[str] = None
    for state in states[start_index : start_index + window]:
        if _half_key(state) != half_key:
            continue
        if _is_pregame_state(state):
            # Pregame status is a reliable negative signal, not a game-start
            # trigger. A missed pregame OCR read followed by 0-0 must not
            # bypass the existing positive activity gate.
            previous_batter_number = None
            continue
        if not _is_plausible_batter_state(state):
            continue
        if (
            state.balls is not None
            and state.strikes is not None
            and (state.balls > 0 or state.strikes > 0)
        ):
            return state.timestamp_seconds
        if (
            previous_batter_number is not None
            and state.batter_number
            and state.batter_number != previous_batter_number
            and _has_batter_change_activity_signal(state)
        ):
            return state.timestamp_seconds
        if state.batter_number and _has_batter_change_activity_signal(state):
            previous_batter_number = state.batter_number
    return None


def _game_status(state: OverlayState) -> Optional[str]:
    value = state.metadata.get("game_status")
    return str(value) if value else None


def _is_pregame_state(state: OverlayState) -> bool:
    return _game_status(state) == "pregame"


def _has_batter_change_activity_signal(state: OverlayState) -> bool:
    """Return true when a batter number is reliable enough for game-start gating."""

    source = state.metadata.get("batter_number_source")
    if source == BATTER_SOURCE_LINEUP_STRIP:
        return _lineup_is_highlight_confirmed(state)
    if source == BATTER_SOURCE_LINEUP_NUMBER:
        return True
    if source == BATTER_SOURCE_BATTER_CARD:
        batter_name = state.metadata.get("batter_name")
        return bool(batter_name and _looks_like_player_name(str(batter_name)))
    return False


def _event_has_roster_name_match(event: Event) -> bool:
    return event.metadata.get("roster_match_source") == "name"
