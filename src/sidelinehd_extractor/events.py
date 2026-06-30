"""Detect exportable events from parsed overlay states."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from sidelinehd_extractor.models import Event, EventType, HalfInning, OverlayState, Roster
from sidelinehd_extractor.processing import write_jsonl


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
            events.append(
                Event(
                    event_type=EventType.HALF_INNING_START,
                    timestamp_seconds=state.timestamp_seconds,
                    label=format_half_inning_label(inning, half),
                    inning=inning,
                    half=half,
                    metadata={"source": "state_change"},
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
                        "lineup_strip_confidence": state.metadata.get(
                            "lineup_strip_confidence"
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

    return events


def detect_events_file(
    states_path: Path,
    output_path: Optional[Path] = None,
    roster: Optional[Roster] = None,
    batting_half: Optional[HalfInning] = None,
    min_at_bat_spacing_seconds: float = 45.0,
    min_at_bat_spacing_roster_confirmed_seconds: float = 20.0,
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
    )
    write_jsonl(destination, events)
    return EventDetectionResult(input_path=source, output_path=destination, event_count=len(events))


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
        return "lineup_number" if source == "lineup_strip" else "number"
    return None


def _half_key(state: OverlayState) -> Optional[Tuple[int, HalfInning]]:
    if state.inning is None or state.half is None:
        return None
    return state.inning, state.half


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
    if source == "lineup_strip":
        if not _lineup_is_highlight_confirmed(state):
            return False
        if roster is None:
            return True
        return _has_roster_match_for_state(state, roster)
    if source == "batter_card" and roster is not None:
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

    return state.metadata.get("lineup_strip_confidence") == "lineup_highlight"


def _preferred_lineup_number_for_state(
    state: OverlayState,
    roster: Roster,
) -> Optional[str]:
    """Return active lineup number when it should override a weak card number."""

    source = state.metadata.get("batter_number_source")
    lineup_number = _highlight_lineup_number_for_state(state, roster)
    if not lineup_number:
        return None
    if source == "lineup_strip":
        return lineup_number
    if source != "batter_card":
        return None
    batter_name = state.metadata.get("batter_name")
    if batter_name and roster.number_for_name(str(batter_name)):
        return None
    if batter_name and _jersey_number_from_text(str(batter_name)):
        return None
    return lineup_number


def _highlight_lineup_number_for_state(
    state: OverlayState,
    roster: Roster,
) -> Optional[str]:
    """Return a rostered lineup number only from highlight-confirmed OCR."""

    if not _lineup_is_highlight_confirmed(state):
        return None
    return _active_lineup_number_for_state(state, roster)


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
            state.metadata.get("batter_number_source") == "lineup_strip"
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
        observed_number = _effective_batter_number(
            player_number_for_state(state, observed_name, roster),
            observed_name,
            name_to_number,
        )
        if (
            observed_number == effective_batter_number
            and _is_plausible_batter_identity(state, observed_number, observed_name)
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
    if require_activity_signal and not _has_half_inning_activity_signal(states[start_index]):
        return False

    observations = 0
    window_states = states[start_index : start_index + window]
    for state in window_states:
        if _half_key(state) == half_key:
            observations += 1
    if len(window_states) < minimum:
        return len(window_states) >= 2 and observations == len(window_states)
    return observations >= minimum


def _has_half_inning_activity_signal(state: OverlayState) -> bool:
    """Return true once the scorebug looks game-active, not merely present.

    SidelineHD pregame overlays can OCR as a stable ``Top 1`` before the game
    has actually started. A plausible batter card is the strongest local signal
    that the inning state is no longer just pregame scorebug noise.
    """

    return _is_plausible_batter_state(state)


def _event_has_roster_name_match(event: Event) -> bool:
    return event.metadata.get("roster_match_source") == "name"
