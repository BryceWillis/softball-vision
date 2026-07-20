# Archive — retired governance files

**These files are history. Do not work from them.**

Until 2026-07-20 this project ran its own governance out of the repository root. That has been replaced by the documentation vault's shared process. The live files are:

| Was | Is now |
|---|---|
| `ROLES.md` | `../../../obsidian-projects/_process/` — roles, cycle, findings, testing |
| `Roadmap.md` | `../../../obsidian-projects/softball-vision-docs/02-roadmap.md` and the `0N-mN-plan.md` files |
| `CODE-REVIEW.md` | `../../../obsidian-projects/softball-vision-docs/CHANGE-REQUESTS.md` |

## What changed, and why these are kept

The old model had **four role-holders** — a product owner, an Opus architect who designed *and* reviewed *and* made the approval commit, and two interchangeable implementers (Codex and Fable 5) who were kept apart by a mandatory git-worktree-per-item rule.

The new model has **three roles** — spec author, implementer, reviewer — and keeps them apart with a status lock in `CHANGE-REQUESTS.md` instead of with worktrees. The worktree rule existed to stop two implementers co-mingling unrelated items in one uncommitted working tree, which happened once and forced a six-item batch review. The `in progress` / `in review` locks close that hole by a different route: only one change is in flight at a time. **The constraint that survives unchanged is the important one — the agent that commits is never the agent that wrote the code.**

`Roadmap.md` was 5,038 lines and held the full design for all 67 items. `02-roadmap.md` deliberately does not reproduce them: shipped work is summarized in one line each, and only unbuilt milestones carry full designs. **The detailed designs for shipped items live here and nowhere else** — that is the main reason this archive exists rather than being deleted.

`CODE-REVIEW.md` held 35 review passes. `CHANGE-REQUESTS.md` is a worklist, not a changelog, so it carries only the three findings that were still open at migration. The rest of the history is here and in `git log`.

## If you are looking for something

- **Why a shipped feature works the way it does** → the item's section in `Roadmap.md` here, or `01-architecture.md` in the notes folder, which has the decisions and the rejected alternatives.
- **Whether a bug was seen before** → `CODE-REVIEW.md` here. Findings are numbered `CR-XX`.
- **What to work on next** → **not here.** `02-roadmap.md` in the notes folder.
