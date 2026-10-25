# Brief 09 — two deterministic wrong answers, and a record that is stale

**For the SWE.** Static investigation; the trace run is the manager's half and
is named at the bottom.

## What I retract first

Yesterday I wrote that the expectations `50` and `512` were "new to the record"
and "two new diagnosable defects". **Both were already recorded**, at
`NEXT_CHAT.md:390` and `:391`. I did not check before writing it. The figures
were right; the claim of novelty was not.

And the record itself is now stale for one of them, which is the finding this
brief exists for.

## What is measured, 2026-10-25, over the ten runs of 2026-10-24

Both wrong answers are **byte-identical in all ten runs** — md5 `7ea0d762` and
`aec8b082` over the answer line, every run. These are not flaky.

### The percentage chain

A four-step follow-up chain ending at `scripts/holdout_eval.py:110`. The
arithmetic is sound: 144 × 12 = 1728, − 728 = 1000, half = 500, 10% = **50**.
Steps one to three pass. The fourth answers

> `10% of 1000 is 100.`

So the agent resolves "that" to the **step-two** answer, not the step-three
answer. `NEXT_CHAT.md:390` already calls this a "known referent error, resolves
'that' to the step-2 answer" and quotes the same reply. **The record is correct
and current. Nothing about this one is new except that it is now settled on
ten runs rather than asserted.**

### The line-count ellipsis — the record is wrong

An elliptical follow-up at `scripts/holdout_eval.py:114`, `prefer_tool`
`file_info`, expectation computed as `_lines("scripts/build_notebook.py")`.

`NEXT_CHAT.md:391` records the failure as *"cannot be read because it is too
long"* — a "known elliptical-follow-up failure", and `:584` says v2 improved on
exactly that. **That is no longer what happens.** Measured today:

| Thing | Value |
| --- | --- |
| `_lines(...)`, i.e. the expectation | **512** |
| what `file_info` reports to the agent | **512 lines, 16,767 bytes** |
| `text.count("\n") + 1` | 513 |
| the file ends with a newline | yes |
| **what the agent answers** | **`scripts/build_notebook.py has 513 lines.`** |
| tools it called | `read_file`, `file_info`, `get_current_time`, `calculate` |
| tool axis | **passes** |

**The agent resolves the ellipsis, picks the right tool, is handed 512 by that
tool, and then states 513.** It is off by exactly one, and it called
`calculate` on the way. The instrument is not at fault: the expectation and the
tool agree on 512.

So the current failure is **not** the documented one. v2 did improve on the
ellipsis; what is left is an arithmetic step the agent takes after already
having the answer. The entry at `:391` describes a model that no longer exists.

## Goal

Three things, in order of what they are worth.

1. **Correct `NEXT_CHAT.md:391`** so it describes the failure that happens now.
2. **Establish why 513.** The strongest hypothesis is that the agent reasons
   "lines = newlines + 1" and uses `calculate` to add one to a number it
   already has. `text.count("\n") + 1` is exactly 513, which is suggestive and
   is not proof.
3. **Say whether either is fixable at all**, and by what. If the answer is
   "neither, at this model size", that is a legitimate and useful result — the
   `4740` question is already recorded as an irreducible capability failure, and
   a fourth entry in that category is worth more than a question quietly
   rewritten to pass.

## What you can do without a model — this is your half

1. **Read the system prompt and every tool description** for anything that
   invites a +1 on a line count, or that describes a line count in terms of
   newlines. `tools.py`'s `file_info` docstring and its rendered output are the
   first place to look; the rendered form is `"<path>: 512 lines, 16,767
   bytes"`, which is unambiguous, so if the inducement exists it is elsewhere.
2. **Check the training data.** Scan
   `G:/OmniAgent/datasets/2026-10-10-merged/` for examples that answer a
   line-count question, and report whether any of them is off by one against
   the file as it stood, or phrases a line count as newlines plus one. 2,215
   examples, three `.jsonl` files; the scan from brief 07 works unchanged. **If
   the training data taught the +1, that is the answer and it is a collection
   defect, not a model one.**
