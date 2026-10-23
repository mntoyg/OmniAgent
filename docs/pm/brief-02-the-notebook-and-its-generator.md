# Brief 02 — the notebook and its generator must be provably the same file

Found while verifying brief 01. `docs/pm/brief-01-task-4-local-only-framing.md`
holds the discovery; this brief holds the fix.

The trap list's first entry says the notebook is generated and that editing it
alone is work that disappears. The repository has a test named for exactly that
failure. The failure happened anyway and the test stayed green.

## What is measured, 2026-10-23, on HEAD `a6cb131`

Running `.venv/Scripts/python.exe scripts/build_notebook.py` on a clean tree
produces `1 insertion(+), 24 deletions(-)` against the committed notebook.

| Difference | Count | What it is |
| --- | --- | --- |
| `"id": "<32 hex>",` removed | 24 | every cell. The committed notebook carries them; the generator emits none. |
| `"import json\n"` added | 1 | into the cell under "## 9. Checksum and manifest" |

### The four defects behind those 25 lines

1. **The generator emits an unused import.** `scripts/build_notebook.py:363`
   puts `import json` in the manifest cell. Nothing in that cell uses `json.`
   — the manifest is written by `run_dir.write_manifest` and the flat copy by
   `flat.write_text(manifest_path.read_text(...))`. `git show
   HEAD:notebooks/train_omniagent_lora.ipynb | grep -c 'json\.'` returns **0**.
   So the import was removed from the notebook alone, which is the trap, and it
   should not be in the generator either.

2. **`ruff` cannot see it.** The generator's own docstring claims writing the
   notebook as a script "lets the cell sources be linted like any other file".
   They are triple-quoted string literals, so no linter reads them. That is how
   an unused import entered and stayed. The docstring overstates what the
   design buys.

3. **The generator declares a schema version it does not satisfy.**
   `scripts/build_notebook.py:487` writes `"nbformat_minor": 5`. nbformat 4.5
   requires an `id` on every cell, and the generator emits none. The committed
   notebook has ids because Jupyter added them when the notebook was executed.
   The committed artifact is more correct than what its generator produces.

4. **`tests/test_notebook.py:264 test_the_notebook_and_its_generator_agree`
   cannot detect any of this, by construction.** It walks the six-entry
   `GENERATED_GUARANTEES` tuple and asserts each snippet appears in both files.
   A line the generator gained and the notebook never received is invisible,
   because no guarantee names that line. It is a substring expectation grading
   characters, not answers — and it is the guard named after this exact failure.
   `test_the_notebook_exists_and_is_valid_nbformat` overstates too: it checks
   `nbformat == 4`, that cells exist, that `cell_type` is in a set and that
   `source` is a list. It never looks at `nbformat_minor` or at `id`, and
   `nbformat` is not a dependency of this project.

## The ruling, with the cost of the alternative

**The generator is the source of truth for cell content. The notebook is a
build artifact that happens to be committed, and it must be byte-reproducible
from the generator.**

That requires the generator to emit cell ids, and **the ids must be
deterministic** — derived from the cell, not random — or every regeneration
churns 24 lines of diff and the comparison test becomes useless.

The alternative considered and rejected: drop `nbformat_minor` to `4`, where
ids are not required, and strip the 24 ids from the committed notebook. It is
the smaller change. **Its cost is that it does not hold.** The moment anyone
opens the notebook in Jupyter it gains ids and the minor version is bumped back
to 5, and the drift is back with a test that was just taught to expect no ids.
Deterministic ids survive that; absent ids do not.

## The blocker you must fix first

`scripts/build_notebook.py` **writes the notebook at import time.** Lines
490–491 are at module level with no `if __name__ == "__main__":` guard, and
`OUT` on line 12 is `Path("notebooks/train_omniagent_lora.ipynb")`, relative to
the current working directory rather than to the file.

So a test that imports the generator **overwrites the real notebook and then
compares the file to itself.** It would pass forever. This is the single way
this brief gets implemented wrongly, and it is also why the fix is a small
refactor and not just a new test.

## Files it may touch

- Modify: `scripts/build_notebook.py`
- Modify: `tests/test_notebook.py`
- Regenerate: `notebooks/train_omniagent_lora.ipynb`, by running the generator

Nothing else. Do not touch `scripts/smoke_train.py`, `tests/test_local_only.py`,
`omniagent.toml`, `README.md`, or anything under `docs/`. Do not add a
dependency — `nbformat` stays out. Standard 2 is no frameworks and the schema
check this needs is two assertions.

## Interfaces it must produce

In `scripts/build_notebook.py`:

```python
def build_notebook() -> dict[str, object]:
    """The notebook as a dict, with a deterministic id on every cell. No I/O."""

def cell_id(index: int, source: list[str]) -> str:
    """First 8 hex characters of sha256 of f"{index}:{''.join(source)}"."""
```

