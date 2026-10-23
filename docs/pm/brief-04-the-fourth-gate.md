# Brief 04 — the fourth gate for `omniagent-core`

**For the security engineer.**

1,221 lines of C++20 sit on the branch `core-offline-runtime` (`cfbde93`),
outside all three gates. Its only evidence is a `ctest` log dated
**2026-10-11 15:57**, 4/4 passed, built under WSL — twelve days old and not
re-run since. The branch is public. This brief gives that code a gate that can
fail, and checks that its README claims have tests behind them.

## Where you work — read this first

Brief 03 is in flight on `main` and owns `tools.py`. **Do not work in the main
checkout.** Make a worktree for the branch:

```
git worktree add ../OmniAgent-core core-offline-runtime
```

Everything in this brief happens there, on `core-offline-runtime`. You touch no
file on `main`, and the two tasks cannot collide.

## What is measured, 2026-10-23

| Fact | Value | How |
| --- | --- | --- |
| llama.cpp origin | `https://github.com/ggml-org/llama.cpp.git` | `git -C models/llama.cpp remote -v` |
| pinned commit | `869034b4bb93a425ea989d30fc3d000f5a461d58` | local checkout `rev-parse HEAD` — **matches the pin** |
| expected `include/llama.h` SHA256 | `edea14f935e2729d157e063b1ebdde3deeca9714389aaf0d5a20424b6b98a5ff` | `CMakeLists.txt:16` |
| actual local SHA256 | **identical** | `sha256sum models/llama.cpp/include/llama.h` |
| checkout size | 213 MB | `du -sh` |
| ctest targets | `make_tiny_gguf`, `core` (TIMEOUT 60), `secure_heap`, `offline_imports` | `CMakeLists.txt:59-84` |
| existing CI | `ubuntu-latest`, ruff/mypy/pytest, `timeout-minutes: 10`, triggers on `main` only | `.github/workflows/ci.yml` |

`models/llama.cpp` is gitignored, so **a clone of the branch cannot build**.
That is the hole this gate closes.

### Two things I checked before writing this, so you do not have to

1. **`OMNI_CORE_TESTING=1` does not relax any check.** `CMakeLists.txt:65`
   defines it `PUBLIC` on the library, which looked like the test build
   exercising a different code path than the shipped one. It appears exactly
   once in the sources, at
   `include/omniagent/local_inference_engine.hpp:66`, and all it does is
   `friend struct EngineTestAccess`. `src/local_file.cpp` and
   `src/local_inference_engine.cpp` contain no such guard, so path and
   filesystem validation are identical in both builds. **If you change that,
   say so loudly** — it would mean the tests stop being about the shipped code.

2. **The filesystem allowlist and the test fixture do not contradict each
   other.** `README.md` says a model on `/mnt/c` or `/mnt/d` is refused, and
   `src/local_file.cpp:19-25` enforces ext4/XFS/Btrfs/tmpfs/ramfs/overlayfs
   unconditionally. The fixture nonetheless loads successfully, because
   `tests/core_tests.cpp:63` does `fs::copy_file(argv[1], model)` — it copies
   the GGUF off the build directory to its own `root` first. **That makes the
   runner's temporary filesystem part of the gate**: on a runner where that
   root is not an allowed type, `core` fails for a reason that has nothing to
   do with the code. Confirm the type on `ubuntu-latest` and record it.

## Goal

Two things, and no more.

1. A CI job that builds `omniagent-core` and runs its four `ctest` targets, and
   that **can go red** — demonstrated, not asserted.
2. Every security claim in `omniagent-core/README.md` mapped to a named test
   that can fail. Any claim with no test behind it is either given one or
   struck from the README.

## Files you may touch, in the worktree only

- Add: `.github/workflows/core.yml`
- Modify: `omniagent-core/README.md`
- Modify or add: files under `omniagent-core/tests/`

Do not touch `tools.py`, `sandbox.py`, `.github/workflows/ci.yml`,
`omniagent-core/src/**`, or `omniagent-core/include/**`. If a claim turns out to
be false about the code rather than merely untested, **do not fix the code** —
record it in `## Result` and stop. Changing a security boundary is a separate
decision.

## The workflow it must produce

A **separate** file, not a job inside `ci.yml`. A C++ build failure must not
block the Python gates, and vice versa — they fail for unrelated reasons and
share nothing.

