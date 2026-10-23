# Brief 06 — pin the gate's environment

**For the security engineer.** Small task, two lines of YAML. The brief is
short because the change is.

## Why

The first hosted run of `core.yml`
([39927752691](https://github.com/mntoyg/OmniAgent/actions/runs/39927752691),
4/4 passed, 1m 21s) raised two warnings:

1. `actions/checkout@v4` targets Node.js 20, which is deprecated and is being
   forced onto Node.js 24.
2. **`ubuntu-latest` began migrating to Ubuntu 26 on 2026-10-19.** That run
   landed on `ubuntu24/20261012.334`, so it has not migrated yet.

The second is the one that matters. This gate's correctness depends on the
runner's `/tmp` being a filesystem type `src/local_file.cpp:19-25` allows —
the run recorded `magic 0xef53`, which is `EXT4_SUPER_MAGIC`. A runner image
change alters that **with nothing in this repository changing**, so the hosted
evidence is true of Ubuntu 24 and is not a standing guarantee.

Pinning converts a silent change into a scheduled one. It is not free: the
`ubuntu-24.04` label will itself be retired eventually, and someone has to
revisit it. That is the trade, taken deliberately.

## A measured correction to record

The owner asked for `@v5`, and **`v5` resolves the Node.js 20 deprecation**, so
that is what this brief specifies. For the record: `actions/checkout` is at
**`v7.0.1`** as of today — `v5.1.0`, `v6.1.0` and `v7.0.1` were all published
2026-07-20. `v5` is therefore two majors behind the current release. Going
further is a one-character change and is **not** in this brief.

## Files you may touch

- `.github/workflows/core.yml`

## Files you may not touch

`.github/workflows/ci.yml` · `.github/workflows/waka-readme.yml` ·
`omniagent-core/**` · `models/**` · `tools.py` · `sandbox.py` · anything on
`main` · `NEXT_CHAT.md` · `docs/` except your `## Result`.

`ci.yml:24` and `waka-readme.yml:13` carry the same floating `ubuntu-latest`,
and `ci.yml:28` the same `actions/checkout@v4`. They are on `main`, where the
fullstack engineer is working, and they are a separate task. Leave them.

Work in the existing worktree on `core-offline-runtime`:

```
cd ../OmniAgent-core
```

## The change

- `runs-on: ubuntu-latest` → `runs-on: ubuntu-24.04`
- both `uses: actions/checkout@v4` → `actions/checkout@v5`

Add a one-line comment above `runs-on` saying why it is pinned: the gate
depends on the runner's `/tmp` filesystem type and `ubuntu-latest` is migrating
to Ubuntu 26. A pin without a reason beside it gets "cleaned up" by the next
person.

Change nothing else. The `timeout-minutes: 10`, the `paths` filters, the branch
list, the fingerprint value, the CRLF-refusal step, the inventory step and the
`--no-tests=error` all stay exactly as they are.

## How this is verified, and who does which half

**This brief's verification is a hosted run, and you do not push.** So it is
split at the start, which is the process fix from brief 05 rather than a
surprise at the end:

- **You** make the change, check it locally as below, commit, and report.
- **The project manager** pushes the branch, reads the hosted run, and records
  what it shows.

Do not ask for a local build; there is nothing here a local build would prove.

### What you check locally

1. The YAML parses. `python3 -c "import yaml,sys;
   yaml.safe_load(open('.github/workflows/core.yml'))"` or equivalent.
2. `grep -n 'ubuntu-latest\|checkout@v4' .github/workflows/core.yml` returns
   **nothing**.
3. `grep -c 'actions/checkout@v5' .github/workflows/core.yml` returns **2** —
   both checkouts, not just the first.
4. `git diff` shows exactly three changed lines plus your comment, in one file.

Report all four outputs. A pin that only landed on one of the two checkouts is
the obvious way to half-do this, and check 3 is what catches it.

### What the hosted run must then show — the manager's half

Stated here so the record has a prediction written before the run:

- the job still succeeds, 4/4 tests passed;
- `Fixture /tmp filesystem` still reports `magic 0xef53`;
- `Verify CRLF is refused` still fires;
- **the Node.js 20 annotation is gone.** If it is still there, the bump did not
  take and that is a finding, not a formality;
- the runner image line names an `ubuntu24` image, now because it was asked for
  rather than by luck.

## The three Python gates

From the **main checkout**, unchanged: `.venv\Scripts\python.exe -m ruff
check .`, `-m mypy`, `-m pytest`. Full path, **no `-q` of your own**. Expect
**633 passed**. You are editing one YAML file, so any movement in that number
means you touched something outside your list.

## The one thing that would make this wrong

Pinning the label while leaving the gate's real dependency undocumented. The
reason this pin exists is `src/local_file.cpp:19-25` — the filesystem
allowlist — and if the comment beside `runs-on` does not say so, the next
person removes the pin to "keep up with latest" and the gate quietly starts
measuring a different environment. The comment is the point as much as the pin.

The second way: bumping one checkout and not the other, which leaves a
deprecated Node runtime in the job while the warning disappears from the step
that was fixed.

## Commit

```
git add .github/workflows/core.yml
git commit -m "ci(core): pin the runner and the checkout action the gate was proved on"
```

`git show --stat` must list exactly that one file. **Do not push.**

## Result

<!-- Engineer: append here. The four local check outputs, the git diff, the
three Python gate results, the commit hash, and anything you refuse to claim —
including, explicitly, that you have not seen a hosted run. -->

## Result

- YAML parse: passed with the main checkout's PyYAML.
- `rg -n 'ubuntu-latest|checkout@v4' .github/workflows/core.yml`: no matches.
- `rg -c 'actions/checkout@v5' .github/workflows/core.yml`: `2`.
- Diff: `.github/workflows/core.yml` only; runner changed to `ubuntu-24.04`, both checkouts to `@v5`, and a comment records the `/tmp` filesystem dependency and Ubuntu 26 migration.
- Python gates: ruff passed; mypy passed (42 files); pytest **633 passed in 11.90s**.
- Commit: `da1a5be9eee6e6f28f60a55076f74c5f81599380`.

I have not seen a hosted run; verification is for the project manager after push. I made no claim about hosted behavior. No push was made.
---

## PM verification — 2026-10-23, `da1a5be`

### The engineer's half, re-run

| Check | Result |
| --- | --- |
| 1. YAML parses | **OK** — `jobs.native` keys are `runs-on`, `timeout-minutes`, `steps` |
| 2. no `runs-on: ubuntu-latest`, no `checkout@v4` | **clean**. The one textual hit for `ubuntu-latest` is inside the comment that explains the pin |
| 3. `grep -c 'actions/checkout@v5'` | **2** — both checkouts, which was the half-done failure mode |
| 4. scope | one file, 4 insertions, 3 deletions. `da1a5be` touches `core.yml` and nothing else |

The comment names `local_file.cpp` and the Ubuntu 26 migration, which was as
much the deliverable as the pin itself.

**The report says, in its own words, "I have not seen a hosted run;
verification is for the project manager after push. I made no claim about
hosted behavior. No push was made."** That is the split from brief 05 working
as intended the first time it was used — named up front, honoured at the end,
with no claim reaching past the evidence.

One small note for whoever automates this later: a naive
`grep ubuntu-latest .github/workflows/` now matches the explanatory comment. A
check written that way would false-positive on the very comment that documents
the pin.

### The hosted half — the manager's

Pushed to `origin`. Run
[39929249216](https://github.com/mntoyg/OmniAgent/actions/runs/39929249216),
job `native`, **success in 1m 49s**.

The prediction was written into this brief before the run. Against it:

| Predicted | Observed |
| --- | --- |
| job succeeds, 4/4 | `100% tests passed, 0 tests failed out of 4`, 0.25 s |
| `Fixture /tmp filesystem` still `0xef53` | `Fixture /tmp filesystem = ext2/ext3 (magic 0xef53)` |
| `Verify CRLF is refused` still fires | fires — `canonical LF. CRLF may result from core.autocrlf=true…` |
| **the Node.js 20 annotation is gone** | **gone.** `grep -ic 'Node.js 20 is deprecated'` over the whole job log returns **0** |
| the image line names an `ubuntu24` image by request | `Image Release: … ubuntu24/20261012.334` |

The `ubuntu-latest will migrate to Ubuntu 26` warning is also gone — the same
grep returns **0** for it. The previous run carried two annotations; this one
carries none.

The image is the same build as before, `ubuntu24/20261012.334`. The difference
is that it is now the image this gate asked for, rather than the one the
`ubuntu-latest` label happened to point at four days into a migration.

1m 49s against 1m 21s for the unpinned run, both far inside
`timeout-minutes: 10`.

### Verdict

**Correct, complete, and nothing to push back on.** The gate now names its own
environment, the two deprecation warnings are cleared, and every property the
gate was proved on this morning still holds on the pinned runner.

### What this does and does not buy

It converts a silent environment change into a scheduled one. It does **not**
make the environment permanent: the `ubuntu-24.04` label will itself be retired,
and when it is, this job fails loudly with an unknown-label error rather than
quietly measuring a different filesystem. That is the trade, and it was taken
deliberately.

Unchanged and still open: **nothing guards this workflow file from being
deleted.** M3's answer from brief 04 has not moved.

Also unchanged: `actions/checkout` is at `v7.0.1`; this is pinned at `v5`,
which clears the Node.js 20 deprecation and is two majors behind. That was the
owner's decision and it is recorded rather than quietly "improved".
