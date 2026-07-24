# Contributing

Thanks for looking. Please read this first — it is short, and it is honest
rather than boilerplate.

## What this project is

A personal-use tool that turns SidelineHD softball streams into YouTube
chapters and per-at-bat jump links. It is shipped and in real use on real
games, not a work in progress looking for hands.

It is developed under a private spec-and-review process: every change is
specified, built, and reviewed by a second party before it is committed. That
worklist and the design behind it live in a documentation vault outside this
repository, so the reasoning for a given change is usually not visible here.

## Pull requests

**External pull requests are not currently part of this project's workflow and
may be declined.** That is a description of how the project runs today, not a
judgment on your patch, and it may change.

If you open one anyway, the one thing that is not negotiable:

**No real player names anywhere in the diff.** This is youth-sports data in a
public repository, and a leaked name is the one defect here that cannot be
fixed forward — git history is public. Every name in the code, tests, docs,
and examples is an invented placeholder, and CI's name-safety test fails a
real name in a tracked file regardless of what any checkbox says. If you are
adding a fixture, sanitize it.

Found a real name already in the repo or its history? **Do not open a public
issue** — that re-publishes the leak. See [SECURITY.md](SECURITY.md) for the
private channel.

## How to actually get a problem fixed

1. **Use the app's Send Feedback button.** It builds a sanitized log — player
   and team names are stripped before anything leaves your machine — and hands
   it to a GitHub issue, an email, or your clipboard. This is the preferred
   path for anything wrong with a run, because it carries the detail that
   makes a problem diagnosable without carrying the names. See
   [Sending feedback](README.md#sending-feedback).
2. **Otherwise, file an issue.** The forms walk you through what is needed and
   warn you about names before you type.

## Running it yourself

Everything you need is in the README: [Run from source](README.md#run-from-source-any-platform)
for setup, and [Development Checks](README.md#development-checks) for the two
commands a change has to pass:

```sh
python -m pytest tests/
python -m ruff check .
```

Run the suite under `pytest`, not `unittest discover` — the latter silently
skips the entire web-app surface and reports green on a regression.