```yaml
name: core
on:
  push:
    paths: ["omniagent-core/**", ".github/workflows/core.yml"]
  pull_request:
    paths: ["omniagent-core/**", ".github/workflows/core.yml"]
  workflow_dispatch:
```

Triggers must cover **both** `main` and `core-offline-runtime`, or the gate is
invisible on the branch where the code actually lives. The `paths` filter keeps
it off documentation commits.

The llama.cpp checkout is done **by the workflow, not by CMake**:

```yaml
- uses: actions/checkout@v4
  with:
    repository: ggml-org/llama.cpp
    ref: 869034b4bb93a425ea989d30fc3d000f5a461d58
    path: models/llama.cpp
```

`CMakeLists.txt:13` says "this build never downloads it", and that stays true —
the workflow supplies the source, the build does not fetch it. This is a
deliberate reading of standard 1 and it is recorded here so nobody has to guess
later.

**Then verify the pin before building**, as its own step:

```
sha256sum models/llama.cpp/include/llama.h
```

and fail the job unless it equals
`edea14f935e2729d157e063b1ebdde3deeca9714389aaf0d5a20424b6b98a5ff`. CMake
checks the same hash, but it does so after configuring half a build and reports
it as a CMake error. A moved ref or a tampered mirror should fail closed in one
step with one sentence.

Then configure, build and test:

```
cmake -S omniagent-core -B omniagent-core/build -DCMAKE_BUILD_TYPE=Release
cmake --build omniagent-core/build --parallel
ctest --test-dir omniagent-core/build --output-on-failure
```

- **Set `timeout-minutes` from a measurement, not a guess.** Time the build and
  put the measured figure plus headroom in the workflow. Report the number.
- **Do not add a build cache in this brief.** A stale cache is a gate that
  tests something other than the current source. If the measured time is
  unacceptable, say so in `## Result` and leave caching to a decision.
- Do not add `continue-on-error` anywhere. A gate that cannot fail the run is
  not a gate.

## Build it locally first, under WSL

Windows is refused at configure time by design (`CMakeLists.txt:5`). Use the
local Ubuntu distribution. **A command over 600 seconds is backgrounded and
dies with the session**, so start the build in the background deliberately and
do other work while it runs rather than losing it at the 600-second mark.

Record the local build time and the `ctest` output. That log replaces the
twelve-day-old one as this code's current evidence.

## Mutation checks that must go red

This is the part that matters. A CI job that stays green while the code is
broken is worse than no job, because it is believed. Run each mutation locally
under WSL against the real build, restoring from a scratch copy outside the
repository each time — never `git checkout --` alone — and assert the target
string is present before replacing it.

| # | Mutation | Must go red |
| --- | --- | --- |
| M1 | Make the wiping store in `src/secure_heap.cpp` a no-op | `secure_heap` |
| M2 | Change one byte of `models/llama.cpp/include/llama.h` | the workflow's SHA256 step **and** the CMake fingerprint — report both, and which fired first |
| M3 | Reference `dlopen` from `tests/plugin_probe.cpp` or the test binary | `offline_imports` |
| M4 | Remove one refusal from `src/local_file.cpp`'s path validation — the `..` case, say | `core` |
| M5 | Remove a filesystem type from the `local_file.cpp` allowlist that the fixture root relies on | `core`, and this tells you which type the runner actually uses |
| M6 | Delete the `ctest` step from the workflow | **nothing locally** — which is the point: name what in the repository would notice, and if the answer is nothing, say so |

M1 and M4 touch `src/`, which this brief otherwise forbids. **Mutations are the
exception**: mutate, observe, restore from the scratch copy, and verify the
restore with a checksum. Nothing under `src/` or `include/` may appear in your
commit — prove it with `git show --stat`.

M6 is not a formality. The three Python gates are enforced by habit and by
`ci.yml`; a fourth gate in a second workflow file has nothing watching that it
still exists. Say plainly what protects it, even if the answer is "nothing yet".

## The claim-to-test map

`omniagent-core/README.md` makes a large number of security claims. Produce a
table in `## Result`: **claim, the README line it is on, the test that can fail
if it is untrue, and how you know that test covers it.** Start from the
"Verification" section, which already lists what the tests are meant to cover:
exact output over ten repetitions, forty concurrent requests, EOS, limits,
aborted prefill then successful reuse, concurrent unload, invalid
model/path/config, symlink/FIFO/log boundaries, and audit redaction — in a
231-line test file.

For every claim with no test behind it, choose one and say which:

- add a test that fails when the claim is untrue, or
- **strike the claim from the README.**

