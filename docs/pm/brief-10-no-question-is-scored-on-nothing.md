# Brief 10 — no question is scored on nothing

> **ON HOLD, 2026-10-26, and not to be pasted yet.** Writing the prediction at
> the end of this file found a defect in **Part 1** of this brief: the rule it
> specifies grades a comparison and instruction-following as one bit, which is
> the thing `scripts/holdout_eval.py:7-12` says not to do. The fork is at
> **"A defect in this brief, found by writing the prediction"** below and is
> with the owner. Parts 2 and 3 are unaffected.

**For the SWE.** Design and static verification only; the measurement half is
the manager's and is named at the bottom. **No model run is needed for any
part of this brief** — including the retro-scoring in Part 1, which reads logs
that are already on disk.

Two items on the open list are the same defect seen twice: **a question whose
right answer is not a substring is graded on a weaker axis, and a weaker axis
reads as "not wrong".** They live in the same three files and they both move
the denominator, so they are one brief and one re-measure rather than two.

## What is measured, 2026-10-26, on HEAD `dbfc39e`

Gates re-run by the manager before writing this: ruff clean, mypy clean over
**43** files, **636 passed**. Working tree clean.

The bank at `scripts/holdout_eval.py:52`:

| Fact | Value |
| --- | --- |
| questions | **19** |
| scored on an answer (`expect` set) | **16** — this is the 11/16 denominator |
| scored on tool choice | 7 |
| scored on honesty | 1 |
| **scored on tool choice alone** | **1** — `scripts/holdout_eval.py:77` |
| **scored on nothing at all** | **1** — `scripts/holdout_eval.py:122`, which prints `no check` |
| reachable files under the seal | **309** (308 in the notes plus `tests/test_search_text_pruning.py`, added in `0c04ffa`) |

### What those two questions actually did, in all ten recorded runs

Read out of `data/holdout-run01.log` … `run10.log` — the ten runs behind the
current baseline. **This is the evidence the brief rests on; do not re-derive
it, but do not trust it either: the logs are on your disk and you can check
any line of it.**

The comparison at `:77` — **answered correctly in 10 runs out of 10**, every
time in the same words, and every time in **7 steps with 6 tool calls**
including three `read_file`s and a `search_text` it had no use for. Scored
`TOOL OK`. The answer axis never saw it.

The follow-up at `:122` — **answered correctly in 0 runs out of 10**, and
scored `no check` in all ten:

| What it answered | Runs |
| --- | --- |
| "I ran out of reasoning steps before reaching an answer." | 6 |
| "I am unable to answer this question as it requires a tool that cannot locate the files mentioned in the question." — a false hedge; both files exist and it had already read one of them | 3 |
| the right file, by the wrong arithmetic: it reported a difference of 391 where the two counts differ by 390 | 1 |

**8 or 9 steps in every one of the ten runs.** This is the derailment the open
list calls a defect in the instrument, and it is worse than "hidden": three of
the ten runs are the agent inventing a tool failure, which is the exact
behaviour the honesty axis exists to catch, landing on a question that has no
honesty axis.

So the instrument currently reports 11/16 while **one question it does not
score is failing deterministically and another is passing for the wrong
reason.**

### Why the second item is the same defect

`agent.budget.exhausted` is the expectation at `scripts/holdout_eval.py:91`
and `scripts/session_eval.py:84`. Measured:

- the string occurs in **five** reachable files, recorded in
  `EXPECTATION_CARRIERS` at `tests/test_eval_workspace.py:60` and asserted by
  `test_the_budget_expectation_is_not_unique_to_its_subject`. A `search_text`
  over `.` returns four files that are not the question's subject.
- the subject itself argues against the answer. `agent.py:194-195` records, in
  prose, that the model "answered that the word 'budget' is not used anywhere
  in the file". `agent.py:370` contains a quoted sentence beginning "I have
  found where 'budget' is used in agent.py". `agent.py:612-618` records both
  fine-tunes reading one file nine times on a comparison question.

A question whose subject file contains both a denial of the answer and a
transcript of a previous wrong attempt is not measuring retrieval. It is the
same class as brief 07's listing subject: **the subject has to be replaced,
not the expectation repaired.**

## Goal

