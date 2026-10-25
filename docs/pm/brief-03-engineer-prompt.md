# Brief 03 — the paste-ready task for the fullstack engineer

**Re-issued 2026-10-26.** The task is unchanged; the figures are refreshed,
because three days of other work moved the tree.

Paste everything below the line.

---

You are the fullstack engineer on OmniAgent, `D:\code-project\OmniAgent`,
branch `main`, HEAD `0a4f757`. Baseline: **633 tests passing**, `ruff` clean,
`mypy` strict clean over 42 files.

**Read `docs/pm/brief-03-search-text-prunes-as-it-descends.md` and execute
it**, including the section at the end dated 2026-10-26 — that section carries
the current numbers and supersedes the ones above it.

`tools.py` has been reserved for you and untouched since 2026-10-23. Every
other brief since has forbidden it.

Before you write anything, read `tests/test_eval_workspace.py:113
reachable_files`. It is the pruning idiom this project already paid 113 seconds
to learn. Match it rather than inventing a second shape.

## The measurement, as of today

| Phase | Warm |
| --- | --- |
| `sorted(rglob("*"))` — 89,550 paths | 1.6–2.9 s, **5–9%** |
| **`resolve()` over 70,032 refused paths** | **25.4–27.6 s, 85–87%** |
| `read_bytes()` over 400 files | 0.04–0.06 s |
| **total** | **29.1–32.6 s** |

A cold first run measured 40.9 s with a 7.1 s walk. That is a page-cache
artefact, not the baseline.

**Do not trust `NEXT_CHAT.md` item 1's original diagnosis** — the brief
retracts it with figures. Materialising the path list is 5–9% of the cost. The
cost is `workspace.resolve(workspace.display(candidate))` called once per
candidate **file**, where 70,032 of them are refused by `sandbox.py:181
_is_hidden` under `.venv`, `.ci-venv`, `.git` and friends, each paying a full
path resolution and a discarded `SandboxError`.

**Baseline to beat: 29.1–32.6 s warm.**

## The constraints that decide whether this is right

1. **The output must not change, byte for byte.** `MAX_SEARCH_FILES` is 400 and
   `MAX_SEARCH_MATCHES` is 50, so the candidate *order* decides which matches
   the agent sees. Today's order is a global sort of full path strings. An
   `os.walk` yielding per directory gives a different order and therefore
   different output. **Collect the pruned paths, then `sorted()` them exactly
   as before.** The 153 training examples were collected against today's
   output and no gate here would notice if you changed it.
2. **Prune on the workspace's own refusal, not on a rule you copy.** Call
   `workspace.resolve(workspace.display(child))` on each directory entry and
   prune the whole branch when it raises. `sandbox.py` refuses more than
   dot-prefixed names, and a second copy of its rules in `tools.py` is a rule
   that will drift.
3. **Do not touch `sandbox.py`**, `MAX_SEARCH_FILES`, `MAX_SEARCH_MATCHES`,
   `max_file_bytes`, or any tool description. A tool description reaches the
   model every turn and is part of every training example.
4. **`models/` stays in scope.** It takes 255 of the 400 scanned files and
   removing it is a behaviour change the owner has not decided.

## One trap specific to measuring this today

The working tree currently holds an untracked
`.tmp-omnipatch-release-audit-67a40f9906cc486895f4a4c514569221`, about 994 KB
of Bandit output that no brief asked for. It is dot-prefixed, so the current
code resolves every leaf inside it and throws them away while a pruning walk
skips the branch at the top. **It flatters your fix.**

Measure before and after **on the same tree state**, and say what was in the
tree when you measured. **Do not delete that directory** — it is not yours and
it is reported to the owner separately.

## Environment rules, each already paid for once

- **Full interpreter path: `.venv\Scripts\python.exe`.** A bare `python`
  resolves to `.ci-venv`.
- **Never pass `-q` to pytest yourself** — `pyproject.toml:168` sets it, and a
  second makes it `-qq` and deletes the `NNN passed` summary line.
- **Mutation checks: copy to a scratch directory outside the repository and
  restore from that copy.** Never `git checkout --` alone. Assert the target
  string is present before replacing it — a `sed` pattern containing `\n`
  matches nothing silently.
- **`cmd.exe` reads `/` as a switch** — backslashes there.
- A throwaway measurement script goes in a scratch directory, **not in the
  repository**: a repo file quoting evaluation material fails the
  eval-workspace invariant.
- **When you time anything, reverse the order and run it again.** I measured a
  walk at 4.58 s that is really 1.6 s because the previous measurement had
  warmed the page cache for it.

## Order of work

1. The three tests from the brief, failing, with test 1's golden value
   **captured by running the current code**, not written from belief.
2. The helper and the change to `search_text`.
3. M1 to M5.
4. Three warm timings before and three after. **Baseline 29.1–32.6 s.**
5. The three gates. Baseline **633 passed**; you add three tests, so expect
   **636**.
6. One commit:
   `perf(search_text): prune a refused branch instead of resolving every leaf`

**Do not run a bare `git push`** — two remotes, and `main` tracks the one this
work does not belong to. Leave it unpushed.

Append `## Result` to the brief: the failing outputs, each mutation with the
names of the tests that changed colour, your six timings and what was in the
tree when you took them, the gate results, the pytest count, the commit hash,
and **anything you refuse to claim**. Then stop.

## The one thing that would make it wrong

Making the search faster while changing what it returns. If the new
implementation cannot reproduce the golden string and the exact truncated match
list, **stop and report it.** The ordering is the contract; the speed is the
task.
