# Brief 03 — `search_text` prunes as it descends

**For the fullstack engineer.**

`NEXT_CHAT.md` item 1 has said since 2026-10-06 that `search_text` is slow
because `sorted(start.rglob("*"))` materialises every path before filtering.
**That diagnosis is wrong, and I measured it today before writing this brief.**
Materialising is 6% of the cost. The prescription in that note — prune as you
descend — is right, for a different reason, and worth about twenty-five seconds
rather than one and a half.

## What is measured, 2026-10-23, on HEAD `f4687e4`

A replay of `tools.py:555-587` against the real workspace, root `.`, needle
`"ReAct"`, with a per-phase clock. Three runs:

| Phase | Run 1 (cold) | Run 2 | Run 3 |
| --- | --- | --- | --- |
| `sorted(rglob("*"))` — 87,482 paths | 1.57 s | 1.67 s | 1.60 s |
| **`workspace.resolve(...)` — 69,186 denied** | **25.32 s** | **25.52 s** | **23.29 s** |
| `stat()` | 0.00 s | 0.00 s | 0.00 s |
| `read_bytes()` — 4,627,772 bytes over 400 files | 3.22 s | 0.03 s | 0.04 s |
| decode and match | 0.04 s | — | — |
| **total** | **34.92 s** | **29.06 s** | **26.62 s** |

Warm, the shape is stable: **`resolve()` is 87–88% of the run, the walk is 6%,
and reading the files is four hundredths of a second.** The 3.22 s read on run 1
is a cold page cache; it does not recur.

That total also matches the 25.7 s this project already recorded for an
unsealed search, which means **that 25.7 s was essentially all `resolve()`**.

### What is actually happening

The loop calls `workspace.resolve(workspace.display(candidate))` once per
candidate **file**, and `sandbox.py:181 _is_hidden` refuses anything with a
dot-prefixed path component. Under `.venv`, `.ci-venv` and `.git` that is
**69,186 files**, each one costing a `display`, a full path resolution and a
raised `SandboxError` that is then discarded. The pruning idiom skips the whole
branch at the directory, so those 69,186 resolutions never happen.

Pruning dot-directories during descent takes the enumeration from 87,482 paths
at 1.6 s to **4,578 paths at 0.06–0.08 s**, measured over three reversed-order
runs — reversed because running the pruned walk after the full one let the full
one warm the cache for it, and the first figure I got that way, 4.58 s, was a
cold-cache artefact.

### Where the 400-file budget goes, and why that is not in this brief

`MAX_SEARCH_FILES` is 400, and of the 400 files scanned from the root:

| Top-level directory | Files scanned |
| --- | --- |
| `models/` | **285** |
| `data/` | 92 |
| `docs/` | 9 |
| `__pycache__/` | 8 |
| the six tracked root `.py` files and `LICENSE` | 6 |

`models/` is not hidden and not denied, so it is legitimately in scope today,
and it takes 71% of the budget. `data/` is the evaluation output directory.
**Changing that is a tool-behaviour change, not an optimisation**, and the
153-example dataset was collected against the current behaviour. It is a
decision for the project owner and it is **deliberately out of this brief.**
Do not touch `sandbox.py`'s denied or listing-only sets.

## Goal

`search_text` produces **byte-identical output** to what it produces today, in
under a second from the workspace root.

## Files you may touch

- Modify: `tools.py` — `search_text` and whatever private helper you add
- Modify or add: the test module that covers `search_text`

Do not touch `sandbox.py`. Do not change `MAX_SEARCH_FILES`,
`MAX_SEARCH_MATCHES`, `max_file_bytes`, or any tool description — a tool
description reaches the model on every turn and is part of every training
example, so changing one invalidates the dataset.

## Interfaces it must produce

A private helper in `tools.py`:

```python
def _searchable_files(workspace: Workspace, start: Path) -> list[Path]:
    """Files under `start` the workspace admits, pruned branch by branch.

    Resolving every path under a hidden directory and discarding it afterwards
    is 87% of a search from the root.
    """
```

- It descends directory by directory and **prunes the whole branch** when
  `workspace.resolve(workspace.display(child))` raises. The project already
  pays for this idiom at `tests/test_eval_workspace.py:113 reachable_files` —
  read it and match it rather than inventing a second shape.