Three changes to the instrument, after which **no question in either
evaluation is scored on tool choice alone or on nothing**, and every
expectation is uniquely located in the file the question is about.

---

# Part 1 — an expectation that can grade more than one substring

## The interface

In `scripts/eval_scoring.py`:

```python
@dataclass(frozen=True)
class Expectation:
    """Several substrings at once, because one cannot grade a comparison."""

    all_of: tuple[str, ...] = ()
    none_of: tuple[str, ...] = ()
```

- `Question.expect` becomes `str | Expectation | None`. A bare `str` keeps
  behaving exactly as it does today, which is `Expectation(all_of=(s,))`.
- `judge()` strips commas from the **answer** and from nothing else, as it
  does now — the question bank writes `1116` and the model writes `1,116`.
- `correct` is true when every string in `all_of` is present and no string in
  `none_of` is.
- A failing mark must name which half failed. `ANSWER WRONG` with no detail
  turns a diagnosis into a re-run.

Also in `scripts/eval_scoring.py`, and it is **not optional**:

```python
def expected_strings(expect: str | Expectation | None) -> tuple[str, ...]:
    """Every string that makes an answer right, for the leak invariant."""
```

`tests/test_eval_workspace.py:105` enumerates expectations with
`len(question.expect)`, which is a `TypeError` on the new type and, worse,
would quietly stop covering the new strings if someone "fixed" it with a
`getattr`. It must go through `expected_strings` instead. **The seal has
already moved a leak once rather than closing it** (`tests/test_eval_workspace.py:100-104`);
this is the same shape.

`expected_strings` returns **`all_of` only**. A `none_of` string is not an
answer — it is the wrong file's name — and treating it as one would make
`README.md` an unreviewed carrier for no reason. Say that in the docstring,
because the next reader will ask.

## The two comparisons

Neither can be graded as it is written, and the reason is not the scorer: a
comparison's answer names **both** files. Measured above —
`tests/test_sandbox.py has more lines than tests/test_config.py` is a right
answer containing the loser's name. So `none_of=(loser,)` would grade a right
answer wrong **unless the question says what shape of answer it wants.**

Therefore each comparison question's text must state the answer shape it will
be graded on, and the rule must match that statement. One sentence, no more.
Keep `prefer_tool="file_info"` on `:77`.

**The winner and the loser are computed at import time from `_lines()`, never
written down.** `scripts/holdout_eval.py:39` already exists for this and its
docstring says why: a hardcoded count is wrong the moment the file is edited,
and the figure then falls for a reason that is not the model. If someone later
adds 200 lines to the shorter file, the expectation must flip by itself.

Measured today, so you can check your import-time computation against it:

| File | Lines |
| --- | --- |
| `tests/test_config.py` | 354 |
| `tests/test_sandbox.py` | 539 |
| `tests/fakes.py` | 122 |
| `scripts/build_notebook.py` | 512 |

And measured under the seal, so you know these are clean expectations:
`tests/test_sandbox.py`, `tests/test_config.py` and `scripts/build_notebook.py`
each occur in **0** reachable files. `tests/fakes.py` occurs in **1** —
`README.md`. That is the one that would need a carrier entry if it ever became
an `all_of` string. Under the rule above it is a `none_of` string, so it does
not. **Check this yourself rather than taking it from me; it is the kind of
fact that moves.**

## Retro-score the ten recorded runs — the static result this brief exists for

Before any new run, score the **recorded answers** in
`data/holdout-run01.log` … `run10.log` with the new rules, offline. A short
throwaway script is fine; it does not ship.

Report, for each of the two comparison questions, what the new rule scores
over the ten recorded answers. Then state plainly what it does **not** tell
us: those answers were given to the **old** question text, so the retro-score
measures the rule, not the rewritten question. It is an upper bound on nothing
and a check that the rule separates "names the longer file" from "I ran out of
reasoning steps". **Do not present it as a prediction of the new baseline.**

## Tests that must fail first

