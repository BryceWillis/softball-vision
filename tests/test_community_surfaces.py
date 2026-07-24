"""Guard the GitHub community surfaces added by M9 slices 72a and 72b.

The repository is public, and every inbound GitHub surface — issues, PRs —
is a channel through which a real player name could be published. These files
are the compose-time guard on those channels: warning first, required no-names
checkbox, a private path for reporting a leak. This module pins them the way
``test_name_safety.py`` pins the in-repo rule, so a well-meaning rewrite into
stock OSS boilerplate goes red instead of quietly dropping the warning.

Assertions are raw-text on purpose: PyYAML is not a dependency and does not
become one for this. YAML validity is proven where it is cheap and real — by
the forms rendering in GitHub's issue chooser, checked at acceptance (a
malformed form silently vanishes from the chooser).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ISSUE_TEMPLATE_DIR = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"

#: The canonical warning sentence, pinned per the 70c copy-pinning precedent.
#: Changing user-facing safety copy must be a deliberate act with a test to
#: update, not a silent edit.
WARNING_SENTENCE = (
    "Do not paste rosters, run output, review reports, or screenshots that "
    "show real player names — this is a public repository."
)

#: The no-names attestation label shared by all three issue forms; GitHub
#: blocks submission while its checkbox is unchecked.
NO_NAMES_CHECKBOX_LABEL = (
    "This report contains no real player names — no rosters, no run output, "
    "no screenshots with names."
)

ISSUE_FORMS = ("bug-report.yml", "feature-request.yml", "feedback.yml")

#: The posture sentence (72b). The project is developed under a private
#: spec-and-review cycle with no PR step, and ``CONTRIBUTING.md`` must keep
#: saying so — a rewrite into stock OSS boilerplate would invite a
#: fork-and-open-a-PR process that does not exist.
CLOSED_POSTURE_SENTENCE = (
    "External pull requests are not currently part of this project's workflow "
    "and may be declined."
)

#: The name-safety bar a PR must clear, pinned for the same reason the issue
#: forms' warning is: it is the one thing in this file that is not negotiable.
CONTRIBUTING_NO_NAMES_SENTENCE = "No real player names anywhere in the diff."

COMMUNITY_FILES = (
    ISSUE_TEMPLATE_DIR / "bug-report.yml",
    ISSUE_TEMPLATE_DIR / "feature-request.yml",
    ISSUE_TEMPLATE_DIR / "feedback.yml",
    ISSUE_TEMPLATE_DIR / "config.yml",
    REPO_ROOT / ".github" / "pull_request_template.md",
    REPO_ROOT / "SECURITY.md",
    REPO_ROOT / "CONTRIBUTING.md",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flatten(text: str) -> str:
    """Collapse hard wraps and emphasis so a pinned sentence does not depend on
    where a line happens to break or whether it is bolded."""

    return " ".join(text.replace("**", "").split())


def test_community_files_exist_and_are_nonempty():
    missing = [
        str(path.relative_to(REPO_ROOT))
        for path in COMMUNITY_FILES
        if not path.is_file() or not _read(path).strip()
    ]
    assert not missing, f"Missing or empty community surface file(s): {missing}"


def test_issue_forms_carry_the_warning_and_a_required_no_names_checkbox():
    for form in ISSUE_FORMS:
        text = _read(ISSUE_TEMPLATE_DIR / form)
        assert WARNING_SENTENCE in text, f"{form}: canonical warning sentence missing"
        label_at = text.find(NO_NAMES_CHECKBOX_LABEL)
        assert label_at != -1, f"{form}: no-names checkbox label missing"
        # The requirement must sit on the checkbox itself — ``required: true``
        # adjacent to the label, not somewhere else in the form.
        after_label = text[label_at + len(NO_NAMES_CHECKBOX_LABEL) :][:80]
        assert "required: true" in after_label, (
            f"{form}: the no-names checkbox is not marked required — GitHub "
            "would accept the issue without the attestation"
        )


def test_chooser_config_disables_blank_issues_and_offers_both_contact_links():
    text = _read(ISSUE_TEMPLATE_DIR / "config.yml")
    # The chooser is the guard: with blank issues enabled, the warning can be
    # bypassed from the UI.
    assert "blank_issues_enabled: false" in text
    assert "Send feedback from inside the app (recommended)" in text
    assert "strips player names for you" in text
    assert "Report a leaked player name — privately" in text
    assert "Never report a real name in a public issue" in text
    assert "/security/advisories/new" in text


def test_security_policy_leads_with_the_name_leak_channel():
    text = _read(REPO_ROOT / "SECURITY.md")
    flat = _flatten(text)
    assert "no real player name may ever appear in this repository" in flat
    assert "do not open a public issue" in flat
    assert "Report a vulnerability" in text
    # A public report of a leak is itself a leak; the policy must say so.
    assert "re-publishes the leak" in text
    # The accepted local-first posture, stated so it is not re-reported.
    assert "loopback-bound" in text


def test_pull_request_template_carries_the_no_names_checkbox():
    text = _read(REPO_ROOT / ".github" / "pull_request_template.md")
    assert "- [ ] This diff contains no real player names" in text
    assert "not currently part of this project's workflow" in text
    # The template is advisory; the real gate is CI, and it must say so.
    assert "name-safety test" in text


def test_contributing_states_the_closed_posture_and_the_no_names_bar():
    """72b's pinned sentences. A future rewrite into standard OSS boilerplate
    goes red here rather than quietly inviting a process that does not exist,
    or quietly dropping the one bar an outside diff has to clear."""

    flat = _flatten(_read(REPO_ROOT / "CONTRIBUTING.md"))
    assert CLOSED_POSTURE_SENTENCE in flat, (
        "CONTRIBUTING.md no longer states that external pull requests are not "
        "part of the workflow — the file would be describing a process this "
        "project does not run"
    )
    assert CONTRIBUTING_NO_NAMES_SENTENCE in flat, (
        "CONTRIBUTING.md no longer states the no-real-names bar for a diff"
    )


def test_contributing_points_at_the_sanitized_feedback_path_first():
    """The in-app path is the one that strips names; a contributor sent to the
    issue forms first would be composing by hand with names in front of them."""

    flat = _flatten(_read(REPO_ROOT / "CONTRIBUTING.md"))
    send_feedback_at = flat.find("Send Feedback button")
    issue_at = flat.find("file an issue")
    assert send_feedback_at != -1, "CONTRIBUTING.md does not name the in-app path"
    assert issue_at != -1, "CONTRIBUTING.md does not name the issue-form path"
    assert send_feedback_at < issue_at, (
        "the in-app Send Feedback path must be offered before the issue forms"
    )


def test_pull_request_template_pointer_resolves():
    """The PR template tells a filer to see CONTRIBUTING.md; 72a shipped that
    pointer one slice ahead of the file by the plan's own sanction, and 72b is
    where it stops dangling."""

    assert "CONTRIBUTING.md" in _read(REPO_ROOT / ".github" / "pull_request_template.md")
    assert (REPO_ROOT / "CONTRIBUTING.md").is_file()


def test_feedback_form_matches_the_webapp_handoff_target():
    """The D5 pairing: the app prefills the form field by id, so the webapp
    constants and the form file must agree or the handoff lands unprefilled."""

    from sidelinehd_extractor.webapp.app import (
        FEEDBACK_TEMPLATE_FILENAME,
        FEEDBACK_TEMPLATE_LOG_FIELD,
    )

    form_path = ISSUE_TEMPLATE_DIR / FEEDBACK_TEMPLATE_FILENAME
    assert form_path.is_file(), (
        f"webapp targets {FEEDBACK_TEMPLATE_FILENAME!r} but no such issue form exists"
    )
    text = _read(form_path)
    assert f"id: {FEEDBACK_TEMPLATE_LOG_FIELD}" in text, (
        f"feedback form has no field with id {FEEDBACK_TEMPLATE_LOG_FIELD!r}; "
        "the handoff prefill would be silently dropped"
    )