A claim with no run behind it does not stay in a public README. That is the
standard this whole project is built on, and the README's own honest limits
section — the paragraph beginning "This contract covers owned heap buffers" —
shows the author already knows the difference. Keep that paragraph.

Do not weaken a claim into vagueness to avoid testing it. Either it is checked
or it is gone.

## Gates before the commit

The three Python gates still apply, from the **main checkout**, because nothing
you touch should affect them:

```
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m pytest
```

Full path, **no `-q` of your own**. Expect **633 passed**, unchanged — if the
number moved, you touched something you should not have.

Plus, in the worktree: `ctest --test-dir omniagent-core/build
--output-on-failure`, 4/4 passing, with the output pasted.

## The one thing that would make this wrong

**A green workflow that proves nothing.** The failure mode is a job that builds
successfully and runs zero tests, or runs them against a stale build directory,
or whose `ctest` step is skipped because a previous step soft-failed. That job
is then cited as "the core is gated" for months. M1 through M5 exist to show
each target can actually fail; M6 exists to admit what guards the gate itself.

The second way: fixing the code. If a mutation reveals that a README claim is
false about `src/`, that is a finding, not a task. Record it and stop — the
owner decides whether a security boundary changes.

## Commit

On `core-offline-runtime`, in the worktree. One commit:

```
git add .github/workflows/core.yml omniagent-core/README.md omniagent-core/tests
git commit -m "ci(core): a fourth gate that builds the native runtime and runs its tests"
```

`git show --stat` must list nothing under `omniagent-core/src/` or
`omniagent-core/include/`.

**Do not push.** This repository has two remotes and the branch exists on
`origin` only; the project manager pushes it.

## Result

<!-- Engineer: append here. The local build time, the ctest output, M1 through
M6 each with what went red and what stayed green, the claim-to-test table with
every untested claim resolved either way, the measured timeout-minutes, the
three Python gate results, the commit hash, and anything you refuse to claim. -->


### Security engineer result — 2026-10-23

Implementation commit: `ef2ab18836f696d921e1ada57996fc7236b58c73` (`ci(core): a fourth gate that builds the native runtime and runs its tests`). This is the single implementation commit. This report is committed separately as requested by “Commit that too”; neither commit is amended. No push or pull request was made.

Worktree: `D:\code-project\OmniAgent-core`, branch `core-offline-runtime`, starting at `cfbde93`. The main checkout remained on `main`. My first command created an unnecessary `codex/brief-04-fourth-gate` worktree before I could read the exact prescribed branch name; I then created the prescribed worktree, verified the preliminary worktree was clean, and removed it and its unused branch. No main-checkout branch switch or source edit occurred. Only the required Python gates ran from main.

#### Build measurement and current evidence

Local distribution: Ubuntu WSL. Fresh Release configure: **12 seconds**; compilation with `--parallel`: **96 seconds**; total configure + build: **108 seconds**. No build cache was added. Build was started deliberately in the background with a live waiting WSL session; detached children were killed when their launcher exited, so a live session was necessary. The measured run completed successfully.

Workflow `timeout-minutes: 10`: 600 seconds gives 492 seconds beyond the measured 108-second local configure/build, allowing dependency checkout and a slower hosted CPU. This is local timing, not a hosted-run measurement.

Baseline command: `ctest --test-dir omniagent-core/build --output-on-failure`:

```text
Internal ctest changing into directory: /mnt/d/code-project/OmniAgent-core/omniagent-core/build
Test project /mnt/d/code-project/OmniAgent-core/omniagent-core/build
    Start 1: make_tiny_gguf
1/4 Test #1: make_tiny_gguf ...................   Passed    0.06 sec
    Start 2: core
2/4 Test #2: core .............................   Passed    0.16 sec
    Start 3: secure_heap
3/4 Test #3: secure_heap ......................   Passed    0.00 sec
    Start 4: offline_imports
4/4 Test #4: offline_imports ..................   Passed    0.03 sec

100% tests passed, 0 tests failed out of 4

Total Test time (real) =   0.28 sec

```

After the added assertions, all restores, and final test changes, the workflow's exact normalization, SHA256, filesystem, inventory and Test shell steps were executed locally with `bash -e -o pipefail`. All exited 0. Final Test output:

```text
Internal ctest changing into directory: /mnt/d/code-project/OmniAgent-core/omniagent-core/build
Test project /mnt/d/code-project/OmniAgent-core/omniagent-core/build
    Start 1: make_tiny_gguf
1/4 Test #1: make_tiny_gguf ...................   Passed    0.06 sec
    Start 2: core
2/4 Test #2: core .............................   Passed    0.17 sec
    Start 3: secure_heap
3/4 Test #3: secure_heap ......................   Passed    0.00 sec
    Start 4: offline_imports
4/4 Test #4: offline_imports ..................   Passed    0.03 sec

100% tests passed, 0 tests failed out of 4

Total Test time (real) =   0.29 sec
```

The inventory must be exactly `make_tiny_gguf`, `core`, `secure_heap`, `offline_imports`; `OMNI_BUILD_TESTS=ON` is explicit, an existing build directory is refused, and `ctest --no-tests=error` is used. A separate empty-test-directory control returned **8**, not green. No cache or `continue-on-error` was added. Push and PR branch filters cover both `main` and `core-offline-runtime`, with exactly the requested paths, plus manual dispatch. YAML and these structural properties were checked locally.

#### Dependency fingerprint: an important measured correction

The required commit and required SHA256 remain unchanged. However, verifying the committed blob exposed a line-ending dependency absent from the brief:

| Header representation | SHA256 |
| --- | --- |
| `git show 869034b4:include/llama.h` (LF) | `d5cf9203bea63b575e76cba4881f29cfd1b611451578b01582b75b72ecbb04bc` |
| Existing Windows checkout (CRLF), and LF blob converted to CRLF | `edea14f935e2729d157e063b1ebdde3deeca9714389aaf0d5a20424b6b98a5ff` |

Verified byte equality after CRLF -> LF; there is no content change beyond line endings. A clean Linux checkout would otherwise fail both fingerprints. Therefore the workflow explicitly normalizes **only** `include/llama.h` to CRLF after the pinned `actions/checkout@v4` and before the independent SHA256 step. Every resulting byte must match the required checksum. CMake still never fetches llama.cpp and was not modified. The ignored local dependency was supplied from the existing local checkout; main's dependency files were not edited.

#### Filesystem evidence

Local `/tmp`: `stat -f` reports **`ext2/ext3 ef53`**; `findmnt -T /tmp` reports **`ext4   /dev/sdd`**. Magic `0xef53` is the `EXT4_SUPER_MAGIC` allowlist case. M5 removes that case and makes `core` fail, then restores it and passes.

**Hosted `ubuntu-latest` filesystem is not confirmed.** No workflow has been pushed or dispatched, so I cannot turn local WSL evidence into a hosted-run observation. The workflow prints `stat -f -c 'Fixture /tmp filesystem = %T (magic 0x%t)' /tmp`; its first hosted run must supply this remaining evidence. The fixture still copies to `/tmp`, and a disallowed filesystem fails the runtime check. Do not cite this report as a hosted green CI run.

#### Mutations and controls

All replacement targets were asserted present exactly once. Originals were copied to external scratch directories (`/tmp/omniagent-brief04.kLTCQM` and the Windows temporary directory for M6), restored from those copies, and SHA256-verified. Source/header mutation restores were followed by rebuilding and all four CTest targets passing.

| Check | What went red | What stayed green / restored control |
| --- | --- | --- |
| Extra M0: generated fixture output replaced by a directory | `make_tiny_gguf`, CTest exit 8, `IsADirectoryError` from the actual writer | Only fixture target selected for failure; binary fixture restored from scratch and checksum-verified; full 4/4 green afterward. |
| M1: replace wiping call in `secure_heap.cpp` with `(void)memory` | `secure_heap`; CTest exit 8, 1/4 failed | `make_tiny_gguf`, `core`, `offline_imports` passed; restore + build + 4/4 passed. |
| M2: change first header byte `#` -> `!` | Workflow SHA256 exits **1 first**; independently invoked CMake fingerprint then exits **1**, “Unsupported llama.cpp API” | Existing test binaries still pass 4/4 without rebuilding, demonstrating why testing a stale build alone is insufficient. Restored header, rebuild and 4/4 pass. |
| M3: reference real `dlopen` from the test executable | Build succeeds; `offline_imports` fails with “Runtime imports a forbidden networking or dynamic-loading function”; CTest exits 8 | Fixture, `core`, `secure_heap` pass. Restore + build + 4/4 pass. An earlier incorrectly C++-linked probe failed to link; it was restored and was **not** counted as import-check evidence. The corrected C-linkage run is the evidence. |
| M4: remove `part == ".."` refusal | `core`, CTest exit 8: `engine.load("/tmp/../tmp/model.gguf") == Error::invalid_path` fails | Fixture, heap and imports pass. Restore + build + 4/4 pass. |
| M5: remove `EXT4_SUPER_MAGIC` from filesystem allowlist | `core`, CTest exit 8: the parent filesystem refusal changes the final-symlink assertion from expected `io` to `invalid_path` | Fixture, heap and imports pass. Local type `ef53` recorded independently. Restore + build + 4/4 pass. This is local WSL evidence, not hosted-run evidence. |
| M6: remove workflow's Test step | **Nothing in the repository notices.** | Main's ruff, mypy and all **633 Python tests** pass while the new worktree workflow lacks its CTest execution. Inventory alone could still pass. Workflow restored from external copy and checksum-verified. |

