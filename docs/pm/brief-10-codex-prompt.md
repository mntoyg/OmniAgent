# Brief 10 — the paste-ready task for the SWE

Paste everything below the line. The companion brief is
`docs/pm/brief-10-no-question-is-scored-on-nothing.md`; `## Result` goes there.

---

You are the **SWE** on OmniAgent, `D:\code-project\OmniAgent`, branch `main`,
HEAD `dbfc39e`. Baseline, re-run by the manager today: **636 tests passing**,
`ruff` clean, `mypy` strict clean over 43 files, working tree clean.

**Read `docs/pm/brief-10-no-question-is-scored-on-nothing.md` and execute it.**
It has three parts, three commits, and a fourth commit for your report.

**No part of this brief needs a model run.** Your sandbox returns
`WinError 10013` on `localhost` and nothing here touches it — the retro-scoring
reads ten log files already on your disk.

## Why this brief exists, in one measurement

Of the 19 questions in the bank at `scripts/holdout_eval.py:52`, one is scored
on tool choice alone and one is scored on nothing at all. Read out of the ten
recorded runs behind the current 11/16 baseline:

- the comparison at `scripts/holdout_eval.py:77` — **right in 10 of 10 runs**,
  and every time in 7 steps with 6 tool calls, three of them `read_file`.
  Scored `TOOL OK`; the answer axis never saw it.
- the follow-up at `scripts/holdout_eval.py:122` — **right in 0 of 10 runs**,
  printed as `no check` every time. Six runs ran out of steps; three invented
  a tool failure for files it had already read; one named the right file with
  the arithmetic off by one. **8 or 9 steps in all ten.**

So the instrument reports 11/16 while one question it does not score fails
deterministically and another passes for the wrong reason.

## The three parts

1. **`Expectation(all_of, none_of)` in `scripts/eval_scoring.py`**, plus
   `expected_strings()` so the leak invariant at
   `tests/test_eval_workspace.py:105` keeps covering expectations it can no
   longer measure with `len()`. A bare `str` must behave exactly as today.
   Then rewrite the two comparison questions so each **states the shape of
   answer it is graded on**, with the winner computed at import time from
   `_lines()` and never written down.
