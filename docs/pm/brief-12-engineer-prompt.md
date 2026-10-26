# Brief 12 — the paste-ready task for the fullstack engineer

Paste everything below the line. The companion brief is
`docs/pm/brief-12-a-record-that-refuses-to-pool.md`; `## Result` goes there.

---

You are the **fullstack engineer** on OmniAgent, `D:\code-project\OmniAgent`,
branch `main`, HEAD `888623a`. Baseline, re-run by the manager today: **642
tests passing**, `ruff` clean, `mypy` strict clean over 44 files.

**Read `docs/pm/brief-12-a-record-that-refuses-to-pool.md` and execute it.**
Two parts, two commits, a third for your report. **No model run is needed.**

**The security engineer is working in `sandbox.py`, `tools.py`,
`tests/test_sandbox.py`, `tests/test_search_text_pruning.py` and
`tests/test_tools.py` right now**, on brief 11. All five are forbidden to
you. Yours are `scripts/holdout_eval.py` and `tests/test_holdout_record.py`.
Run your gates from a clean tree and say which HEAD you were on; if the test
count moves for a reason that is not yours, say that too.

## Why this brief exists, in one measurement

`data/holdout-runs.jsonl` holds **209 records: 190 at `43aba72` and 19 at
`60183b8`.** The 19 are one run I made while the tree was dirty — brief 10's
Part 3 was uncommitted while it ran — and that run is **void**, recorded as
void in brief 10.

**Nothing in the file says so.** `scripts/session_eval.py:219 commit()` exists
so runs of different code are not pooled, and a dirty tree defeats it the same
way its own docstring describes. The file already contains the proof.

## Part 1 — the record says whether the tree was clean

Add a cleanliness field, taken from `git status --porcelain` the way
`commit()` takes the hash: fixed argv, no shell, a timeout, `"unknown"`
instead of an exception.

**`"unknown"` is not `True`.** It belongs with `commit` and `model`, at the
run level — **not inside `question_record()`**, which is pure and is tested
for carrying nothing but index, tools, steps and the six verdict booleans.
That purity test must keep passing before and after.

## Part 2 — `--report`, and what it refuses

`scripts/session_eval.py:287 report()` is the shape to follow;
`Spread.settled` at `:205` is the idea. `holdout_eval` has no equivalent, so
every reading of its file so far has been a throwaway script — mine, twice,
and the second one found a defect the first had not.

Per question index: how many runs, how many passed each axis, the step range,
whether it settled. And it **refuses**:

1. runs where the tree was not clean, **and runs where cleanliness is
   unknown** — dropped, not down-weighted, with a line saying how many and
   why;
2. pooling across commits — group by commit; one number over two commits is
   two numbers;
3. guessing. Every record in the file today predates Part 1 and has no field
   at all, so **the first run of `--report` must drop all 209 and say so.**
   If it prints a tidy table instead, the reader is wrong.

A question with no surviving runs is named as such. `0/0` printed as a result
is the defect this project keeps finding in its own instruments.

Build the tests over a temporary JSONL in `tmp_path`, the way
`tests/test_session_eval.py` does. **Do not write into `data/`** — it is
read-only for you.

## Mutations — restore from a scratchpad copy, never `git checkout --` alone

Ma treat `"unknown"` as clean · Mb pool two commits into one tally · **Mc put
the cleanliness field inside `question_record()`** · Md report a question
with zero surviving runs as `0/0`.

**Mc is the one to watch.** The purity test is the only thing between this
record and a run artifact the agent could read its own answers out of. It
passes today for free; Mc tells you whether it would still catch anything.

## Gates

```
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m pytest
```

Full path, **never your own `-q`**. Baseline **642 passed**, mypy clean over
**44** files.

## Commits

```
git add scripts/holdout_eval.py tests/
git commit -m "measure: a run record that says whether the tree was clean"

git add scripts/holdout_eval.py tests/
git commit -m "measure: a report that drops what it cannot trust, and says so"

git add docs/pm/brief-12-a-record-that-refuses-to-pool.md
git commit -m "docs: brief 12 result -- the record refuses to pool"
```

**Do not run a bare `git push`** — two remotes, and `main` tracks the one this
work does not belong to. Name it: `git push origin main`.

## The one thing that would make this wrong

**A reader that produces a number from the records it has rather than saying
what it could not use.** Every instrument defect found here this week was an
instrument reporting something where it should have reported nothing. The
first output of `--report` on today's file should be "209 records, 209
dropped, no cleanliness recorded". Anything tidier is the same defect rebuilt.