M6 means **nothing yet guards the gate itself against deletion of its execution step**. There is no committed workflow-contract test noticing that deletion. The one-off external YAML validation performed after restoration is not a repository guard or branch-protection rule.

Restore checksums:

```text
M1 secure_heap.cpp: 5cd61a804f594ca0fce7f545c7dcedc836b2baf1e329c00291e7ae9d2161255d
M2 llama.h:         edea14f935e2729d157e063b1ebdde3deeca9714389aaf0d5a20424b6b98a5ff
M3 core_tests.cpp:  b8669c753b5061c62fd49f2e81d7e12bab413bd17d3067bee95f74d253bf3aba
M4 local_file.cpp:  740c246552394663e8f5054aeb01f45c11ac18ad92a0fb61805f3387ed043447
M5 local_file.cpp:  740c246552394663e8f5054aeb01f45c11ac18ad92a0fb61805f3387ed043447
M6 core.yml:        d467c80810e2be060ba4c4391169a3026deb67465965979287ca600f41c1f13e
```

M3's checksum is the test source at mutation time; subsequent final changes independently test group/world audit permissions and tidy indentation. These later test-only changes were rebuilt and passed. No runtime claim failed in the unmutated source, so no runtime fix was made.

#### Claim-to-test map

README lines refer to the README in implementation commit `ef2ab18`. Test locations below refer to the same commit. “Core” subcases are assertions in the `core` CTest executable, not additional registered targets.