2. **Retire the `'budget'` question** at `scripts/holdout_eval.py:91` and
   `scripts/session_eval.py:84` — its expectation sits in five reachable files
   and its subject file argues against the answer in three places
   (`agent.py:194`, `:370`, `:612`). Replace it with a `search_text` question
   over **one new file in `eval-fixture/`**: marker in exactly one reachable
   file, expectation (the subject's filename) in zero, both ≥ 12 characters,
   contamination count zero against the 2,215 training examples.
3. **One JSONL record per question** from `holdout_eval`, into
   `data/holdout-runs.jsonl`, tagged with the short commit. Index, tools,
   steps, verdict booleans — **never the question text and never an
   expectation.** Built by a pure function and tested directly; do not add a
   client parameter to `evaluate()`.

## Before any new behaviour, the test that asserts the defect must die

`tests/test_holdout_questions.py:29` is
`test_only_the_comparisons_are_scored_on_tool_choice_alone`. It pins today's
defect in place. **Delete it and replace it with its opposite** — no question
is scored on tool choice alone — and watch the new one fail first.

## Retro-score the ten logs — the result this brief is really for

Score the recorded answers in `data/holdout-run01.log` … `run10.log` against
your new rules, offline, before anything is run again. Report both figures.
Then say what it does **not** tell us: those answers were given to the old
question text, so it measures the rule and not the rewritten question. **It is
not a prediction of the new baseline.**

## Mutations — restore from a scratchpad copy, never `git checkout --` alone

Ma drop `none_of` from the condition · Mb swap winner and loser and report
both retro-scores · Mc make `expected_strings` return `()` and check the leak
invariant goes red · Md put the marker in a second fixture file · Me write the
new expectation into a fixture file's contents, then delete it · Mf add a
seventh file to `eval-fixture/` and confirm brief 08's listing expectation does
**not** move · Mg put a question text into the Part 3 record.

**Md, Me and Mf need files the lists below otherwise forbid, and that is
permitted for the mutation only.** Md and Mf create a throwaway file under
`eval-fixture/` and delete it before any commit; Me edits **your new subject
file**, never one of the six already there, and restores it from the
scratchpad copy. Nothing from a mutation reaches a commit.

**Mc is the one to take seriously.** An invariant that passes because it
iterates an empty tuple is worse than no invariant: the figures quoted from it
read as checked. If Mc stays green, that is a finding to report, not to work
around.

## Files you may touch

`scripts/eval_scoring.py` · `scripts/holdout_eval.py` ·
`scripts/session_eval.py` · `tests/test_eval_scoring.py` ·
`tests/test_holdout_questions.py` · `tests/test_eval_workspace.py` ·
`tests/test_session_eval.py` (only if Part 2 breaks it) · a new test file if
you want one · **one** new file under `eval-fixture/` (no subdirectory) ·
`.gitignore` only if `data/holdout-runs.jsonl` is not already covered.

## Files you may not touch

`agent.py` · `tools.py` · `sandbox.py` · `scripts/eval_workspace.py` ·
`scripts/collect_dataset.py` · `scripts/build_notebook.py` · `README.md` ·
`questions/**` · `models/**` · `omniagent-core/**` · `.github/workflows/**` ·
`NEXT_CHAT.md` · `docs/` except your `## Result` · the six existing files under
`eval-fixture/` · anything on `core-offline-runtime`.

`data/**` is **read-only**: read the ten logs, write nothing into it by hand.

Every mutation above is inside the touchable set. If a file is in neither
list, ask rather than decide.

## Quoting

`docs` is in `ANSWER_KEY`, so this file is sealed and quoting a question here
would not fail the invariant — briefs 07 and 08 said otherwise and were wrong.
Keep the discipline as defence in depth: in your `## Result`, refer to
questions by line number and **do not quote the new marker, the new filename,
or any question text.**

The rule that a test does enforce: **nothing goes into `eval-fixture/` except
the one new subject file.** That directory is reachable by design.

## Gates

```
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m pytest
```

Full path, **never your own `-q`**. Baseline **636 passed**, mypy clean over
43 files. This brief adds tests and one reachable file, so both move — say
what to, and why. A move you cannot explain is a finding.

## The split

- **You:** all three parts, the tests, Ma–Mg, the retro-score, the gates, the
  four commits.
- **The project manager:** the prediction written before any run, the ten new
  runs with variance, the new baseline, and whether the comparisons move the
  score for the model's reasons or the instrument's.

**Do not report a measurement you did not produce.** Say plainly in
`## Result` that the ten runs are outstanding and are the manager's.

## Commits

Three commits for the work, gates green at each, then a fourth for the report:

```
git add scripts/eval_scoring.py tests/test_eval_scoring.py scripts/holdout_eval.py tests/test_holdout_questions.py tests/test_eval_workspace.py
git commit -m "eval: grade a comparison with a rule, not a substring"

git add eval-fixture scripts/holdout_eval.py scripts/session_eval.py tests/test_eval_workspace.py tests/test_session_eval.py
git commit -m "eval: a search subject whose answer is only in the subject"

git add scripts/holdout_eval.py tests/ .gitignore
git commit -m "measure: one record per question, so a derailment can be scored later"

git add docs/pm/brief-10-no-question-is-scored-on-nothing.md
git commit -m "docs: brief 10 result -- the instrument no longer scores a question on nothing"
```

**Do not run a bare `git push`** — two remotes, and `main` tracks the one this
work does not belong to. Name it: `git push origin main`.

## The one thing that would make this wrong

**A rule that grades phrasing instead of answers.** A `none_of` list tuned
until the ten recorded answers come out right is the old mistake with more
machinery. Each comparison question **says** what shape of answer it is graded
on, and the rule checks exactly that. If you are adding a third `none_of`
string to make a recorded answer pass, stop and report it: the question is
wrong, not the rule.
