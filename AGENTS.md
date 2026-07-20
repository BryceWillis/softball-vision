# Softball Vision (`sidelinehd-extractor`)

This repository holds the **implementation**. The design, the roadmap, and the review workflow live in a **separate documentation repository**, mounted alongside it at:

```
../obsidian-projects/softball-vision-docs/
```

Note the `-docs` suffix: the notes folder is `softball-vision-docs`. The unsuffixed name is *this* repository.

## Read this first, before you write any code

1. **`../obsidian-projects/softball-vision-docs/AGENTS.md`** — the working agreements: this project's constraints, its security rule, its testing requirements, and pointers to the shared process. **Follow them.** They are canonical and they override any habit you have.
2. **`../obsidian-projects/_process/`** — the shared process: roles, the review cycle, the two commands, how a finding is written.
3. **`01-architecture.md`** — the design, and more importantly the decisions and assumptions behind it.
4. **`03-experience.md`** — the UI spec, if your change touches the web app or the desktop launcher.
5. **`CHANGE-REQUESTS.md`** — the change currently in flight, and its state.

**Read only `_process/` and `softball-vision-docs/`.** The documentation vault holds several unrelated projects; the others are not context. See `../obsidian-projects/_process/SCOPE.md`.

If the notes folder is not mounted or you cannot read it, **stop and say so.** Do not infer the project's state or intent from the code alone — the reasoning is in the docs, and the parts most likely to trip you are the assumptions the code cannot express.

## The rules that catch people out

- **Never commit your own work.** Build, test, then hand off for review uncommitted. The commit belongs to the reviewer, and only on approval — committing your own unreviewed work makes the review advisory rather than binding.
- **Every change ships with tests.** A change without them is not ready for review. Run `python -m pytest tests/` (not `unittest discover`, which silently skips the entire web-app surface) and `python -m ruff check .`; both must be clean.
- **The reviewer is never the agent that wrote the code.** That is the whole point of the gate — and why the reviewer is the one trusted to commit.
- **Never commit a real player name.** This is youth-sports data in a public repository. Fixtures, docs, and examples use sanitized placeholders only; `runs/` and `rosters/` are gitignored and stay that way. A leak is the one defect here that cannot be fixed forward.
- **Restart the server after changing code.** A long-lived `serve` process holds the old code in memory — this once produced a game's worth of plausible-looking wrong scores for two days. If output disagrees with the code you are reading, suspect a stale server first.

Everything else is in the notes folder's `AGENTS.md`.

---

*Historical note: this project previously ran its own governance out of `ROLES.md`, `Roadmap.md`, and `CODE-REVIEW.md` in this repository. Those are retired and archived under `docs/archive/`; the process is now the vault's shared one, and the roadmap lives in the notes folder. The archive is history, not instructions — do not work from it.*