| Claim | README line | Named test/check | Why it can fail / evidence |
| --- | --- | --- | --- |
| CMake requires supplied source; header fingerprint rejects changes | 10 | Configure controls; CI `Verify llama.cpp header` | Missing dependency exits 1 without a fetch; M2 exits 1 at both the separate SHA256 check and CMake. CMake download paths remain disabled; CMake was not edited. |
| CRLF fingerprint representation | 21 | CI normalization and SHA256 steps | Executed the exact workflow steps locally; LF blob normalized to CRLF matches the required SHA256. |
| Path syntax rejection: relative, URI, drive/backslash, colon, NUL, empty components, dot/traversal | 66 | `core` | `omniagent-core/tests/core_tests.cpp:81`; `omniagent-core/tests/core_tests.cpp:88`: exact error assertions; new direct boundary tests exercise model and audit modes. M4 fails on traversal. |
| Parent/final symlinks, FIFO, procfs refused; fixture copied to /tmp | 68 | `core` | `omniagent-core/tests/core_tests.cpp:64`; `omniagent-core/tests/core_tests.cpp:94`; symlink/FIFO assertions immediately follow. M5 proves dependence on the ext-family allowance. |
| Malformed GGUF and model size limits | 69 | `core` | `omniagent-core/tests/core_tests.cpp:102`; `omniagent-core/tests/core_tests.cpp:112`: explicit invalid_model/model_too_large assertions. |
| Invalid context config and thread counts 0/257 | 70 | `core` | `omniagent-core/tests/core_tests.cpp:105`; `omniagent-core/tests/core_tests.cpp:107`: explicit invalid_config checks, including newly added thread cases. |
| Prompt/context/output limits and entire partial-output span wiping | 71 | `core` | `omniagent-core/tests/core_tests.cpp:128`; `omniagent-core/tests/core_tests.cpp:131`: partial-output overflow must zero both bytes; prompt/context checks follow. |
| Ten exact repeated outputs, forty requests on four shared-engine threads | 73 | `core` | `omniagent-core/tests/core_tests.cpp:119`; `omniagent-core/tests/core_tests.cpp:146`: compares aaa and requires correct == 40. |
| EOS and token-limit stops differ | 74 | `core` | `omniagent-core/tests/core_tests.cpp:122`; `omniagent-core/tests/core_tests.cpp:193`: exact stop enum, token and byte counts. |
| Cancellation, successful reuse and immediate cleanup | 75 | `core` | `omniagent-core/tests/core_tests.cpp:198`; `omniagent-core/tests/core_tests.cpp:217`: cancelled error, zero output, newly checked clean state before reuse, then successful generation. |
| Concurrent unload and repeated unload | 76 | `core` | `omniagent-core/tests/core_tests.cpp:156`; `omniagent-core/tests/core_tests.cpp:225`: repeated success, unloaded state, and only allowed race outcomes. |
| Zero token/piece scratch and exposed logits; empty KV sequence positions | 77 | `core` / `EngineTestAccess::clean` | `omniagent-core/tests/core_tests.cpp:30`: all scratch/logit elements checked, KV maximum sequence position == -1. Called after repeated generation and immediately after cancellation. Does not inspect raw KV bytes. |
| Group/world-readable, hardlinked and final-symlink audit refusal | 79 | `core` | `omniagent-core/tests/core_tests.cpp:181`: newly separate 0640 and 0604 cases; hardlink and symlink checks follow. |
| Exact numeric audit schema and retained multiple records | 80 | `core` | `omniagent-core/tests/core_tests.cpp:169`: sscanf parses all three fields; %n must reach end of each line, status is bounded, and >40 records survive. This is not proof of UID ownership enforcement or O_APPEND semantics on reopening. |
| Audit write failure returns log_io and wipes output | 81 | `core` | `omniagent-core/tests/core_tests.cpp:238`: read-only descriptor forces failure; verifies log_io, whole-span zeroing and clean request state. |
| Backend abort and terminate exit 70 without diagnostic output | 103 | `core` | `omniagent-core/tests/core_tests.cpp:245`: two child processes, a pipe captures stdout/stderr, EOF with no bytes and exit 70 required; abort is given private text and an address. |
| Zero before release including padding, realloc, array and aligned scalar delete | 83 | `secure_heap` | `omniagent-core/tests/secure_heap_tests.cpp:22`; `omniagent-core/tests/secure_heap_tests.cpp:36`: observer scans full allocation before real free, failures must be 0, releases >=5. M1 fails this target. |
| Failed realloc preserves the original allocation | 85 | `secure_heap` | `omniagent-core/tests/secure_heap_tests.cpp:60`: SIZE_MAX allocation failure must preserve every usable byte of original block (strengthened from checking one byte). |
| Plugin initialization and explicit load cannot execute local probe | 87 | `core` | `omniagent-core/tests/core_tests.cpp:68`; `omniagent-core/tests/core_tests.cpp:116`: null load result and absent constructor marker. |
| Enumerated forbidden binary imports | 89 | `offline_imports` | `tests/check_imports.cmake:1-11` inspects undefined binary imports; M3 builds successfully with a real C-linkage dlopen reference and this target fails. |
| Deterministic synthetic fixture and real inference | 110 | `make_tiny_gguf` + `core` | Python-only generator produces GGUFs consumed by repeated inference/EOS checks. Extra M0 makes its output path a directory and this target fails with IsADirectoryError. |

Caller responsibilities, supported-build instructions, and explicit limits are not additional promises of isolation or erasure. The paragraph beginning “This contract covers owned heap buffers” was preserved verbatim. Its numeric limits are exercised by the prompt/context/output/model/thread checks above; fatal/terminate behavior has two child-process tests. No unsupported erasure, peak-RAM, crash or isolation guarantee was introduced.

Untested original claims were **struck**, not left as vague security assurances. The new “Tested security boundaries” section records specific observations separately:

