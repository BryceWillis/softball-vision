# Security Policy

## The property that matters most: no real player names

This tool reads youth-softball video, so real player names flow through it
constantly — and **no real player name may ever appear in this repository**.
Every name in the code, tests, docs, and examples is an invented placeholder,
enforced by a test in CI. This is the project's paramount security property:
git history is public, so a leaked name is the one defect that cannot be
fixed forward.

**If you find a real name in this repository or its history: do not open a
public issue.** A public report re-publishes the leak while reporting it.
Instead, use **Report a vulnerability** on this repository's Security tab —
it is private to the maintainer.

## Other vulnerabilities

Use the same private channel: **Security tab → Report a vulnerability**.

Before reporting, know what is by design. The web app is local-first:
loopback-bound, single-user, and unauthenticated. It has no CSRF or
same-origin protection on its mutating routes, and that is the accepted
posture for a localhost-only install — that hardening is deliberately
deferred until any hosted seam exists. Reports that a scanner flagged
these on `127.0.0.1` are expected and not vulnerabilities here.

## Supported versions

The latest release. No response-time promises — this is a personal-use
project maintained in spare time.
