# Brief 01 — the paste-ready task for the engineer

Everything below the line is self-contained. Paste it as the whole task. The
companion brief is `docs/pm/brief-01-task-4-local-only-framing.md`; the engineer
does not need to open it, but `## Result` must be appended to it at the end.

---

You are the fullstack engineer on OmniAgent, a Windows repository at
`D:\code-project\OmniAgent`, git branch `main`, currently at `a455d99`.
Baseline: 631 tests passing, `mypy` strict clean over 41 files, `ruff` clean.

## Your task

One docstring in one file tells the reader to train on a hosted notebook. The
project's hardware manifest records an RTX 3050 Laptop GPU and the project's
first standard is "local only". Remove that framing from that one docstring and
add one test that keeps it out.

## Environment rules — these have each cost this project real time

1. **Always use the full interpreter path: `.venv\Scripts\python.exe`.** A bare
   `python` resolves to `.ci-venv` and silently tests the wrong environment.
2. **Never pass `-q` to pytest yourself.** `pyproject.toml:168` already sets
   `-q`; a second one makes it `-qq` and the `NNN passed` summary line vanishes
   entirely, so a grep for "passed" finds nothing while the run was green.
3. **`cmd.exe` reads `/` as a switch.** In `cmd`, write the path with
   backslashes. In PowerShell or bash either separator works.
4. **Never hand-edit `notebooks/train_omniagent_lora.ipynb`.** It is generated
   by `scripts\build_notebook.py`. An edit to the notebook alone disappears on
   the next regeneration.
5. **Put throwaway scripts outside the repository.** A file in the repo that
   quotes a held-out evaluation question fails a repository invariant.
6. Do not create a pull request, do not amend or rebase existing commits, do
   not switch branches, and do not touch the `core-offline-runtime` branch.

## What was already measured for you, 2026-10-23

A case-insensitive search for `colab` across the tracked tree returns exactly
five hits in four files. Four of the five are correct as they stand:

| File | Line | What it says | Verdict |
| --- | --- | --- | --- |
| `scripts/smoke_train.py` | 3 | "The notebook in ``notebooks/`` is meant for a Colab GPU and a real base model" | **this is your target** |
| `scripts/smoke_train.py` | 7 | "minutes into someone's Colab session" | **this is your target** |
| `scripts/build_notebook.py` | 37 | "**Why local rather than Colab.** The whole project runs on one rule: nothing…" | argues *for* local training — **do not touch** |
| `notebooks/train_omniagent_lora.ipynb` | 13 | the same sentence, generated from the line above | **do not touch** |
| `tests/test_notebook.py` | 92 | asserts the notebook imports no `google.colab`, `files.download`, `files.upload`, `drive.mount` | already guards the real risk — **do not touch** |

`README.md` contains no occurrence of the string at all. Do not modify it.

**`tests/test_local_only.py` does not exist yet. You create it.**

## Files you may touch

- Create: `tests/test_local_only.py`
- Modify: `scripts/smoke_train.py` — **the module docstring only**, lines 1–16

Nothing else. If you conclude another file must change, stop and write the
argument into `## Result` instead of changing it.

## Step 1 — write the failing test first

Create `tests/test_local_only.py` with one test. Use the repo's existing idiom
for locating the root, the same one in `tests/test_shipped_config.py:25`:

```python
REPO_ROOT = Path(__file__).resolve().parent.parent
```

The test asserts on `scripts/smoke_train.py` alone. Read it with
`encoding="utf-8"`. Give it a real name and a docstring that says why, for
example `test_smoke_train_does_not_point_the_reader_at_a_hosted_notebook`.
Full type annotations — `mypy` runs in strict mode.

Do not parametrize it over several files. A parametrized case with no mutation
check behind it is a case that proves nothing, and two of the four other files
above would make such a case fail for the wrong reason.

## Step 2 — run it and watch it fail

```
.venv\Scripts\python.exe -m pytest tests/test_local_only.py -v
```

**Paste the failing output verbatim into your report.** It must fail by naming
`scripts/smoke_train.py` and the offending text. A failure from an import
error, a missing file or a wrong path is not this test failing — fix that and
run again before continuing.

## Step 3 — rewrite the docstring

The current docstring, `scripts/smoke_train.py` lines 1–16, reads:

