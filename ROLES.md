# Project Roles

This file is the canonical reference for roles, responsibilities, and workflow in this project. All agents and contributors should read it before doing any work.

---

## The Roles

Three role *types* — Product Owner, Architect, Implementer — across four agents (the Implementer role is shared by two: Codex and Fable 5).

### 1. Product Owner — Ryan Moore

Ryan owns the product direction, runs the tool on real games, approves implementations, and decides when work is done. He starts each work session by directing agents to the next task or asking for a review.

### 2. Architect — Claude (Claude Code)

Claude is the senior architect. In a fresh session, Claude's role is to:

- **Design** full implementations for roadmap items before Codex touches them. Designs are written directly into `Roadmap.md` under the item's section, covering the algorithm, data model changes, acceptance criteria, and edge cases.
- **Review** Codex's implementations via code review passes. Findings are written to `CODE-REVIEW.md` as numbered items (CR-XX). The `/code-review` skill runs the review.
- **Resolve** CR items after verifying Codex's fixes — moving them from "Ready for Review" to the Resolved section of `CODE-REVIEW.md`.
- **Maintain** the Implementation Queue in `Roadmap.md`, keeping item order and rationale current.

Claude does **not** write implementation code. The one commit Claude makes is the **review-approval commit** that concludes a successful review pass (see CR Lifecycle) — staging the reviewed changes plus the `Roadmap.md`/`CODE-REVIEW.md` updates and committing them, because that commit *is* the approval signal. Claude does not commit at any other time. When Ryan says "ready for a review," Claude runs a review pass. When Ryan asks for a design, Claude writes it into the Roadmap.

### 3. Implementers — Codex and Fable 5

There are **two implementers**: Codex, and Claude Code running on **Fable 5** (`claude-fable-5`). They are interchangeable and follow the **same protocol** below. Only one should hold a given item at a time — check the queue/CR status before picking work so the two don't collide on the same item. In a session, an implementer should:

1. **Check `CODE-REVIEW.md` first.** Open items always preempt the roadmap queue. If any item has status **Open**, implement it before picking up any roadmap work.
2. **Read the Implementation Queue** in `Roadmap.md`. Pick the highest-priority item that is **Ready to implement** and not already claimed by the other implementer.
3. **Stop for items marked "Needs design."** Do not start implementation. Ask the architect (Opus) to write the full design first.
4. **Implement per the architect's design** in `Roadmap.md`. Do not reinterpret or simplify the design without flagging it.
5. **Update `CODE-REVIEW.md`** for any CR being fixed: set status to **Ready for Review** and add a short implementation note describing what was done and how tests were added.
6. **Run the full test suite** before considering work done. All tests must pass.
7. **Update `Roadmap.md`** — move the implemented item's status to "Ready for review" in the queue table.

An implementer does **not** write designs, move CRs to Resolved, or conduct code review passes — those belong to the Architect (Opus).

**Independent review is preserved.** The Architect (Opus) reviews all implementations regardless of which implementer wrote them. No agent reviews or approves its own work: Fable 5 implements but never runs a review pass on code it wrote. Review and the approval commit stay with the Opus architect.

---

## Workflow Loop

```
Ryan: "design item N"
  → Claude writes full design into Roadmap.md item N section

Ryan: "implement" (or an implementer — Codex or Fable 5 — picks up next queue item)
  → implementer checks CODE-REVIEW.md for Open items first
  → implementer implements, updates CR status to "Ready for Review"
  → implementer runs tests (must all pass)
  → implementer updates Roadmap.md queue status

Ryan: "ready for a review"
  → Claude runs /code-review skill
  → Claude writes findings (CR-XX) to CODE-REVIEW.md as Open items
  → Claude optionally resolves already-Ready-for-Review items in the same pass

Ryan: "Codex completed the CRs, please review"
  → Claude reads each CR's implementation note in CODE-REVIEW.md
  → Claude reads the relevant source files and tests
  → If all CRs pass: Claude moves them to Resolved and **commits all staged changes** — the commit IS the approval
  → If new findings arise: Claude writes them as Open items, does NOT commit, and the loop repeats
```

---

## File Map

| File | Owner | Purpose |
|------|-------|---------|
| `ROLES.md` | Architect | This file. Canonical role definitions. |
| `CLAUDE.md` | Architect | Claude Code session bootstrap — assigns architect role, points here. |
| `AGENTS.md` | Architect | Codex session bootstrap — assigns implementer role, points here. |
| `Roadmap.md` | Architect | Item designs, Implementation Queue, accepted deliverables. |
| `CODE-REVIEW.md` | Architect / Codex | CR lifecycle: Open → Ready for Review → Resolved. |
| `PROJECT-EXPLANATION.md` | Ryan | Plain-English product description for new contributors. |
| `NEW_GAME_CHECKLIST.md` | Ryan | Operational checklist for processing a new game video. |

---

## CR Lifecycle (CODE-REVIEW.md)

| Status | Set by | Meaning |
|--------|--------|---------|
| Open | Architect | Finding accepted; Codex should implement. |
| Ready for Review | Codex | Implementation done and tested; awaiting architect confirmation. |
| Resolved | Architect | Implementation verified; item moved to Resolved section. |
| Deferred | Architect | Valid finding, intentionally postponed. |

---

## Security Constraint — Player Name Sanitization

**Real player names from actual game runs must never be committed to the public repository.**

- All public-facing examples (tests, docs, README) use sanitized placeholder names: `Emma B.`, `Olivia M.`, `Maya R.`, `Amelia V.`, `Ava T.`, `Sofia L.`, `Riley S.`, `Mia K.`, `Charlotte P.`, `Ella C.`, `Abby W.`, `Zoe H.`, `Chloe N.`
- Real runs live in `runs/` (gitignored).
- Real roster CSVs live in `rosters/` (gitignored).
- Both agents must audit any new test fixtures, documentation examples, or sample data before committing to ensure no real names are present.
