# Brief 03 — the paste-ready task for the fullstack engineer

Paste everything below the line. The engineer works in this repository, so it
reads the brief itself; this carries the constraints that must not be missed.

---

You are the fullstack engineer on OmniAgent, `D:\code-project\OmniAgent`,
branch `main`, HEAD `f4687e4`. Baseline: **633 tests passing**, `ruff` clean,
`mypy` strict clean over 42 files.

**Read `docs/pm/brief-03-search-text-prunes-as-it-descends.md` and execute it.**
It carries today's measurements; do not re-derive them, and do not trust
`NEXT_CHAT.md` item 1 on this subject — the brief retracts its diagnosis with
figures.

Before you write anything, read `tests/test_eval_workspace.py:113
reachable_files`. It is the pruning idiom this project already paid 113 seconds
to learn. Match it rather than inventing a second shape.

## The constraints that decide whether this is right

1. **The output must not change, byte for byte.** `MAX_SEARCH_FILES` is 400 and
   `MAX_SEARCH_MATCHES` is 50, so the candidate *order* decides which matches
   the agent sees. Today's order is a global sort of full path strings. An
   `os.walk` yielding per directory gives a different order and therefore
   different output. **Collect the pruned paths, then `sorted()` them exactly
   as before.** The 153 training examples were collected against today's
   output, and no gate in this repository would notice if you changed it.
2. **Prune on the workspace's own refusal, not on a rule you copy.** Call
   `workspace.resolve(workspace.display(child))` on each directory entry and
   prune the whole branch when it raises. `sandbox.py` refuses more than
   dot-prefixed names, and a second copy of its rules in `tools.py` is a rule
   that will drift.
3. **Do not touch `sandbox.py`**, `MAX_SEARCH_FILES`, `MAX_SEARCH_MATCHES`,
   `max_file_bytes`, or any tool description. A tool description reaches the
   model every turn and is part of every training example.
4. **`models/` stays in scope.** It takes 285 of the 400 scanned files, and
   removing it is a behaviour change the project owner has not decided. Out of
   scope for this task.

## Environment rules, each already paid for once

- **Full interpreter path: `.venv\Scripts\python.exe`.** A bare `python`
  resolves to `.ci-venv`.
- **Never pass `-q` to pytest yourself** — `pyproject.toml:168` sets it, and a
  second makes it `-qq` and deletes the `NNN passed` summary line.
- **Mutation checks: copy to a scratch directory outside the repository and
  restore from that copy.** Never `git checkout --` alone. Assert the target
  string is present before replacing it — a `sed` pattern containing `\n`
  matches nothing silently, so a mutation can appear to pass without having
  mutated anything.
- **`cmd.exe` reads `/` as a switch** — use backslashes there.
- A throwaway measurement script goes in a scratch directory, **not in the
  repository**: a repo file quoting evaluation material fails the
  eval-workspace invariant.
- **When you time anything, run the candidate first and the baseline second, or
  reverse the order and run it again.** I got 4.58 s for a walk that is really
  1.6 s because the previous measurement had warmed the page cache for it.

## Order of work

1. The three tests from the brief, failing, with the golden value for test 1
   **captured by running the current code**, not written from belief.
2. The helper and the change to `search_text`.
3. The five mutation checks, M1 to M5.
4. Three warm timings before and three after. Baseline **26.6–29.1 s**.
5. The three gates. Expect **636 passed**.
6. One commit:
   `perf(search_text): prune a refused branch instead of resolving every leaf`

**Do not run a bare `git push`** — two remotes, and `main` tracks the one this
work does not belong to. Leave it unpushed.

Append `## Result` to the brief: the failing outputs, each mutation with the
names of the tests that changed colour, your six timings, the gate results, the
pytest count, the commit hash, and **anything you refuse to claim**. Then stop.

## The one thing that would make it wrong

Making the search faster while changing what it returns. If the new
implementation cannot reproduce the golden string and the exact truncated match
list, **stop and report it.** The ordering is the contract; the speed is the
task.
