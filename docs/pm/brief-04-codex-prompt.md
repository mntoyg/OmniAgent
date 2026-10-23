# Brief 04 — the paste-ready task for the security engineer

Paste everything below the line. The companion brief is
`docs/pm/brief-04-the-fourth-gate.md`; `## Result` goes there.

---

You are the **security engineer** on OmniAgent, a Windows repository at
`D:\code-project\OmniAgent`. Another engineer is working on `main` right now,
so your first command is a worktree:

```
git worktree add ../OmniAgent-core core-offline-runtime
```

**Everything you do happens in `../OmniAgent-core`, on the branch
`core-offline-runtime`.** You touch no file on `main`. Do not switch the main
checkout's branch for any reason.

**Read `docs/pm/brief-04-the-fourth-gate.md` and execute it.** It carries
today's measurements and two findings I already checked so you do not repeat
them. Do not re-derive the figures; do verify anything you are about to rely on.

## Your task in one sentence

Give the 1,221 lines of C++20 in `omniagent-core/` a CI gate that can fail, and
check that the security claims in its README have tests behind them.

## The constraints that decide whether this is right

1. **A gate that cannot fail is worse than no gate**, because it gets believed.
   M1 through M5 in the brief exist to demonstrate each `ctest` target going
   red for a real reason. M6 asks what guards the gate itself; if the answer is
   "nothing", say so plainly rather than leaving it implied.
2. **CMake must still never download llama.cpp.** The workflow supplies the
   source with `actions/checkout` pinned to commit
   `869034b4bb93a425ea989d30fc3d000f5a461d58` from `ggml-org/llama.cpp`, and a
   separate step fails the job unless
   `sha256sum models/llama.cpp/include/llama.h` equals
   `edea14f935e2729d157e063b1ebdde3deeca9714389aaf0d5a20424b6b98a5ff`. Both of
   those values are verified against the local checkout as of today.
3. **Do not fix `src/` or `include/`.** If a mutation shows a README claim is
   false about the code, that is a finding and you stop. Changing a security
   boundary is the owner's decision, not yours. Mutations are the one exception
   — mutate, observe, restore from a scratch copy, verify the restore with a
   checksum, and prove with `git show --stat` that nothing under `src/` or
   `include/` is in your commit.
4. **A claim with no run behind it does not stay in a public README.** For each
   untested claim: add a test that fails when it is untrue, or strike the
   claim. Do not soften a claim into vagueness to avoid testing it. Keep the
   honest limits paragraph that begins "This contract covers owned heap
   buffers" — it is correct and it is the model for the rest.
5. **No build cache, and no `continue-on-error`.** A stale cache tests
   something other than the current source; `continue-on-error` makes the gate
   decorative. Set `timeout-minutes` from your measured build time plus
   headroom, and report the number you measured.

## Environment rules, each already paid for once

- **Windows is refused at configure time on purpose** (`CMakeLists.txt:5`).
  Build under the local Ubuntu WSL distribution.
- **A command over 600 seconds is backgrounded and dies with the session.** A
  llama.cpp build may exceed that. Start it in the background deliberately and
  do other work while it runs, rather than losing it at the limit.
- **Mutation checks: copy the file to a scratch directory outside the
  repository and restore from that copy.** Never `git checkout --` alone.
  Assert the target string is present before replacing it — a `sed` pattern
  containing `\n` matches nothing silently, so a mutation can appear to pass
  without having mutated anything.
- **Full interpreter path for the Python gates: `.venv\Scripts\python.exe`**,
  run from the **main checkout**, and **never pass `-q` to pytest yourself**
  (`pyproject.toml:168` sets it; a second one deletes the summary line). Expect
  **633 passed**, unchanged. If that number moved you touched something you
  should not have.
- **`cmd.exe` reads `/` as a switch** — backslashes there.
- Do not create a pull request. Do not amend existing commits.

## Two things already checked, so you do not have to

- **`OMNI_CORE_TESTING=1` relaxes nothing.** It occurs once, at
  `include/omniagent/local_inference_engine.hpp:66`, and only adds
  `friend struct EngineTestAccess`. `src/local_file.cpp` and
  `src/local_inference_engine.cpp` have no such guard, so the test build
  enforces the same path and filesystem validation as the shipped one. If you
  find otherwise, that is the most important thing in your report.
- **The filesystem allowlist and the fixture do not contradict each other.**
  `tests/core_tests.cpp:63` copies the GGUF off the build directory with
  `fs::copy_file` before loading it, which is why a fixture under `/mnt/d`
  loads at all. That makes **the runner's temporary filesystem part of the
  gate** — confirm its type on `ubuntu-latest` and record it, because
  `src/local_file.cpp:19-25` enforces ext4/XFS/Btrfs/tmpfs/ramfs/overlayfs and
  nothing else.

## Order of work

1. The worktree, then the local WSL build, then `ctest`. Paste the output — it
   replaces the 2026-10-11 log as this code's current evidence.
2. `.github/workflows/core.yml`, triggering on both `main` and
   `core-offline-runtime`, with the `paths` filter from the brief.
3. M1 through M6, each with what went red and what stayed green.
4. The claim-to-test table, with every untested claim resolved one way or the
   other.
5. The three Python gates from the main checkout. **633 passed**, unchanged.
6. One commit on the branch:
   `ci(core): a fourth gate that builds the native runtime and runs its tests`

**Do not push.** Two remotes, and the branch exists on `origin` only.

Append `## Result` to `docs/pm/brief-04-the-fourth-gate.md`: the build time,
the `ctest` output, M1 to M6, the claim-to-test table, the measured
`timeout-minutes`, the Python gate results, the commit hash, and **anything you
refuse to claim**. Commit that too, then stop.

## The one thing that would make all of this wrong

A workflow that goes green while proving nothing — building successfully and
running no tests, or testing a stale build directory, or skipping `ctest`
because an earlier step soft-failed. That job then gets cited as "the core is
gated" for months. Show each target failing for a real reason, or the gate is
decoration.
