# Brief 07 — the paste-ready task for the SWE

Paste everything below the line. The companion brief is
`docs/pm/brief-07-a-metric-that-does-not-move.md`; `## Result` goes there.

---

You are the **SWE** on OmniAgent, `D:\code-project\OmniAgent`,
branch `main`, HEAD `cca7c6a`. Baseline: **633 tests passing**, `ruff` clean,
`mypy` strict clean over 42 files.

**Read `docs/pm/brief-07-a-metric-that-does-not-move.md` and execute it.**

## Before anything: this task cannot quote its own subject

`tests/test_eval_workspace.py:157` fails if **any file the agent can reach**
holds a held-out question's text, and `:175` does the same for an expected
answer. `docs/` is reachable. `_DISTINCTIVE` is 12 characters.

**The new question text and the new expectation belong in
`scripts/holdout_eval.py` and nowhere else.** Not in your report, not in a
commit message, not in a scratch file left inside the repository. Refer to it
as "the question at `scripts/holdout_eval.py:96`". A file that leaks either one
turns the green suite red — and that is the invariant working, not a bug to
route around.

## Your task

The question at `scripts/holdout_eval.py:96` has `prefer_tool="list_directory"`
and its subject is `data/`, the directory every evaluation run writes into.
Rebuild it against a subject that does not move.

## What is already measured, 2026-10-24 — do not re-derive

- `data/` holds **101** files today; the notes recorded 85 on 2026-10-11.
- `list_directory` on that subject returns **3,742 characters over 102 lines**.
- The expected string **is still in the tool output**. It is missing from the
  **answer** — and `scripts/eval_scoring.py:88` grades
  `question.expect in answer.replace(",", "")`, the final answer only.
- So the question requires the agent to relay one arbitrary entry out of 102
  into its reply. Summarising a 102-entry listing, which is the sensible reply,
  is graded WRONG while being right, and it gets worse every run.
- Parsed with `ast`: **19 `Question` objects, 1 unanswerable**; `prefer_tool` is
  `None` ×12, `file_info` ×5, `search_text` ×1, **`list_directory` ×1 — this
  one**. Retiring it takes `list_directory` coverage to **zero**, which is why
  the decision is rebuild.

## Step 0 — report your capability before building anything

Verification needs **ten holdout-evaluation runs against Ollama on
`localhost:11434`**. Establish you can do that first:

1. Ollama does not autostart but may already be up:
   `.venv\Scripts\python.exe -c "import httpx;print(httpx.get('http://localhost:11434/api/tags').status_code)"`
   To start it, PowerShell:
   `Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" -ArgumentList "serve" -WindowStyle Hidden`,
   then wait ~15 s. `&` from bash does not work.
2. Run the evaluation for **one** session and report what came back.

**If you cannot, stop and say so.** The brief then splits — you design the
replacement, the project manager runs the ten. That is planned, not a failure.
Do not work around it and do not report numbers you did not produce.

## Choosing the subject

It must be a directory **nothing the evaluation or the test suite writes into**.
`data/` is disqualified. `scripts/` is recorded contaminated
(`NEXT_CHAT.md:221`, listings 33× and 14× in the dataset). `tests/` gains a
`__pycache__` that `list_directory` can see. `docs/` has 17 tracked files and
nothing writes there. Tracked counts are not listings.

**Verify stability:** the candidate's listing must be byte-identical before and
after a full `pytest` run and after one evaluation run. A subject that moves
under either is `data/` with a different name.

**Run the contamination check** against `G:/OmniAgent/datasets/2026-10-10-merged/`
(153 examples, present and readable): search the collected `.jsonl` for listings
of your candidate and its distinctive entries. If the model was trained on that
listing, the question measures recall, not tool use. No script exists — write
down the command you used so the next person repeats it instead of inventing a
third one.

## Designing the expectation

Prefer a question with **one** right answer the agent cannot summarise away over
"what is inside X". The expectation must be what makes the answer right, not a
string that merely co-occurs with it. Keep `prefer_tool="list_directory"` —
restoring that coverage is the point. Read
`tests/test_eval_workspace.py:199` and `:219` first; they encode two earlier
mistakes about expectations and subjects.

## Ten runs, not three

Three runs have twice produced a conclusion that ten reversed.

- **Write the prediction before the first run.**
- **Never two model runs at once** — the card is 4 GB.
- **A command over 600 s is backgrounded and dies with the session.** A full
  holdout run measured 544 s. Start each in the background on purpose.
- **Redirect evaluation output to `data/`** — it prints and keeps nothing, and
  `data/` is gitignored.
- Report all ten results and the variance, not a mean.

## Mutations — scratch copies outside the repo, restore from them

| # | Mutation | Must go red |
| --- | --- | --- |
| M1 | expectation changed to something the right answer lacks | the question scores WRONG |
| M2 | `prefer_tool` changed to a tool that cannot answer it | the tool-choice axis; say whether the answer axis stayed green |
| M3 | **add a file to the new subject directory** | **the score must not move** |
| M4 | put the new expectation in a reachable file under `docs/` | `tests/test_eval_workspace.py:175` goes red. Delete that file; do not commit it |

M3 is the whole brief. M4 proves you understand why this task cannot quote
itself.

## Gates

```
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m pytest
```

Full path, **never your own `-q`**. Baseline **633 passed**. If the count moves,
explain why rather than accepting it.

## Files you may touch

`scripts/holdout_eval.py` · `tests/test_eval_workspace.py` only if an invariant
must learn the new subject, and say so if you touch it.

## Files you may not touch

`tools.py` · `sandbox.py` · `scripts/eval_scoring.py` ·
`scripts/collect_dataset.py` · `questions/**` · `models/**` ·
`omniagent-core/**` · `.github/workflows/**` · `NEXT_CHAT.md` · `docs/` except
your `## Result` · anything on the `core-offline-runtime` branch.

**`tools.py` is in flight with the fullstack engineer.** Do not edit it, and do
not change tool behaviour to make a question easier. If a file is in neither
list, ask rather than decide.

## Commit

```
git add scripts/holdout_eval.py
git commit -m "measure: the list_directory question no longer asks about a directory we write to"
```

Add the test file only if you changed it, and say why. **Do not run a bare
`git push`** — two remotes, and `main` tracks the one this work does not belong
to.

## The one thing that would make this wrong

Replacing one unstable subject with another. `data/` failed because the
evaluation writes into it; a subject pytest writes into, or that gains a
`__pycache__`, or whose listing differs between a clean clone and this working
tree, fails the same way on a longer fuse — and the next person finds it the
way this one was found, from a score that drifted. **M3 catches that before it
ships.**

The second way: making the expectation easy enough to always pass. A question
that cannot be failed measures nothing, exactly like the test replaced in
brief 02.