| Test | Where | Must fail before, pass after |
| --- | --- | --- |
| `judge` grades an `Expectation` with two `all_of` strings | `tests/test_eval_scoring.py` | new behaviour |
| `judge` fails an answer containing a `none_of` string | `tests/test_eval_scoring.py` | new behaviour |
| a bare `str` expectation is unchanged | `tests/test_eval_scoring.py` | regression guard — must pass **before and after** |
| `expected_strings` returns every `all_of` string and no `none_of` string | `tests/test_eval_scoring.py` | new behaviour |
| **no question is scored on tool choice alone** | `tests/test_holdout_questions.py` | replaces `test_only_the_comparisons_are_scored_on_tool_choice_alone` at `:29`, which asserts today's defect and must be **deleted, not weakened** |
| no expectation string contains a comma | `tests/test_holdout_questions.py:49` | generalise it through `expected_strings` |

---

# Part 2 — a search subject that is only about itself

Retire the question at `scripts/holdout_eval.py:91` **and** the identical one
at `scripts/session_eval.py:84`. Both go, or the next drift measurement runs a
question we have declared unfit.

Replace it with a `search_text` question over a **new file in
`eval-fixture/`** holding one distinctive marker.

Requirements, all of them measurable without a model:

1. **The marker occurs in exactly one reachable file** — the new subject.
   Measure it with `reachable_files()` from `tests/test_eval_workspace.py`,
   not with `grep` over the working tree: the tree is not what the agent sees.
   One carrier, against the five the old question had.
2. **The expectation occurs in zero reachable files.** Make the expectation
   the subject's own filename, so what makes the answer right is *which file
   the marker is in* — the thing a search tool is for. Verify that the
   filename string appears in no file's contents, including `README.md`. If it
   does, change the name rather than adding a carrier entry.
3. **Both are at least 12 characters.** Below `_DISTINCTIVE`
   (`tests/test_eval_workspace.py:77`) the leak invariant does not cover them,
   and an uncovered expectation is one that can be leaked back in later.
4. **Contamination count zero**, by brief 07's scan over the three `.jsonl`
   files at `G:/OmniAgent/datasets/2026-10-10-merged/` — 2,215 examples.
   Report the count for the marker and for the filename. **A non-zero count
   gets changed, not explained.**
5. **The new file is honest about what it is**, like the six already in that
   directory. This is a public repository. It says in its own words that it
   exists to give the evaluation a subject whose contents do not move. No
   filler, no invented purpose.
6. **It renders intact** under `MAX_INTACT_READ_CHARS` (`tools.py:474`,
   2,400 on the rendered text, which carries a header and a line number per
   line). The six existing files render at 173–202 characters; stay in that
   range.
7. **`eval-fixture` stays out of `ANSWER_KEY`.** Sealing it is how `docs/`
   disqualified itself as a subject.

**Keep `EXPECTATION_CARRIERS["agent.budget.exhausted"]` and
`test_the_budget_expectation_is_not_unique_to_its_subject`.** The log event
still exists and the five-carrier spread is a measured fact about this
codebase, not a fact about a question. Retiring the question does not make the
record false. Say in a comment that the entry now documents the codebase
rather than guarding a live expectation.

## Tests that must fail first

| Test | Where | Must fail before, pass after |
| --- | --- | --- |
| the new marker has exactly one reachable carrier | `tests/test_eval_workspace.py` | new behaviour |
| the new expectation has zero reachable carriers | `tests/test_eval_workspace.py` | new behaviour |

Write these as assertions over `reachable_files()`, in the same style as the
tests already there: assert the property, not a hand-written list of files.

---

# Part 3 — record the steps now so the derailment axis needs no new runs

`scripts/session_eval.py` already keeps `Outcome.steps` per question.
`scripts/holdout_eval.py` keeps only a total, so the per-question step counts
behind the table above had to be scraped out of printed logs.

Add a per-question record to `holdout_eval`, appended to
`data/holdout-runs.jsonl` — gitignored, beside `data/session-runs.jsonl`, and
tagged with the short commit the way `session_eval.commit()` does, so runs of
different code are not pooled.

**Each record carries the question's index, the tools called in order, the
step count, and the verdict's booleans. It carries neither the question text
nor any expectation.** Two reasons, and the second is the one that matters:
the agent must not be able to read its own answer key out of a run artifact —
that is the leak `scripts/eval_workspace.py` exists to close — and an index is
enough to join back to the bank.