- **It returns `sorted(...)`.** This is the part that is easy to get wrong.
  Today's candidate order is a global sort of full path strings, and
  `MAX_SEARCH_FILES` and `MAX_SEARCH_MATCHES` truncate, so the order decides
  *which* matches the agent sees. An `os.walk` that yields per-directory
  produces a different order and therefore different output. Collect, then sort
  exactly as before.
- `search_text` keeps its own per-candidate `resolve` for the files the helper
  returns, or drops it if the helper already resolved them — either is fine,
  but the output must not change.

## The tests that must fail first

Write them, run them, **paste the failing output**, then change `tools.py`.

1. **Output equivalence against a golden string.** Build a fixture workspace
   containing: a file with two matches, a subdirectory with a match, a
   dot-directory with a match, a file over `max_file_bytes`, and a binary file
   with a null byte in the first bytes. Capture what `search_text` returns
   **today** and assert the new implementation returns exactly that. Run it
   against the current code first so the golden value is measured, not written
   from belief.

2. **Ordering under truncation.** A fixture with more matches than
   `MAX_SEARCH_MATCHES` across several directories, asserting the exact list of
   matches returned. This is the test that catches a reordered walk, and
   without it the change is unverifiable.

3. **No resolution happens under a pruned branch.** Assert that searching a
   tree whose dot-directory holds thousands of entries does not resolve them —
   count the calls by wrapping `workspace.resolve`, or assert the helper's
   returned length. A timing assertion is not acceptable; it will be flaky on
   CI.

## Mutation checks that must go red

Copy each file to a scratch directory outside the repository first and restore
from that copy. Never `git checkout --` alone. Assert the target string is
present before replacing it.

| # | Mutation | Must go red |
| --- | --- | --- |
| M1 | Drop the `sorted()` from `_searchable_files` | the ordering test |
| M2 | Prune on `child.name.startswith(".")` instead of on the workspace's own refusal | the equivalence test — the workspace refuses more than hidden names, and a second copy of its rules in `tools.py` is a rule that will drift |
| M3 | Do not prune: recurse into a branch whose resolve raised | test 3 |
| M4 | Delete test 1's assert | **nothing** — it must go green, so you know M1 and M2 were caught by the tests you think caught them |
| M5 | Return files whose size exceeds `max_file_bytes` | the equivalence test |

Report every test that turned red for each mutation, by name, and say which is
yours when more than one is.

## Measure the result, and report the number

Before and after, from the workspace root, same needle, **three runs each,
warm**:

```
.venv\Scripts\python.exe -c "import time,tools;t=time.perf_counter();tools.search_text('ReAct','.');print(f'{time.perf_counter()-t:.2f} s')"
```

Baseline to beat: **26.6–29.1 s warm.** Report your three numbers, not an
average of one run. If the result is not under a second, say so — the walk is
6% of the cost and the rest is the resolutions this change removes, so
something is still resolving a branch it should have pruned.

## The three gates

```
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m pytest
```

Full path, **no `-q` of your own** — `pyproject.toml:168` sets it and a second
one deletes the summary line. Baseline **633 passed**; you add three tests, so
expect **636**. Report the actual number.

`search_text` already carries `# noqa: PLR0912` for its branch count. If your
helper lets you remove that, remove it; if you need a second one, say why in
`## Result` rather than adding it silently.

## The one thing that would make this wrong

**Making the search faster while changing what it returns.** The output order
decides which 50 matches of a truncated search the agent sees, and the 153
training examples in `G:/OmniAgent/datasets/2026-10-10-merged/` were collected
against today's output. A faster `search_text` that returns a different string
for the same query silently invalidates every training example that used it,
and no gate in this repository would notice.

That is why test 1 is a golden string captured from the current code and test 2
asserts an exact truncated list. If you cannot make the new implementation
reproduce them, **stop and report it** — the ordering is the contract, not the
speed.

The second way: copying `sandbox.py`'s rules into `tools.py` to decide what to
prune. The workspace is the only thing that knows what it refuses. Ask it, and
prune on its answer.

## Commit

```
git add tools.py tests/
git commit -m "perf(search_text): prune a refused branch instead of resolving every leaf"
```

Do not run a bare `git push` — this repository has two remotes and `main`
tracks the one this work does not belong to. Leave it unpushed.

## Result

<!-- Engineer: append here. The failing outputs, every mutation with the names
of the tests that changed colour, the three before and three after timings, the
three gate results, the pytest count, the commit hash, and anything you refuse
to claim. -->
