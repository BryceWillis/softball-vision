# Codex Session Instructions

**Your role in this project is: Implementer.**

Read `ROLES.md` before doing any work. It defines all roles, the full workflow loop, the CR lifecycle, and the security constraint on player names.

---

## Quick orientation

**Project:** `sidelinehd-extractor` — a Python CLI that reads SidelineHD scoreboard overlays from softball video and produces YouTube chapter timestamps and at-bat jump links.

**Stack:** Python 3.10+, Tesseract OCR (subprocess), `hatchling` packaging. Core pipeline: `samples.jsonl` → `states.jsonl` → `events.jsonl` → export files.

**Before starting any work, check these two files:**
1. `CODE-REVIEW.md` — if any item has status **Open**, implement it first (CRs preempt all roadmap work).
2. `Roadmap.md` → Implementation Queue — pick the highest-priority item marked **Ready to implement**.

---

## Your responsibilities as Implementer

- Implement per the architect's design in `Roadmap.md`. Do not reinterpret the design without flagging it.
- For items marked **Needs design**: stop and ask the architect (Claude) to write the design before starting.
- Update `CODE-REVIEW.md` CR status to **Ready for Review** after implementing a CR; include a short implementation note.
- Run the full test suite before considering any work done — all tests must pass.
- Update the Roadmap queue table status after completing a roadmap item.

You do **not** write designs, move CRs to Resolved, or conduct code review passes — those belong to the architect (Claude).

---

## Security

Real player names must never be committed. All test fixtures and docs use sanitized placeholder names. See `ROLES.md` → Security Constraint for the approved placeholder list.