```
Run the whole fine-tuning pipeline on a CPU with a tiny model.

The notebook in ``notebooks/`` is meant for a Colab GPU and a real base model,
which cannot be exercised here. This script runs the same steps -- validate,
load, LoRA-train, merge, generate -- small enough to finish on a laptop, so
that an API change in transformers/trl/peft fails here rather than twenty
minutes into someone's Colab session.

It is a smoke test: it proves the pipeline executes, not that the model is any
good.

Usage::

    python scripts/smoke_train.py
    python scripts/smoke_train.py --dataset data/dataset.jsonl --epochs 1
```

**Facts it must keep saying**, because each is true and load-bearing:

- the script runs the whole pipeline on a CPU with a tiny model;
- the notebook needs a real GPU and a real base model, which a CPU cannot
  exercise — the contrast is with *hardware*, not with a hosting service;
- the steps are validate, load, LoRA-train, merge, generate;
- the reason it exists is to make a `transformers`/`trl`/`peft` API change fail
  here in seconds instead of twenty minutes into a real training run;
- it proves the pipeline executes, not that the model is any good.

**Facts it must stop saying:** that the notebook targets a hosted notebook
service, and that the twenty minutes are lost inside someone's hosted session.
The notebook targets the local GPU the manifest records.

Leave the `Usage::` block exactly as it is. Its bare `python` is a separate
issue that is not in this task's scope.

## Step 4 — the three mutation checks

Before each mutation, copy the file you are about to change into a scratch
directory **outside the repository**, and restore it from that copy afterwards.
Do not restore with `git checkout --` alone. Before each replacement, assert
the target string is actually present — a `sed` pattern containing `\n` matches
nothing silently, so a mutation can appear to pass without having mutated
anything.

| # | Mutation | Expected |
| --- | --- | --- |
| M1 | Put the word `Colab` back into the `scripts/smoke_train.py` docstring | **your new test goes red** |
| M2 | Replace your new test's body with `pass` | **it goes green** — this is how you know M1 was caught by your test and not by something else |
| M3 | Hand-insert `import google.colab` into `notebooks/train_omniagent_lora.ipynb` without regenerating it | **a test that is not yours goes red** |

For M1, report **every** test that turned red, not just yours. If more than one
did, say which is yours and which already covered it — a test asserting "this
is refused" proves nothing when several independent guards would refuse it.

For M3, name the test that caught it. The point is to establish that the
notebook is guarded by a test you did not write, so you are not claiming
coverage you did not add. Restore the notebook from your scratch copy.

## Step 5 — confirm the notebook is still in sync

You are not changing the notebook's generator, so this must be a no-op. Prove
it:

```
.venv\Scripts\python.exe scripts\build_notebook.py
git diff --stat notebooks/
```

`git diff` must report **no change**. If the notebook does change, the
committed notebook was already out of sync with its generator — stop, do not
commit, and report that instead. It is a real finding and a separate task.

## Step 6 — the three gates

```
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m pytest
```

All three must be green. Paste the `pytest` summary line. Expected: **632
passed** — 631 plus your one test. If the number is anything else, report the
actual number and say why; do not round it and do not describe it as "all
tests passing" without the count.

## Step 7 — commit

One commit, only after the gates are green:

```
git add scripts/smoke_train.py tests/test_local_only.py
git commit -m "docs: the notebook trains locally, which is what the manifest records"
```

**Do not run a bare `git push`.** This repository has two remotes and `main`
tracks the wrong one for this work. Leave the commit unpushed; the project
manager pushes it.

Do not use `git add -A` — it sweeps in whatever else is in the tree.

## Step 8 — report

Append a `## Result` section to
`docs/pm/brief-01-task-4-local-only-framing.md` containing:

1. the new test's name and the file it lives in;
2. the verbatim failing output from Step 2;
3. M1, M2 and M3 with, for each, which tests changed colour and their names;
4. the Step 5 `git diff --stat` result;
5. the `pytest` summary line and the ruff and mypy results;
6. the commit hash;
7. **anything you refuse to claim** — any step you could not verify, any number
   you did not measure yourself, any place you widened or narrowed the scope.

Commit that too. Then stop.

## The one thing that would make all of this wrong

Deleting the word `colab` wherever it appears. Two of its five occurrences are
the project explaining why it does **not** use a hosted notebook, and one is
the test that keeps `google.colab` out of the generated notebook. A repository
that satisfied `"colab" not in any file` would have thrown away its own
statement of the rule and the guard that enforces it — and all three gates
would still be green while it did so. The target is one docstring in one file.
