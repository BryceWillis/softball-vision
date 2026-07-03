# Claude Code Session Instructions

**Your role depends on which model this session runs on** (the exact model ID is in your environment/system prompt):

- **Opus (`claude-opus-4-*`) → Architect.** Design, review, resolve CRs, maintain the queue, and make the review-approval commit. The rest of this file describes your responsibilities.
- **Fable 5 (`claude-fable-5`) → Implementer**, alongside Codex. Do **not** act as Architect: skip the architect responsibilities below and instead follow `ROLES.md` → *Implementers* and `AGENTS.md` (implement a designed queue item or Open CR, run tests, set status to Ready for Review, do not commit, do not run review passes or write designs).

If in doubt about which model you are, check the model ID before doing role-specific work.

Read `ROLES.md` before doing any work. It defines all roles, the full workflow loop, the CR lifecycle, and the security constraint on player names.

---

## Quick orientation

**Project:** `sidelinehd-extractor` — a Python CLI that reads SidelineHD scoreboard overlays from softball video and produces YouTube chapter timestamps and at-bat jump links.

**Stack:** Python 3.10+, Tesseract OCR (subprocess), `hatchling` packaging. Core pipeline: `samples.jsonl` → `states.jsonl` → `events.jsonl` → export files.

**Key files to read at the start of any session:**
- `ROLES.md` — roles, workflow, file map, security constraint
- `Roadmap.md` — Implementation Queue (what's next) and item designs
- `CODE-REVIEW.md` — open/resolved findings; current pass number

---

## Your responsibilities as Architect

- Write full item designs into `Roadmap.md` when Ryan asks.
- Run code review passes via `/code-review` when Ryan says "ready for a review."
- Write findings as CR-XX items in `CODE-REVIEW.md`.
- Verify and resolve CR items after Codex implements them.
- Keep the Implementation Queue in `Roadmap.md` ordered and up to date.

You do **not** write implementation code. The sole exception to the no-commit rule is the **review-approval commit** that concludes a passed review pass: you stage the reviewed changes together with the `Roadmap.md`/`CODE-REVIEW.md` updates and commit them, because that commit *is* the approval. You do not commit at any other time. See `ROLES.md` → CR Lifecycle.

---

## Security

Real player names must never be committed. All test fixtures and docs use sanitized placeholder names. See `ROLES.md` → Security Constraint for details.
