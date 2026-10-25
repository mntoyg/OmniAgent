# Brief 09 — the paste-ready task for the SWE

Paste everything below the line. The companion brief is
`docs/pm/brief-09-two-deterministic-wrong-answers.md`; `## Result` goes there.

---

You are the **SWE** on OmniAgent, `D:\code-project\OmniAgent`, branch `main`,
HEAD `0507632`. Baseline: **633 tests passing**, `ruff` clean, `mypy` strict
clean over 42 files.

**Read `docs/pm/brief-09-two-deterministic-wrong-answers.md` and execute it.**
It is an investigation, not a change: **no question and no expectation is
edited in this brief at all.**

## The two failures, by location only

Both wrong answers are **byte-identical across all ten runs** of 2026-10-24, so
neither is flaky.

**`scripts/holdout_eval.py:110`** — the fourth step of a four-step follow-up
chain. The arithmetic is sound and the expectation is right. The agent answers
`10% of 1000 is 100.`, resolving the pronoun to the **step-two** result instead
of step three. `NEXT_CHAT.md:390` already records this as a known referent
error and quotes the same reply. **That entry is correct and current** — the
only thing new is that it is now settled on ten runs.

**`scripts/holdout_eval.py:114`** — an elliptical follow-up,
`prefer_tool="file_info"`, expectation computed by `_lines(...)`. This is where
the record is wrong:

| Thing | Value |
| --- | --- |
| the expectation | **512** |
| what `file_info` reports to the agent | **512 lines, 16,767 bytes** |
| `text.count("\n") + 1` | 513 |
| the file ends with a newline | yes |
| **what the agent answers** | **`has 513 lines.`** |
| tools called | `read_file`, `file_info`, `get_current_time`, `calculate` |
| tool axis | **passes** |

**The agent resolves the ellipsis, picks the right tool, is handed 512 by that
tool, and then states 513.** The instrument is not at fault — expectation and
tool agree. `NEXT_CHAT.md:391` records the failure as *"cannot be read because
it is too long"*, which is **no longer what happens**; `:584` records v2
improving on exactly that, and it did. The entry is **stale, not false.**

## Your half — none of it needs a model

1. **Review the system prompt and every tool description** for anything that
   invites a +1 on a line count or defines lines in terms of newlines.
   `file_info`'s rendered output is `"<path>: 512 lines, 16,767 bytes"`, which
   is unambiguous — so if the inducement exists, it is elsewhere.
2. **Scan the training data** at `G:/OmniAgent/datasets/2026-10-10-merged/`
   (2,215 examples, three `.jsonl` files; brief 07's scan works unchanged) for
   examples answering a line-count question. Report whether any is off by one
   against the file as it then stood, or phrases a line count as newlines plus
   one. **If the data taught the +1, that is the answer, and it is a collection
   defect rather than a model one.**
3. **Can `_lines` and `file_info` ever disagree?** They agree on this file
   today. Establish whether that is by construction or by accident — a file
   with no trailing newline, or with CRLF, is the interesting case. If they can
   diverge, the question is gradeable only by luck, and that is a separate
   defect deserving its own entry.
4. **Scan for the referent error too**: does any collected example resolve a
   pronoun to an earlier step than the immediately preceding one?

**State negative results as results.** "I looked here and it is not there" is
what makes the trace run worth doing; omitting it wastes the run.

## What you must not do

**Do not change either question to make it pass.** If the agent is wrong, the
question is working. The only reason to touch a question is a wrong
expectation, and neither of these has one.

**Do not change `tools.py`** — it is in flight with the fullstack engineer, and
a tool description reaches the model every turn and is part of every training
example, so changing one invalidates the dataset.

## Files you may touch

`NEXT_CHAT.md` — **only** the stale entry at `:391`, struck in place, rewritten
to describe what now happens. And your `## Result` in the brief.

## Files you may not touch

`tools.py` · `sandbox.py` · `scripts/holdout_eval.py` ·
`scripts/eval_scoring.py` · `scripts/eval_workspace.py` ·
`scripts/collect_dataset.py` · `tests/**` · `eval-fixture/**` ·
`questions/**` · `models/**` · `data/**` · `omniagent-core/**` ·
`.github/workflows/**` · `README.md` · anything on `core-offline-runtime`.

If a file is in neither list, ask rather than decide.

## Gates

```
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m pytest
```

Full path, **never your own `-q`**. Baseline **633 passed** and it **must not
move** — you are editing one Markdown file.

## The split

Your sandbox returns `WinError 10013` on `localhost`, confirmed twice on
2026-10-24, so you cannot run the agent.

- **You:** the prompt and tool-description review, both training-data scans,
  the `_lines` vs `file_info` divergence answer, the `NEXT_CHAT.md`
  correction, the gates, the commit.
- **The project manager:** a run with tool arguments printed, to see what
  `calculate` was actually asked.

Say plainly in your report that the trace run is outstanding and whose it is.

## Commit

```
git add NEXT_CHAT.md docs/pm/brief-09-two-deterministic-wrong-answers.md
git commit -m "docs: the line-count follow-up fails differently than the record says"
```

**Do not run a bare `git push`** — two remotes, and `main` tracks the one this
work does not belong to.

## The one thing that would make this wrong

**Concluding from the hypothesis.** `text.count("\n") + 1` being exactly 513 is
suggestive and proves nothing. A model can be off by one for many reasons, and
`calculate` appearing in the trace does not say what it computed. If the scans
come back empty, the honest result is "the inducement is not in the prompt or
the data, and the trace run is needed" — **not** a story about newlines.

The second way: treating a stale record as a wrong one. `NEXT_CHAT.md:391` was
right when written. The correction should say the entry is stale, not that it
was mistaken.