Keep it testable without a model: build the record in a **pure function** that
takes the index, the verdict, the step count and the tool list and returns a
`dict`, and test that function directly. **Do not add a client parameter to
`evaluate()` for this.** A pure function is why `eval_scoring.py` can be
checked in milliseconds instead of minutes.

Measure and report whether `data/holdout-runs.jsonl` is reachable under the
seal. `data` is in `LISTING_ONLY`, so the expected answer is no — but it is
the kind of thing that has been wrong before, and the record carries no
secrets either way.

## Test that must fail first

| Test | Where |
| --- | --- |
| the record holds index, tools, steps and verdict booleans, and holds neither question text nor expectation | `tests/test_holdout_questions.py` or a new `tests/test_holdout_record.py` — your call |

---

# Mutations that must go red

Restore from a scratchpad copy, **never `git checkout --` alone**.

**Md, Me and Mf need files this brief otherwise forbids, and that is
permitted for the mutation only.** Md and Mf create a throwaway file under
`eval-fixture/` and delete it before any commit. Me edits **your new subject
file**, not one of the six that were already there, and restores it from the
scratchpad copy. Nothing from a mutation reaches a commit. Three of my briefs
have put a mutation behind a forbidden file and made the engineer invent a
substitute; this is the one place where the lists do not apply, and it is
named here rather than left to you.

| # | Mutation | Must go red |
| --- | --- | --- |
| Ma | Drop `none_of` from `judge`'s condition | the comparison tests in `tests/test_eval_scoring.py` |
| Mb | Swap the winner and the loser in one comparison's rule | that question's retro-score over the ten logs flips. **Report both numbers** |
| Mc | Make `expected_strings` return `()` for an `Expectation` | `tests/test_eval_workspace.py`'s expectation invariant goes green while covering nothing — so **it must not**. If it stays green, the invariant is not covering the new type and that is a finding to report, not to work around |
| Md | Put the new marker into a second file in `eval-fixture/` | the one-carrier test from Part 2 |
| Me | Write the new expectation into a fixture file's **contents** | `test_no_unreviewed_file_holds_an_expected_answer`. Delete the string afterwards; do not commit it |
| Mf | Add a seventh file to `eval-fixture/` | the listing question's expectation **does not move** (brief 08's Sc, re-run because this brief adds a file to that directory) |
| Mg | Put a question text into the Part 3 record | the record test |

**Mc is the one to take seriously.** A test asserting "this is refused" proves
nothing if several independent guards would refuse it, and the mirror of that
is a test that passes because it is checking nothing. Mc is how you find out
which one you wrote.

# The three gates

```
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m pytest
```

Full path, **no `-q` of your own** (`pyproject.toml:168` sets it; a second one
deletes the summary line). Baseline **636 passed**, mypy clean over **43**
files. This brief adds tests and one reachable file, so both numbers move:
say what they moved to and why. A move you cannot explain is a finding.

# Files you may touch

- `scripts/eval_scoring.py`
- `scripts/holdout_eval.py`
- `scripts/session_eval.py`
- `tests/test_eval_scoring.py`
- `tests/test_holdout_questions.py`
- `tests/test_eval_workspace.py`
- `tests/test_session_eval.py` — only if Part 2's replacement breaks it
- a new test file if you want one
- `eval-fixture/<one new file>` — **one file, no subdirectory.** A second
  subdirectory makes brief 08's listing question ambiguous
- `.gitignore` — only if `data/holdout-runs.jsonl` is not already covered

# Files you may not touch

`agent.py` · `tools.py` · `sandbox.py` · `scripts/eval_workspace.py` ·
`scripts/collect_dataset.py` · `scripts/build_notebook.py` ·
`README.md` · `questions/**` · `models/**` · `omniagent-core/**` ·
`.github/workflows/**` · `NEXT_CHAT.md` · `docs/` except your `## Result` ·
the six existing files under `eval-fixture/` · anything on
`core-offline-runtime`.

`data/**` is **read-only** for this brief: read the ten run logs, write
nothing into it by hand. Both evaluations append to it when they run, which is
theirs to do and not yours.

Every mutation in the table above is inside the touchable set — I have checked
that this time. If a file is in neither list, ask rather than decide.

# `docs/` and the no-quoting rule, stated honestly

`docs` is in `ANSWER_KEY`, so this file is sealed and quoting a question here
would **not** fail the invariant. Briefs 07 and 08 told two engineers it
would, and that was wrong.