3. **Check whether `_lines` and `file_info` can ever disagree.** They agree on
   this file today. Find out whether they agree by construction or by accident
   — a file without a trailing newline, or with `\r\n`, is the interesting case.
   If they can diverge, the question is gradeable only by luck and that is a
   separate defect worth its own entry.
4. For the percentage chain, **check whether the referent error is in the
   training data too**: does any collected example resolve a pronoun to an
   earlier step than the immediately preceding one?

Report what you find and what you looked at and did not find. A negative result
here is useful and must be stated as one, not omitted.

## What you must not do

**Do not change either question to make it pass.** If the agent is wrong, the
question is working. The only reason to touch a question is if the *expectation*
is wrong, and for both of these it is not — the arithmetic is sound and the
expectation agrees with the tool.

Do not change `tools.py` — it is still in flight with the fullstack engineer on
brief 03, and in any case a tool description reaches the model on every turn and
is part of every training example, so changing one invalidates the dataset.

## Files you may touch

- `NEXT_CHAT.md` — **only** the stale entry at `:391` and only to make it
  describe what now happens. Strike in place, do not delete.
- `docs/pm/brief-09-two-deterministic-wrong-answers.md` — your `## Result`

## Files you may not touch

`tools.py` · `sandbox.py` · `scripts/holdout_eval.py` ·
`scripts/eval_scoring.py` · `scripts/eval_workspace.py` ·
`scripts/collect_dataset.py` · `tests/**` · `eval-fixture/**` ·
`questions/**` · `models/**` · `data/**` · `omniagent-core/**` ·
`.github/workflows/**` · `README.md` · anything on `core-offline-runtime`.

**No question and no expectation changes in this brief at all.** If a file is in
neither list, ask rather than decide.

## The three gates

```
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m pytest
```

Full path, **no `-q` of your own**. Baseline **633 passed**. You are editing one
Markdown file and writing a report, so the count must not move. If it does, you
touched something outside your list.

## The split

You cannot run the agent: your sandbox returns `WinError 10013` on `localhost`,
confirmed twice on 2026-10-24.

| Half | Owner |
| --- | --- |
| the prompt and tool-description review, the two training-data scans, the `_lines` vs `file_info` divergence question, the `NEXT_CHAT.md` correction, the gates, the commit | **you** |
| a run with the tool arguments printed, to see what `calculate` was actually asked, and any re-measurement of either question | **the project manager** |

**Do not report a measurement you did not produce.** Say plainly that the trace
run is outstanding and whose it is.

## The one thing that would make this wrong

**Concluding from the hypothesis.** `text.count("\n") + 1` being exactly 513 is
suggestive and proves nothing: a model can be off by one for many reasons, and
`calculate` appearing in the trace does not say what it computed. If your scans
come back empty, the honest result is "the inducement is not in the prompt or
the data, and the trace run is needed" — not a story about newlines.

The second way: treating a stale record as a wrong measurement. `NEXT_CHAT.md:391`
was **right when it was written**. v2 improved on the ellipsis, as `:584`
records. The entry is stale, not false, and the correction should say so.

## Commit

```
git add NEXT_CHAT.md docs/pm/brief-09-two-deterministic-wrong-answers.md
git commit -m "docs: the line-count follow-up fails differently than the record says"
```

**Do not run a bare `git push`** — two remotes, and `main` tracks the one this
work does not belong to.

## Result

<!-- Engineer: append here. What you reviewed and what you found, including
negative results. The two training-data scan commands and their counts. The
_lines vs file_info divergence answer. The NEXT_CHAT correction you made. The
three gate results, the commit hash, and anything you refuse to claim --
including that the trace run is the manager's and is outstanding. -->
