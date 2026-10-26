# Brief 11 — the paste-ready task for the security engineer

Paste everything below the line. The companion brief is
`docs/pm/brief-11-the-walk-stops-paying-for-resolve.md`; `## Result` goes
there.

---

You are the **security engineer** on OmniAgent, `D:\code-project\OmniAgent`,
branch `main`, HEAD `6fbdced`. Baseline, re-run by the manager today: **642
tests passing**, `ruff` clean, `mypy` strict clean over 44 files, tree clean.

**Read `docs/pm/brief-11-the-walk-stops-paying-for-resolve.md` and execute
it.** Two stages, two commits, a third for your report. **No model run is
needed anywhere** — your sandbox's `WinError 10013` does not come into it.

## Answer these two before you start, in your first message

1. **Can you create a junction (`mklink /J`) and a symlink in your sandbox?**
   Junctions need no administrator rights; symlinks usually do, or Developer
   Mode. If symlinks are unavailable, say so and run the junction mutations —
   **do not quietly skip them.**
2. **Does `st_file_attributes` exist on your Python build?** Windows only. If
   it is missing, stop and report rather than inventing a substitute.

## What you are attacking

`tools.py:539 _searchable_files` walks with `iterdir()` and calls
`workspace.resolve()` on **every** entry, which does a full `Path.resolve()`
(`sandbox.py:105-138`), plus `is_dir()`, sometimes `is_symlink()`, and a
`stat()`. Measured today, three passes, plain workspace first because running
one warms the cache for the other:

| | plain | sealed |
| --- | --- | --- |
| wall | **1.25 / 1.25 / 1.44 s** | 0.60 / 0.60 / 0.61 s |
| `resolve` calls | **4,681** | 685 |
| time in `resolve` | **0.89 / 0.88 / 1.01 s** | 0.47 / 0.48 / 0.49 s |
| share | **70–71%** | 79–80% |

**Stage 1:** replace `iterdir()` with `os.scandir()` and take `is_dir`,
`is_file`, `is_symlink` and `stat` from the `DirEntry`, which already has them
from the directory read. **Do not touch `resolve()` yet.** Report the figures
in the same shape. **If Stage 1 alone brings the plain wall under ~0.6 s, say
so and stop** — bring me the number and I decide whether Stage 2 is worth
touching a security boundary for.

**Stage 2:** a child of an already-resolved, already-inside directory is
inside too, **unless it can point elsewhere** — so only those need a full
`resolve()`. The denied, hidden, credential-name and size checks still run on
every entry.

## The hazard, and it is the whole brief

**On Windows, `is_symlink()` is not the test for "can point elsewhere".** A
**junction** is a directory reparse point that `Path.resolve()` follows and
that `is_symlink()` reports as `False`, and `mklink /J` needs no
administrator rights. A walk that skips `resolve()` for every non-symlink
**follows a junction straight out of the workspace** — a sandbox escape
bought with a performance change.

The test must be the reparse-point attribute
(`stat.FILE_ATTRIBUTE_REPARSE_POINT` via
`entry.stat(follow_symlinks=False).st_file_attributes`), with `is_symlink()`
as the POSIX path. `scandir` has already read it, so it is free.

**If you cannot establish by test that your check catches a junction, do not
ship Stage 2. Report it.** A slow walk is a correct walk.

## Hard invariant

**Byte-identical output on both workspaces**, compared by hash, not by eye.
`_searchable_files` sorts on the walked path and the training examples were
collected against that order.

## Mutations — build the hostile trees in a scratchpad directory, never in the repo

Ma a junction pointing outside the workspace · Mb a symlink to an outside
directory · Mc a symlink to an outside file · **Md remove your reparse-point
check and confirm Ma now fails** · Me a denied path under the root · Mf a
hidden directory with files · Mg a file over `max_file_bytes`. Ma, Mb, Mc, Me,
Mf and Mg must behave identically under the old code and the new.

**Md is the one that matters.** A test asserting "this is refused" proves
nothing if several guards would refuse it — containment, denial and
hiddenness could each catch a badly built fixture. Md tells you which one is
doing the work.

## Files you may touch

`sandbox.py` · `tools.py` (`_searchable_files` and nothing else in it) ·
`tests/test_sandbox.py` · `tests/test_search_text_pruning.py` ·
`tests/test_tools.py`

## Files you may not touch

`agent.py` · `scripts/**` · `tests/test_eval_workspace.py` ·
`tests/test_holdout_questions.py` · `tests/test_holdout_record.py` ·
`eval-fixture/**` · `questions/**` · `models/**` · `data/**` ·
`omniagent-core/**` · `.github/workflows/**` · `NEXT_CHAT.md` · `README.md` ·
`docs/` except your `## Result` · anything on `core-offline-runtime`.

`scripts/holdout_eval.py` and `tests/test_holdout_record.py` are **reserved
for brief 12**, which goes to the fullstack engineer, so the two briefs
cannot collide. If a file is in neither list, ask rather than decide.

**Do not change a tool's description or the system prompt** — they reach the
model every turn and are part of every training example.

## Gates

```
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m pytest
```

Full path, **never your own `-q`**. Baseline **642 passed**, mypy clean over
**44** files. Your new tests move the count — say what to.

## Commits

```
git add tools.py tests/
git commit -m "perf(search_text): take what the directory read already knows"

git add sandbox.py tools.py tests/
git commit -m "perf(search_text): resolve only what can point elsewhere"

git add docs/pm/brief-11-the-walk-stops-paying-for-resolve.md
git commit -m "docs: brief 11 result -- the walk's remaining cost, measured"
```

**Do not run a bare `git push`** — two remotes, and `main` tracks the one this
work does not belong to. Name it: `git push origin main`.

## The one thing that would make this wrong

**Buying speed with a hole.** If the new walk is fast and Ma is green only
because a different guard caught the junction, the hole is there and the test
is lying to you. Md is not optional.

The second way: **output that is nearly identical.** A different order, one
file more or fewer, and every figure collected against the old order stops
being comparable. Hash it.