Keep the discipline anyway, as defence in depth: if `docs` ever leaves
`ANSWER_KEY`, every brief in it becomes a leak at once. So in your `## Result`,
refer to questions by line number and **do not quote the new marker, the new
filename, or any question text.**

The rule that is not defence in depth, and that a test will enforce:
**nothing may be written into `eval-fixture/` except the one new subject file
this brief asks for.** That directory is reachable by design.

# The split — who does which half

You cannot run an evaluation: your sandbox returns `WinError 10013` on
`localhost`, confirmed twice on 2026-10-24 with Ollama up and answering for
the manager. **Nothing in this brief needs one.** The retro-scoring reads logs
already on disk, and every check above is static.

| Half | Owner |
| --- | --- |
| all three parts, the tests, Ma–Mg, the retro-score over the ten logs, the three gates, the commits | **you** |
| the prediction written before any run, the ten new runs with variance, the new baseline, and whether the two comparisons move the score for the model's reasons or the instrument's | **the project manager** |

**Do not report a measurement you did not produce.** Say in `## Result` that
the ten runs are outstanding and are the manager's.

# The one thing that would make this wrong

**A rule that grades phrasing instead of answers.** The whole point of this
brief is that the old instrument graded characters; a `none_of` list tuned
until the ten recorded answers come out right is the same mistake with more
machinery. The defence is that each comparison question **says** what shape of
answer it is graded on, and the rule checks exactly that and nothing else. If
you find yourself adding a third or fourth `none_of` string to make a recorded
answer pass, stop and report it — the question is wrong, not the rule.

The second way: **the leak invariant stops covering the new expectation type.**
Mc exists to make you watch that fail before you trust it. An invariant that
passes because it iterates an empty tuple is worse than no invariant, because
the figures quoted from it read as checked.

# Commit

Three steps, one commit each, gates green at every step:

```
git add scripts/eval_scoring.py tests/test_eval_scoring.py scripts/holdout_eval.py tests/test_holdout_questions.py tests/test_eval_workspace.py
git commit -m "eval: grade a comparison with a rule, not a substring"

git add eval-fixture scripts/holdout_eval.py scripts/session_eval.py tests/test_eval_workspace.py tests/test_session_eval.py
git commit -m "eval: a search subject whose answer is only in the subject"

git add scripts/holdout_eval.py tests/ .gitignore
git commit -m "measure: one record per question, so a derailment can be scored later"
```

Then **commit this brief file with your `## Result` appended**:

```
git add docs/pm/brief-10-no-question-is-scored-on-nothing.md
git commit -m "docs: brief 10 result -- the instrument no longer scores a question on nothing"
```

**Do not run a bare `git push`** — two remotes, and `main` tracks the one this
work does not belong to. Name it: `git push origin main`.

# The prediction, written before any run — 2026-10-26, HEAD `4c33c2f`

Written **before the engineer has started**, which is earlier than the
standard asks for and is the point: a prediction written after the code exists
is a story told about a number. Ollama has not been restarted and no run of
any kind has been made since this brief was issued.

Current baseline to beat: **`omniagent-v2`, 11/16, zero variance over ten
runs, 2026-10-24**, failing set byte-identical every run.

## What the denominator does, and the misreading I am pre-committing against

| Change | Denominator |
| --- | --- |
| today | 16 |
| the `'budget'` question retired | 15 |
| its replacement added | 16 |
| the comparison at `:77` becomes checkable | 17 |
| the follow-up at `:122` becomes checkable | 18 |

**The new figure will look like a regression and will not be one.** 11/16 is
69%; anything under 12.4/18 reads as worse while meaning nothing of the kind.
I am writing this down now so that neither of us gets to discover it
afterwards.

## The five predictions, each falsifiable

**P1 — the comparison at `:77` scores 0/10 under Part 1 as written.** It is
answered correctly in substance in all ten recorded runs, and every one of
those answers names both files. The new rule forbids the loser's name, so the
question passes only if the model obeys the new "name the file only"
instruction. This model drops out of formats it was explicitly taught
(`agent.py:207-218`), so I do not expect it to obey a format instruction it
has never seen. **If P1 is right, a question that is right ten times out of
ten will report zero.**

