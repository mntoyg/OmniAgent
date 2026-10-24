# Brief 08 — the paste-ready task for the SWE

Paste everything below the line. The companion brief is
`docs/pm/brief-08-a-subject-that-exists-to-be-listed.md`; `## Result` goes
there.

---

You are the **SWE** on OmniAgent, `D:\code-project\OmniAgent`, branch `main`,
HEAD `b378093`. Baseline: **633 tests passing**, `ruff` clean, `mypy` strict
clean over 42 files.

**Read `docs/pm/brief-08-a-subject-that-exists-to-be-listed.md` and execute
it.** Your brief-07 investigation is why it exists: you established that no
directory in this repository is listable, unsealed, stable, uncontaminated and
present in a clean clone. The owner's decision is to build one.

## The constraint that has not relaxed

`tests/test_eval_workspace.py:157` fails if **any file the agent can reach**
holds a held-out question's text; `:175` does the same for an expectation.
`docs/` is reachable and `_DISTINCTIVE` is 12 characters.

The new question's text and expectation go into `scripts/holdout_eval.py` and
**nowhere else** — not in your report, not in a commit message, and above all
**not into a file inside the new directory**, which the agent can read by
design. Call it "the question at `scripts/holdout_eval.py:96`".

## Your task

Create **`eval-fixture/`** — five files and one subdirectory holding one file —
and point the question at it.

The hyphen is deliberate: it cannot be imported as a Python module. The name is
free and `.gitignore` does not match it. **Do not add `eval-fixture` to
`ANSWER_KEY`** — sealing it makes it invisible to `list_directory`, which is
exactly how `docs/` disqualified itself.

Every file's content must be **honest about what it is**: this ships in a public
repository, so each file says in its own words that the directory exists to give
the evaluation a subject whose listing does not change. No invented purpose, no
filler.

## Measured for you today — do not re-derive

- Only **4** tracked files can be read by a sealed agent **and** render intact:
  `tests/__init__.py` (78 rendered chars), `requirements.txt` (238),
  `tests/test_local_only.py` (924), `LICENSE` (1,262). 36 are denied or
  unreadable; 37 are too long.
- `MAX_INTACT_READ_CHARS` is **2,400** (`tools.py:474`), and the check is on the
  **rendered** text — a header plus a line number on every line, so many short
  lines inflate it fast.

So keep the fixture files small and this directory pays for itself twice: it
gives the evaluation a stable subject, and it raises the readable set that
`NEXT_CHAT.md` item 6 says `read_file` is starved of.

## Check the filenames against the dataset before committing them

"Uncontaminated by construction" is true of the **directory**, not of the names
you pick. A file called `dataset.jsonl` or `agent.py` collides with strings the
model has seen thousands of times. Run brief 07's scan over each name:

```python
import pathlib
base = pathlib.Path('G:/OmniAgent/datasets/2026-10-10-merged')
for f in sorted(base.glob('*.jsonl')):
    for line in f.read_text(encoding='utf-8', errors='ignore').splitlines():
        if line.strip() and '<your-filename>' in line:
            ...  # count it
```

2,215 examples across three files. **Report the count for every name you
keep.** A non-zero count gets the name changed, not explained.

## The question

Replace the question at `scripts/holdout_eval.py:96`, keeping
`prefer_tool="list_directory"` — it is still the only such question of the 19.

- **One right answer the agent cannot summarise away**, not "what is inside X".
  The old one failed because it needed the agent to volunteer one entry out of
  102, and `scripts/eval_scoring.py:88` grades `expect in answer` against the
  final answer only.
- The expectation must be **what makes the answer right**.
- **The answer must not change when a sixth file is added later.**

## What you verify — none of it needs a model

Paste every output.

1. `list_directory('eval-fixture')` under a **sealed** workspace
   (`sealed_workspace` from `scripts/eval_workspace.py`) returns exactly the
   entries you expect.
2. Every file returns content from `read_file`, not the "too long" error.
   Report each rendered length.
3. The listing is byte-identical **before and after a full `pytest` run**.
4. The contamination count for each filename.

| # | Mutation | Must go red |
| --- | --- | --- |
| Sa | put a plausible expectation string into one fixture file | `tests/test_eval_workspace.py:175`. Delete the string; do not commit it |
| Sb | add `"eval-fixture"` to `ANSWER_KEY` | the sealed listing stops naming the directory. Revert. Proves the subject works **because** it is unsealed |
| Sc | add a sixth file | the listing changes and **the expected answer does not** |

Sc is the design check. Sb is why `docs/` failed.

## Gates

```
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m pytest
```

Full path, **never your own `-q`**. Baseline **633 passed**. New reachable files
mean the invariants scan more of them; if the count moves, explain why.

## Files you may touch

`eval-fixture/**` (new) · `scripts/holdout_eval.py` · `README.md` — **one**
short line saying what the directory is, naming neither the question nor the
expectation.

## Files you may not touch

`tools.py` · `sandbox.py` · `scripts/eval_workspace.py` ·
`scripts/eval_scoring.py` · `scripts/collect_dataset.py` ·
`tests/test_eval_workspace.py` · `questions/**` · `models/**` · `data/**` ·
`omniagent-core/**` · `.github/workflows/**` · `NEXT_CHAT.md` · `.gitignore` ·
`docs/` except your `## Result` · anything on `core-offline-runtime`.

`tools.py` is in flight with the fullstack engineer. If a file is in neither
list, ask rather than decide.

## The split, stated up front

Your sandbox returns `WinError 10013` on `localhost` — confirmed twice on
2026-10-24 with Ollama up and answering for the manager. So:

- **You:** the directory, the filenames and their contamination counts, the
  question and expectation, Sa/Sb/Sc, the static checks, the gates, the commit.
- **The project manager:** the prediction written first, the answer-axis and
  tool-axis mutations, the add-a-file run, and the **ten runs** with variance.

**Do not report a measurement you did not produce.** Say plainly that the ten
runs are outstanding and whose they are.

## Commit

```
git add eval-fixture scripts/holdout_eval.py README.md
git commit -m "measure: a fixture directory the evaluation can list without measuring itself"
```

**Do not run a bare `git push`** — two remotes, and `main` tracks the one this
work does not belong to.

## The one thing that would make this wrong

Putting anything in the new directory that the agent should not read. It is
reachable by design — `list_directory` names it, `read_file` opens it,
`search_text` searches it. A stray expectation, a held-out question or a copied
answer key inside it hands the evaluation's answers to the model through the one
directory built to be looked at. **Sa exists so you watch that fail before you
trust it.**

The second way: a question whose answer changes when a sixth file arrives. That
is the old question with a new subject, and Sc catches it.