- `build_notebook()` performs **no file I/O** and returns the same dict every
  call. Calling it twice must produce equal dicts.
- `cell_id` takes the index as well as the source so two identical cells cannot
  collide. Eight hex characters satisfies the nbformat id pattern.
- `OUT` is resolved from `__file__`, not from the working directory, so the
  generator writes the same path wherever it is run from.
- The write, the `mkdir` and the `print` move under
  `if __name__ == "__main__":`. **Importing the module must touch no file.**
- Remove `import json` from the manifest cell's source text. Keep the
  generator's own `import json` at line 9 — `json.dumps` still writes the file.
- Correct the module docstring's claim about linting: the cell sources are
  string literals and no linter reads them.

## The tests that must fail first

Two, both in `tests/test_notebook.py`. Write them, run them, and **paste the
failing output** before changing the generator.

```python
def test_the_committed_notebook_is_what_the_generator_produces() -> None:
    """The notebook is a build artifact; drift means one file was edited alone."""

def test_the_generator_is_deterministic() -> None:
    """Two calls must agree, or the comparison above is noise."""
```

The first compares `build_notebook()` against
`json.loads(NOTEBOOK.read_text(encoding="utf-8"))` — **the whole dict, equality,
not a snippet list.** On failure the message must say which cell index differs.

Neither test may write to `notebooks/`, run the generator as a subprocess, or
use a temporary directory. Compare in memory. There is nothing to write.

**Replace `test_the_notebook_and_its_generator_agree` with the first of these.**
Delete it and delete `GENERATED_GUARANTEES`. It is not a weaker version of the
new test, it is a test that cannot fail for the reason it is named, and leaving
both means the next reader trusts the wrong one. If you disagree, argue it in
`## Result` and leave both rather than deleting.

Extend `test_the_notebook_exists_and_is_valid_nbformat` with two assertions:
`nbformat_minor == 5`, and every cell has a non-empty string `id`.

## Mutation checks that must go red

Copy each file to a scratch directory outside the repository before mutating,
restore from that copy, and assert the target string is present before
replacing it. Never `git checkout --` alone.

| # | Mutation | Must go red |
| --- | --- | --- |
| M1 | Change one character in any cell's source text in `scripts/build_notebook.py` | the comparison test |
| M2 | Change one character in a cell's source in `notebooks/train_omniagent_lora.ipynb`, the generator untouched | the comparison test |
| M3 | Make `cell_id` return `uuid4().hex[:8]` instead of the hash | the determinism test |
| M4 | Delete the comparison test's assert | **nothing** — it must go green, which is how you know M1 and M2 were caught by it |
| M5 | Put `import json` back into the manifest cell source and regenerate | the comparison test, because the committed notebook will not have it |

M1 and M2 are not the same check. M1 proves the test notices the generator
moving; M2 proves it notices the notebook moving. A test that only catches one
of them leaves the drift that actually happened undetected — it was the
notebook that was edited alone.

Report every test that turned red for each mutation, by name. If a mutation
turns more than one red, say which is yours.

## The three gates

```
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m pytest
```

Full path, and **no `-q` of your own** — `pyproject.toml:168` already sets it
and a second one deletes the summary line. Baseline is **632 passed**. You
remove one test and add two, so expect **633**. Report the actual number.

`mypy` runs in strict mode over 42 files and `build_notebook.py` is one of
them, so `build_notebook()` and `cell_id` need full annotations.

## The one thing that would make this wrong

**A test that regenerates the notebook on disk and then reads it back.** It
compares the file to itself and passes forever, and because the generator
writes at import time, even `import scripts.build_notebook` does it. If at any
point `git status` shows `notebooks/train_omniagent_lora.ipynb` modified while
you are only running tests, stop: the test is writing, and whatever it then
proved, it did not prove this.

The second way: deleting
`test_the_notebook_and_its_generator_agree` and replacing it with something
that also only checks snippets. The new test's value is that it is an equality
check over the whole document. If it has a list of things to look for in it, it
is the old test with a new name.

## Commit

One commit after the gates are green. The regenerated notebook goes in it — the
24 new deterministic ids and the removed import are the point.

```
git add scripts/build_notebook.py tests/test_notebook.py notebooks/train_omniagent_lora.ipynb
git commit -m "fix(notebook): the committed notebook is provably its generator's output"
```

Do not run a bare `git push` — this repository has two remotes and `main`
tracks the one this work does not belong to. Leave it unpushed.

## Result

<!-- Engineer: append here. The two failing outputs from before the fix, every
mutation with the names of the tests that changed colour, the three gate
results, the pytest count, the commit hash, and anything you refuse to claim. -->