**P2 — the follow-up at `:122` scores 0/10.** Six of ten runs exhaust the step
budget and three invent a tool failure; nothing in this brief changes the
agent, so I expect the same behaviour and the same answers. The one run that
named the right file would be graded wrong under Part 1 as written, because it
names both.

**P3 — the replacement search question scores 9/10 or 10/10.** Brief 08's
replacement went 10/10 and this one is an easier shape: one marker, one
carrier, `search_text` is the obvious tool. **The failure mode, if there is
one, is the agent answering with the matched line instead of the filename** —
that is what the retired question trained it to do, and it is the specific
thing I will look for in run 1.

**P4 — the total is 12/18, with zero variance.** 11 correct today, minus the
`'budget'` question which was a guaranteed miss, plus the replacement (P3),
plus nothing from `:77` and `:122` (P1, P2). Zero variance survives because
every one of those outcomes is the same in all ten recorded runs.

**P5 — the wall clock stays unstable and the step count moves.** The 237 s to
1,508 s spread is a property of the machine, not the question set, so I expect
it to persist. The step total will not stay at 57: two questions are reworded
and one is replaced.

**What would make me wrong in an interesting way:** P1 failing because the
model *does* obey the format instruction. That would say something about this
fine-tune that the nine briefs so far have not — and it is cheap to find out,
which is the next section.

# A defect in this brief, found by writing the prediction

P1 is a prediction that **my own rule turns a question the agent answers
correctly into a zero.** That is worth stopping for.

`scripts/holdout_eval.py:7-12` states the principle this project was built on:
tool choice and correctness are scored separately, because "dumping a whole
file to count its lines is a wrong answer that happens to be right", and
rolling two things into one figure hides exactly that. `scripts/eval_scoring.py:76-80`
says the same again.

**Part 1 as written breaks that principle.** A comparison question graded on
`none_of` plus a format instruction reports one bit for two different
capabilities — can it compare, and will it obey an answer format. When that
bit is zero we cannot say which failed. That is the defect the whole project
is organised against, and I wrote it into the brief myself.

The honest alternative is weaker in a way I can state exactly:

| | **A1 — as issued** | **A2 — the winner's name alone** |
| --- | --- | --- |
| the rule | `all_of=(winner,)`, `none_of=(loser,)`, question text demands the filename only | `expect=winner`, a plain substring, question text unchanged |
| needs the `Expectation` type | yes | **no — Part 1 collapses to giving two questions an ordinary expectation** |
| `:77` on the recorded answers | 0/10 | 10/10 |
| `:122` on the recorded answers | 0/10 | **1/10** — run 07 names the right file |
| the hole | closed | **open: "Y is longer than X" would be graded right.** Never observed in ten runs, and it is why the original author left the question unscored |
| axes | comparison and instruction-following rolled into one bit | separate, as the project requires |
| variance | zero preserved | **the first non-zero score variance this project has measured**, 12 or 13 depending on the run |

A2's non-zero variance is not a flaw in A2. It is information A1 would hide:
the derailment at `:122` is *not* fully deterministic, and today's "byte-identical
every run" claim is true of the answers, not of the behaviour behind them.

**This is a decision about what the instrument is for, so it goes to the owner
rather than being settled here.** It is recorded at the top of this file as a
hold on Part 1. Parts 2 and 3 stand either way.

## The probe that would settle P1 for about a minute of model time

Ask the reworded `:77` question once, on its own, under the sealed workspace,
and read whether the model answers with the filename alone. One question, not
an evaluation — minutes, not the 40-to-250 of a full run. **The prediction
above is written and committed first, so the probe can only confirm or refute
it, not inform it.** This is the manager's half and needs Ollama restarted.

## Result

<!-- Engineer: append here. The retro-score of the ten recorded logs under the
new rules for both comparisons, with what it does not tell us; the carrier
counts for the new marker and the new filename; the contamination counts; the
rendered length of the new fixture file; Ma-Mg each with the test that went
red; the three gate results with the new test count explained; whether
data/holdout-runs.jsonl is reachable; the commit hashes; and anything you
refuse to claim -- including that the ten runs are the manager's and are
outstanding. Quote neither the marker, the filename, nor any question text. -->
