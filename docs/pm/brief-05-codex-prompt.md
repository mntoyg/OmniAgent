# Brief 05 — the paste-ready task for the security engineer

Paste everything below the line. The companion brief is
`docs/pm/brief-05-the-fingerprint-is-the-linux-file.md`; `## Result` goes there.

---

You are the **security engineer** on OmniAgent. Work in the existing worktree:

```
cd ../OmniAgent-core
```

That is `core-offline-runtime`. The fullstack engineer is on `main` in
`D:\code-project\OmniAgent` — **do not switch its branch** and do not edit
anything there.

**Read `docs/pm/brief-05-the-fingerprint-is-the-linux-file.md` and execute
it.** You found this defect in brief 04 and reported it instead of fixing it,
which was the right call. The owner has now decided the fix.

## The decision you are implementing

`omniagent-core/CMakeLists.txt:16` demands
`edea14f935e2729d157e063b1ebdde3deeca9714389aaf0d5a20424b6b98a5ff`, which is
the hash of `include/llama.h` **in a Windows CRLF working tree**. The canonical
git blob that every Linux checkout holds is
`d5cf9203bea63b575e76cba4881f29cfd1b611451578b01582b75b72ecbb04bc`.

The fingerprint becomes the LF value. The workflow's CRLF normalization step
goes. CMake does **not** normalize before hashing — that option was considered
and rejected, because the fingerprint is meant to be exact.

## Order of work — this part is not optional

**Get a working LF build before you change the hash.** The moment you flip the
value, the `/mnt/d` path everything has been built from stops configuring and
you will have nothing to verify against.

```sh
git clone /mnt/d/code-project/OmniAgent/models/llama.cpp /tmp/llama-lf
sha256sum /tmp/llama-lf/include/llama.h
```

No network; it clones the copy already on disk, and WSL's git has no
`autocrlf`, so that tree is LF. **Confirm the hash is `d5cf9203…` before
trusting it.** If it is not, stop and report — everything rests on it.

Then configure against `/tmp/llama-lf` with the **current** hash still in place
and watch it be refused. That is your "watch it fail first" step, and it is the
behaviour you are about to invert. Paste that refusal.

## Files you may touch

`omniagent-core/CMakeLists.txt` · `.github/workflows/core.yml` ·
`omniagent-core/README.md`

## Files you may not touch

`omniagent-core/src/**` · `omniagent-core/include/**` ·
`omniagent-core/tests/**` · `models/**` · `tools.py` · `sandbox.py` ·
`.github/workflows/ci.yml` · anything on `main` · `NEXT_CHAT.md` · `docs/`
except your `## Result`.

Brief 04 named only what was allowed and never said whether `CMakeLists.txt`
was forbidden. That ambiguity was mine and it is why a defect got worked around
instead of reported. **If a file is in neither list, ask rather than decide.**

## The three changes

1. **`CMakeLists.txt`** — the LF hash, and an error message that names both
   things a mismatch could mean. **Print the computed hash.** The current
   message says "use commit 869034b4…" when you already have that commit, and
   that misdirection is why this sat unnoticed for twelve days. The new message
   must mention LF, CRLF, `core.autocrlf=true` and reading a Windows checkout
   through `/mnt`.
2. **`core.yml`** — delete the "Reproduce the fingerprint's line endings" step
   entirely, update the `sha256sum --check` value, and **add a step that proves
   the fingerprint can still fail**: copy the header to a throwaway tree,
   convert it to CRLF, configure against that tree, assert the configure
   **fails**. Temporary directory only; `git status` clean afterwards.
   Configure-only — the fingerprint fires before anything compiles, so it costs
   seconds.
3. **`README.md`** — the paragraph claiming the fingerprint expects CRLF and
   that CI converts LF to CRLF is now false. Replace it with the LF hash and
   say plainly that a CRLF working tree is refused and why. **Keep** the
   sentence that this is not verification of the complete dependency source.

## Controls and mutations

Scratch copies outside the repository, restore from them, never
`git checkout --` alone, and assert the target string is present before
replacing it.

| # | Mutation / control | Expected |
| --- | --- | --- |
| C1 | Configure against `/tmp/llama-lf` after the change | **succeeds** |
| C2 | Configure against the CRLF tree on `/mnt/d` after the change | **refused**, message names line endings |
| M1 | Change one byte of *content*, not a line ending, in the LF header | refused, printed `found:` hash differs |
| M2 | Put `edea14f9…` back in `CMakeLists.txt` | C1 breaks — proves C1 depends on the new value |
| M3 | Delete the new CI refusal step | nothing locally — say what would notice, and if nothing would, say so |

Then build and `ctest` fully against `/tmp/llama-lf`: **4/4 must pass.** For
reference, the project manager measured configure 5 s, build 82 s, ctest
0.20 s on `/mnt/d` with cmake 3.28.3 and g++ 13.3.0. An LF tree on ext4 should
be no slower. **If the tests fail against an LF checkout, that is a much larger
finding than this brief — stop and report it.**

## Environment rules, each already paid for once

- Windows is refused at configure time by design. Build under WSL Ubuntu.
- **A command over 600 seconds is backgrounded and dies with the session.**
  Start the build in the background deliberately.
- Python gates from the **main checkout**, full path
  `.venv\Scripts\python.exe`, **never your own `-q`**. Expect **633 passed**.
- `cmd.exe` reads `/` as a switch — backslashes there.
- No pull request. No amending existing commits.

## Commit

```
git add omniagent-core/CMakeLists.txt .github/workflows/core.yml omniagent-core/README.md
git commit -m "fix(core): pin the fingerprint to the header Linux actually checks out"
```

`git show --stat` must list exactly those three files. **Do not push** — the
project manager pushes the branch after verifying, which will be the first time
this workflow has ever run on `ubuntu-latest`.

Append `## Result`: the LF clone's hash, the refusal you watched first, C1, C2,
M1, M2, M3, the full ctest output, the Python gate results, the commit hash, and
**anything you refuse to claim**. Commit that too, then stop.

## The one thing that would make all of this wrong

Making the build work again while the fingerprint loses the ability to refuse
anything — normalized before hashing, downgraded to a warning, or a CI step
that reports success because the configure it tested never ran. C2, M1 and M2
exist to show the check still bites. If you cannot produce a refusal, the
fingerprint is decoration and this brief has made the repository less safe.
