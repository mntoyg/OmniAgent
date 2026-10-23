# Brief 06 — the paste-ready task for the security engineer

Paste everything below the line. The companion brief is
`docs/pm/brief-06-pin-the-gates-environment.md`; `## Result` goes there.

---

You are the **security engineer** on OmniAgent. Work in the existing worktree:

```
cd ../OmniAgent-core
```

That is `core-offline-runtime`. The fullstack engineer is on `main` in
`D:\code-project\OmniAgent` — do not touch anything there except to run the
Python gates.

**Read `docs/pm/brief-06-pin-the-gates-environment.md` and execute it.** It is
a small task: two lines of YAML in one file.

## The change

In `.github/workflows/core.yml` only:

- `runs-on: ubuntu-latest` → `runs-on: ubuntu-24.04`
- **both** `uses: actions/checkout@v4` → `actions/checkout@v5`
- a one-line comment above `runs-on` saying why it is pinned: the gate depends
  on the runner's `/tmp` filesystem type, which `src/local_file.cpp:19-25`
  restricts, and `ubuntu-latest` is migrating to Ubuntu 26.

Nothing else changes. `timeout-minutes: 10`, the `paths` filters, the branch
list, the fingerprint value, the CRLF-refusal step, the inventory step and
`--no-tests=error` all stay exactly as they are.

## Why, in one paragraph

The first hosted run of this workflow passed 4/4 and recorded
`Fixture /tmp filesystem = ext2/ext3 (magic 0xef53)` — `EXT4_SUPER_MAGIC`,
which the allowlist permits. It also warned that `ubuntu-latest` began
migrating to Ubuntu 26 on 2026-10-19. **This gate's correctness depends on that
filesystem type, and a runner image change alters it with nothing in this
repository changing.** Pinning turns a silent change into a scheduled one. The
`ubuntu-24.04` label will itself be retired one day; that is the accepted trade.

For the record, measured today: `actions/checkout` is at **`v7.0.1`** —
`v5.1.0`, `v6.1.0` and `v7.0.1` were all published 2026-07-20. `v5` is two
majors behind but it does resolve the Node.js 20 deprecation, and `v5` is what
the owner decided. Do not go further than `v5` in this task.

## Files you may not touch

`.github/workflows/ci.yml` · `.github/workflows/waka-readme.yml` ·
`omniagent-core/**` · `models/**` · `tools.py` · `sandbox.py` · anything on
`main` · `NEXT_CHAT.md` · `docs/` except your `## Result`.

`ci.yml` and `waka-readme.yml` have the same floating label and `ci.yml` the
same `@v4`. They live on `main` where another engineer is working. Leave them.

## Verification is split, and this is deliberate

**You do not push, and this brief's real verification is a hosted run.** So the
halves are named up front rather than discovered at the end: you make the
change and check it locally; the project manager pushes and reads the run. Do
not ask for a local build — there is nothing here one would prove.

Check all four of these and report every output:

1. The YAML parses:
   `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/core.yml'))"`
2. `grep -n 'ubuntu-latest\|checkout@v4' .github/workflows/core.yml` →
   **nothing**
3. `grep -c 'actions/checkout@v5' .github/workflows/core.yml` → **2**
4. `git diff` → exactly the three changed lines plus your comment, one file

Check 3 is the important one. Bumping one checkout and not the other is the
obvious way to half-do this, and it would leave a deprecated Node runtime in
the job while the warning vanishes from the step that was fixed.

## The three Python gates

From the **main checkout**, full path `.venv\Scripts\python.exe`, and **never
your own `-q`** (`pyproject.toml:168` sets it; a second deletes the summary
line). Expect **633 passed**. You are editing one YAML file — any movement in
that number means you touched something outside your list.

## Commit

```
git add .github/workflows/core.yml
git commit -m "ci(core): pin the runner and the checkout action the gate was proved on"
```

`git show --stat` must list exactly that one file. **Do not push.**

Append `## Result` to `docs/pm/brief-06-pin-the-gates-environment.md`: the four
check outputs, the diff, the Python gate results, the commit hash, and
**anything you refuse to claim** — including, explicitly, that you have not
seen a hosted run. Commit that too, then stop.

## The one thing that would make this wrong

Pinning the label while leaving the reason undocumented. This pin exists
because of the filesystem allowlist in `src/local_file.cpp:19-25`. If the
comment beside `runs-on` does not say so, the next person removes the pin to
"keep up with latest" and the gate quietly begins measuring a different
environment. **The comment is as much the deliverable as the pin.**