| Original README lines (cfbde93) | Untested claim removed | Resolution |
| --- | --- | --- |
| 3-7 | CPU-only and complete absence of HTTP/client/server/socket/downloader/RPC/cloud/dynamic-loader code | Struck blanket absence claim. Retained only named plugin-probe and enumerated undefined-import observations, including their limits. |
| 11-14 | Windows/macOS/musl always fail closed instead of disabling clearing | Struck cross-platform guarantee; only Linux/WSL was run. |
| 30-34 | All global delete variants, mandatory interface behavior, silent process-wide hooks and effects | Struck universal/process-wide guarantees; concrete heap cases and abort/terminate output are tested. Dedicated-process/linking directions remain caller guidance. |
| 46, 62, 64-68 | Static diagnostic guarantee, NUL/UTF-8 behavior, greedy finite-logit validation, encoder/decoder rejection, FILE* loading, no mmap/lazy/GPU/MTP, all quantizations | Struck these unrun assertions. Example no longer claims a static diagnostic or lack of a trailing NUL; exact fixture output is separately tested. |
| 70-76 | Preallocation, batching/one-token scheduling, reserve-before-decode, oversized token-piece handling, UTF-8 truncation | Struck mechanism and unexercised edge guarantees. The actual span overflow/context/EOS assertions remain specific. |
| 79-89 | Universal openat/O_NOFOLLOW/nonblocking/regular-file mechanism and full ext4/XFS/Btrfs/tmpfs/ramfs/overlayfs allowlist plus NFS/SMB/FUSE/9p/unknown/WSL-mount refusal | Struck universal filesystem/platform claims; retained tested syntax, symlink, FIFO and procfs cases. M5 establishes only the local ext-family dependency. |
| 93-99 | Current-UID ownership enforcement, O_APPEND-only/reopen semantics, no default log creation, all upstream log silence, never leaking across every possible failure | Struck these blanket guarantees. Added exact record-schema and partial-output tests; separate group-only/world-only permission assertions now fail independently. Audit write failure and fatal-output checks remain concrete. |
| 102-104 | One-mutex proof for all operations, separate engines concurrent, exact atomic-cancel/queued-command semantics | Struck implementation and independent-engine guarantees; retain measured shared-engine requests/cancellation/unload outcomes. |
| 105-110 | Synchronize and clear all KV/recurrent bytes, destructor context-before-model order, cleanup on every error/exception/partial batch | Struck universal cleanup/order guarantees. The test now checks immediate cleanup after cancellation but does not synchronize cancellation to a known completed prefill batch or inspect all KV bytes. |
| 111-115 | All delete variants and all CPU scratch/container/backend-output/weight allocations follow wiping paths; fence/store mechanism | Struck universal backend-allocation coverage. Retain only allocations observed by `secure_heap`; strengthened failed-realloc preservation checks every usable byte. |
| 135-142 | Guaranteed abort during a completed partial prefill and observer-exclusivity build guarantee | Struck unproven scope; cancellation/reuse and concrete allocation observations are recorded. |

This is a claim-coverage review of the README, not an exhaustive security audit of llama.cpp or proof against direct syscalls, hidden/static network code, malicious filesystems or arbitrary hostile GGUFs. No source/include boundary was altered.

#### Python gates from main

Run with `D:\code-project\OmniAgent\.venv\Scripts\python.exe`, working directory `D:\code-project\OmniAgent`, with no extra `-q`:

```text
-m ruff check .
All checks passed!

-m mypy
Success: no issues found in 42 source files

-m pytest
633 passed in 11.83s
```

All three exited 0. They also supplied M6's green controls. No Python source, `tools.py`, `sandbox.py` or existing `ci.yml` was edited.

#### Commit scope proof and claims refused

`git show --stat` for the implementation:

```text
ef2ab18 ci(core): a fourth gate that builds the native runtime and runs its tests
 .github/workflows/core.yml                 |  66 ++++++++++++
 omniagent-core/README.md                   | 161 +++++++++++------------------
 omniagent-core/tests/core_tests.cpp        |  77 ++++++++++----
 omniagent-core/tests/secure_heap_tests.cpp |   4 +-
 4 files changed, 187 insertions(+), 121 deletions(-)
```

`git diff --exit-code cfbde93 HEAD -- omniagent-core/src omniagent-core/include` returned 0. The commit contains no runtime source or header changes. The separate report commit adds only this brief with this Result section.

I refuse to claim: a hosted `ubuntu-latest` run or its actual temporary-filesystem type; protection against someone deleting the gate; complete absence of networking merely from imports; byte-complete backend KV/weight erasure or tracing every backend allocation; guaranteed cancellation after a completed partial batch; all-platform fail-closed behavior; or full dependency-source authenticity from a single header fingerprint. These are explicit limits, not green checks. The branch remains local and unpushed for the project manager.

---

## PM verification — 2026-10-23, `ef2ab18`

Re-run, not read. The engineer's report is a claim; what follows was produced
by commands in this session.

### I built it and tested it myself

In WSL Ubuntu, a fresh build directory on ext4, source from this worktree,
dependency from the main checkout:

```
configure: 5 s
build: 82 s
1/4 make_tiny_gguf ... Passed   0.06 sec
2/4 core ............. Passed   0.12 sec
3/4 secure_heap ...... Passed   0.00 sec
4/4 offline_imports .. Passed   0.02 sec
100% tests passed, 0 tests failed out of 4
```

Toolchain: cmake 3.28.3, g++ 13.3.0 (Ubuntu 13.3.0), Python 3.12.3. **This
replaces the 2026-10-11 log as the current evidence for this code.** The
engineer measured 12 s + 96 s; I measured 5 s + 82 s building to `/tmp`
instead of `/mnt/d`, which is the difference.

`/tmp` in the local distribution is `ext2/ext3 magic 0xef53`, which is
`EXT4_SUPER_MAGIC`. That matches the `ef53` in the report and it is why `core`
passes: `tests/core_tests.cpp:63` copies the fixture there before loading it.

### Scope held

`git diff cfbde93 79167c1 --name-only` filtered for
`omniagent-core/(src|include)/` returns **nothing**. The four files touched are
`core.yml`, the core README, `core_tests.cpp` and `secure_heap_tests.cpp`.
`main` is untouched and clean, and its three gates are green on
**633 passed**, `ruff` clean, `mypy` clean over 42 files — unchanged, as
required.

### The fingerprint finding is real, and I proved it a second way

The report's "important measured correction" is correct and it is the most
consequential thing found today. Measured here:

| Form of `include/llama.h` | SHA256 |
| --- | --- |
| the local working tree, a Windows checkout with `core.autocrlf=true` | `edea14f9…a5ff` — **what `CMakeLists.txt:16` demands** |
| the canonical git blob, i.e. what any Linux checkout holds | `d5cf9203bea63b575e76cba4881f29cfd1b611451578b01582b75b72ecbb04bc` |

Prediction written before the run: the LF header hashes to `d5cf9203…`, which
is not the demanded value, so the check must refuse. Replaying
`CMakeLists.txt` lines 15–18 verbatim against the canonical blob:

```
-- computed: d5cf9203bea63b575e76cba4881f29cfd1b611451578b01582b75b72ecbb04bc
CMake Error: Unsupported llama.cpp API: use commit 869034b4bb93a425ea989d30fc3d000f5a461d58
```

**The fingerprint refuses the canonical form of the exact commit it names, and
tells the reader to use the commit they already have.** The pin is an artefact
of one Windows working tree, not of upstream. The 2026-10-11 build passed only
because WSL read `/mnt/d`, which carries the CRLF copy — which is also why my
own build above passed.

So `omniagent-core` as committed **cannot be configured from a clean checkout
on the only platform it supports.** That is a defect in the code, not in the
gate, and the engineer was right to report it rather than fix it.

### Better than the brief asked for

- `ctest --no-tests=error`, so an empty test set fails instead of passing.
- A **test-inventory step** asserting the names are exactly
  `make_tiny_gguf`, `core`, `secure_heap`, `offline_imports`. The brief did not
  ask for this and it answers part of M6: a target that silently disappears is
  now caught. A deleted workflow file still is not.
- `test ! -e omniagent-core/build` before configuring, forcing a fresh build.
- `timeout-minutes` justified in a comment by the measurement behind it.
- An empty-test-directory control returning exit 8 rather than green.
- M2 turned up something the brief did not anticipate: the existing test
  binaries still pass 4/4 without rebuilding after the header changes, which is
  why testing a stale build directory proves nothing.

### What is not established, and the report says so

- **The workflow has never run on `ubuntu-latest`.** The branch is unpushed, so
  every statement about the hosted runner — including its temporary
  filesystem's type, which `src/local_file.cpp:19-25` makes part of the gate —
  is local WSL evidence standing in for hosted evidence. The report refuses to
  claim otherwise, correctly.
- Nothing protects the gate itself from being deleted.
- A single header fingerprint is not dependency authenticity, and the README
  still says so.

### The one thing I would push back on

The workflow step that rewrites `include/llama.h` to CRLF **before** verifying
its checksum. Content equality is still enforced afterwards, the step is
commented, and the README now documents the CRLF expectation — so nothing is
hidden. But a security gate that normalizes its dependency's bytes before
fingerprinting them is the wrong shape for the job, and the defect it works
around stays in place for every human who clones this branch.

It is not the engineer's call to change `CMakeLists.txt`, and the brief did not
grant it. The fingerprint's value is the owner's decision, and it is on the
table as a lettered choice.
