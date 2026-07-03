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
4. **Implement per the architect's design** in `Roadmap.md`, following the **design-deviation policy** below.
5. **Update `CODE-REVIEW.md`** for any CR being fixed: set status to **Ready for Review** and add a short implementation note describing what was done and how tests were added.
6. **Run the full test suite** before considering work done. All tests must pass.
7. **Update `Roadmap.md`** — move the implemented item's status to "Ready for review" in the queue table.

An implementer does **not** write designs, move CRs to Resolved, or conduct code review passes — those belong to the Architect (Opus).

### Design-Deviation Policy (tiered)

The design in `Roadmap.md` is the spec the review is checked against. Deviating from it is sometimes right — the implementer sees the real code — but the risk lives in *cross-cutting* changes, where the implementer lacks the architect's whole-roadmap context. So the policy is tiered by **blast radius**, with one hard rule.

**Escalation test — ask before deviating:** *Could this change affect another item, a user-visible contract, the security/name constraint, or a future design decision?*

- **No → adjust and flag.** For changes local to this item's own internals — a detail the design left unspecified, a rename to avoid a real collision, an obvious defensive guard, a template/layout choice — the implementer may make the call, and **must record it** (see the hard rule). The on-the-ground context is an asset here.
- **Yes → stop and ask the architect first**, before implementing. This covers: changing a default or user-visible behavior; touching the security/PII boundary or name handling; altering a data format, API, or contract another item depends on (e.g. `finalize_run_exports`, the corrections/roster CSV, the manifest); or dropping/weakening an acceptance criterion. These are exactly where missing context bites (see the item 41 `save_crops` default flip — a reasonable-looking local call that rippled into the review UI and existing behavior; it should have been escalated).

**Hard rule — never silent.** Every deviation, either tier, is recorded as a **Deviations** line in the item's `CODE-REVIEW.md` Ready-for-Review note, so the architect evaluates it at review regardless. An unflagged change quietly defeats the review anchor.

**Independent review is preserved.** The Architect (Opus) reviews all implementations regardless of which implementer wrote them. No agent reviews or approves its own work: Fable 5 implements but never runs a review pass on code it wrote. Review and the approval commit stay with the Opus architect.

**Independent review is preserved.** The Architect (Opus) reviews all implementations regardless of which implementer wrote them. No agent reviews or approves its own work: Fable 5 implements but never runs a review pass on code it wrote. Review and the approval commit stay with the Opus architect.

**Worktree isolation is mandatory when both implementers are active (learned Pass 16→17).** Two implementers editing the same uncommitted working tree co-mingle unrelated items in the same files (e.g. items 41 and 48 both landed in one uncommitted `workflow.py`), which makes per-item review and the "commit = approval" model impossible. Therefore:

- **One item (or CR) per branch, in its own git worktree**, branched off the latest approved `main`. Never implement directly in the shared `main` working tree while another implementer is active.
  - `git worktree add ../sv-item-<N> -b impl/item-<N> main`
- **Submit for review from that branch.** The architect reviews the branch diff against `main` (`git diff main...impl/item-<N>`) and, on approval, commits/merges it. Only reviewed branches reach `main`.
- **If two items must touch the same file, sequence them** — the first merges to `main`, the second rebases onto it — rather than editing the same file in two live worktrees.
- Keep the `main` working tree clean between approvals so the next branch starts from a reviewed base.

### Implementer Session Prompt Template (mandatory first step: worktree)

Every implementer session — Codex or Fable 5 — starts from this template. The
`git worktree` command is **step 0 and non-negotiable**: it is what prevents the
Pass 16→17 shared-tree tangle. Fill in `<N>` (item number) and the item name.

```
You are the Implementer on sidelinehd-extractor (<Codex | Fable 5>). Read ROLES.md
(your role, the security constraint, the CR lifecycle) before writing code.

STEP 0 — ISOLATE (do this before anything else, do not skip):
  git fetch origin && git worktree add ../sv-item-<N> -b impl/item-<N> origin/main
  cd ../sv-item-<N>
Work ONLY in this worktree. Never edit the shared main working tree.

TASK: implement item <N> (<name>) per its design in Roadmap.md — or the named
Open CR in CODE-REVIEW.md, which preempts the queue.

RULES:
- Follow the tiered design-deviation policy (see ROLES.md). Ask yourself: could a
  change affect another item, a user-visible contract, the security/name
  constraint, or a future design decision? If YES, stop and ask the architect
  before implementing. If NO (local to this item's internals), you may adjust.
  Either way, NEVER deviate silently — record every deviation as a "Deviations:"
  line in your CODE-REVIEW.md note.
- Reuse existing pipeline/helpers; do not re-implement what the codebase has.
- Security: never write real player names to committed files; fixtures use
  sanitized placeholders. Names only leave the machine via item 38/39e.
- Run the full suite (PYTHONPATH=src python3 -m pytest tests/) and ruff; all green.

WHEN DONE:
- Set the item Ready for Review in CODE-REVIEW.md (short implementation note) and
  in the Roadmap queue. Commit to your branch impl/item-<N>. DO NOT commit to main,
  DO NOT merge, DO NOT run a review pass or resolve CRs — those are the Opus
  architect's. Tell Ryan the branch name so the architect can review
  `git diff origin/main...impl/item-<N>`.
```

The architect reviews the branch diff, and the **approval commit merges the branch
to `main`** (`git merge --no-ff impl/item-<N>` or an equivalent squash) — that
merge is the approval signal. After merging, prune the worktree
(`git worktree remove ../sv-item-<N>`).

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
