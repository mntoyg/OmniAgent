# Brief 01 — Task 4: the hosted-notebook framing goes

Plan task: `docs/superpowers/plans/2026-10-06-train-and-deploy.md` §"Task 4: The
Colab framing goes". This is the last open task in that plan.

**Read this brief before the plan's Task 4 section. The plan's own file list and
test are wrong, and this brief narrows both. Measured below.**

## Goal

Nothing in the repository may tell a reader to train on a hosted notebook. The
manifest records an RTX 3050 Laptop GPU and standard 1 is local only.

## What was measured, 2026-10-23, on HEAD `85d137d`

A case-insensitive search for `colab` over the tracked tree (excluding `.venv`,
`.ci-venv`, `models/`, `data/`, `omniagent-core/`) returns exactly five hits in
four files:

| File | Line | Text | Verdict |
| --- | --- | --- | --- |
| `scripts/smoke_train.py` | 3 | "The notebook in ``notebooks/`` is meant for a Colab GPU and a real base model" | **contradicts the manifest — fix** |
| `scripts/smoke_train.py` | 7 | "minutes into someone's Colab session" | **contradicts the manifest — fix** |
| `scripts/build_notebook.py` | 37 | "**Why local rather than Colab.** The whole project runs on one rule: nothing" | **correct as written — keep** |
| `notebooks/train_omniagent_lora.ipynb` | 13 | the same sentence, generated from the line above | **correct as written — keep** |
| `tests/test_notebook.py` | 92 | asserts the notebook imports no `google.colab`, `files.download`, `files.upload`, `drive.mount` | **already guards the real risk — keep** |

`README.md` contains no occurrence of the string at all.

### Two corrections to the plan

1. **The plan lists `README.md` and `scripts/build_notebook.py` as files to
   modify. Neither should change.** `README.md` has nothing to change.
   `build_notebook.py:37` is a sentence that *argues for* local training; the
   generated notebook carries it. Deleting it removes a true statement and
   weakens the document that explains the rule.
2. **The plan's test is `assert "colab" not in path.read_text().lower()`
   parametrized over three paths. That assertion is wrong for two of the three
   and vacuous for one.** It would pass on `README.md` because the string was
   never there, and it would force the deletion of correct prose from
   `build_notebook.py`. A substring expectation grades characters, not answers.

## Files you may touch

- Modify: `scripts/smoke_train.py` (module docstring only)
- **Create**: `tests/test_local_only.py` — measured 2026-10-23, the file does
  not exist. The plan's Task 4 lists it under "Test:" as though it did.
- Regenerate: `notebooks/train_omniagent_lora.ipynb` — **only** via
  `.venv/Scripts/python.exe scripts/build_notebook.py`. Editing the notebook by
  hand is work that disappears on the next regeneration.

Do not touch `README.md`, `scripts/build_notebook.py`, `tests/test_notebook.py`,
or `omniagent.toml`. If you believe one of them must change, append the argument
to `## Result` and stop rather than changing it.

## Interfaces it must produce

No new interfaces. One new test function in `tests/test_local_only.py`:

```python
def test_smoke_train_does_not_point_the_reader_at_a_hosted_notebook() -> None:
    """The manifest records an RTX 3050 Laptop GPU; standard 1 is local only."""
```

It asserts on `scripts/smoke_train.py` alone. If you want the guard to cover
more than one file, each file needs its own mutation check below — a
parametrized case with no mutation behind it is a case that proves nothing.

## The test that must fail first

1. Write the test above.
2. Run `.venv/Scripts/python.exe -m pytest tests/test_local_only.py -v` with
   **no `-q` of your own** (`pyproject.toml:168` already sets it; a second `-q`
   deletes the summary line).
3. Paste the failing output into `## Result`. It must name
   `scripts/smoke_train.py` and the offending text. A failure for any other
   reason — import error, missing file, wrong path — is not this test failing.

Then rewrite the docstring and watch it go green. Keep what the docstring says
about catching a `transformers`/`trl`/`peft` API change before a twenty-minute
run; that is the reason the script exists and it is true.

## Mutation checks that must go red

Copy the file to the scratchpad first and restore from that copy. Never
`git checkout --` alone. Before each replacement, assert the target string is
present — a `sed` pattern containing `\n` matches nothing silently, so a
mutation can "pass" without having mutated anything.

| # | Mutation | Must go red |
| --- | --- | --- |
| M1 | Put `Colab` back into the `scripts/smoke_train.py` docstring | the new test |
| M2 | Delete the new test's assert (replace the body with `pass`) | nothing — record that it goes green, which is how you know M1 is the test and not something else |
| M3 | Hand-edit `notebooks/train_omniagent_lora.ipynb` to insert `import google.colab`, without regenerating | `tests/test_notebook.py` |

M3 exists for one reason: to establish that the notebook is guarded by a test
that is not yours, so you are not claiming coverage you did not add. State in
`## Result` which test caught it, by name.

**A test asserting "this is refused" proves nothing if several independent
guards would refuse it.** If M1 turns more than one test red, name every one of
them in `## Result` and say which of them is yours.

## The three gates, before the commit

```
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy
.venv/Scripts/python.exe -m pytest
```

Full path every time — a bare `python` picks up `.ci-venv`. Paste the `pytest`
summary line. Baseline to beat: **631 passed**, mypy strict clean over 41 files,
ruff clean. The new test makes it 632. If the count is anything else, say so
rather than rounding it.

## The one thing that would make this wrong

Deleting the word `colab` everywhere it appears. Two of the five occurrences are
the project explaining why it does *not* use a hosted notebook, and one is a
test that keeps `google.colab` out of the generated notebook. A repository that
passes `"colab" not in any file` would have lost its own explanation of the rule
and the guard that enforces it. The target is one docstring in one file.

The second way: editing `notebooks/train_omniagent_lora.ipynb` directly. It is
generated by `scripts/build_notebook.py`. Edit the generator or nothing.

## Commit

One commit, after the gates are green:

```
docs: the notebook trains locally, which is what the manifest records
```

Then check the plan's Task 4 steps off in
`docs/superpowers/plans/2026-10-06-train-and-deploy.md` and note in the plan
that Steps 1 and 3 were narrowed by this brief, with the reason.

## Result

<!-- Engineer: append here. What landed, what was measured, what you refuse to
claim. Quote the failing test output, each mutation's result, and the pytest
summary line. If you changed scope, say what and why. -->
