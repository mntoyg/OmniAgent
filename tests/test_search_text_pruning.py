"""``search_text`` must prune a refused branch without changing its output.

The speed is the task and the ordering is the contract. ``MAX_SEARCH_FILES``
is 400 and ``MAX_SEARCH_MATCHES`` is 50, so the candidate order decides which
matches reach the model, and the collected training examples were recorded
against today's order. These three assert the order and the pruning
separately: a golden string, an exact truncated list, and the absence of any
resolution under a branch that was refused at its root.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from sandbox import MAX_FILE_BYTES, SandboxError, Workspace, get_workspace, set_workspace
from tools import search_text

#: Deliberately not a word this repository uses: a fixture needle that also
#: occurred in the tree would make a failure ambiguous.
NEEDLE = "pruneme"


def _install(root: Path) -> Iterator[Workspace]:
    installed = Workspace.at(root)
    original = get_workspace()
    set_workspace(installed)
    yield installed
    set_workspace(original)


@pytest.fixture
def mixed(tmp_path: Path) -> Iterator[Workspace]:
    """One of every kind of candidate the walk has to decide about."""
    root = tmp_path / "work"
    root.mkdir()

    # Two matches in one file, and a third in a subdirectory.
    (root / "top.txt").write_text(f"{NEEDLE} one\nquiet\n{NEEDLE} two\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "nested.txt").write_text(f"{NEEDLE} nested\n", encoding="utf-8")

    # Refused: a dot-directory, and -- the reason this fixture is not just
    # dot-prefixed names -- a denied suffix that no startswith('.') rule sees.
    (root / ".hidden").mkdir()
    (root / ".hidden" / "secret.txt").write_text(f"{NEEDLE} hidden\n", encoding="utf-8")
    (root / "secret.key").write_text(f"{NEEDLE} credential\n", encoding="utf-8")

    # Skipped on measurement, not on admission: over the byte limit, and
    # binary by the tool's own sniff.
    (root / "big.txt").write_text(f"{NEEDLE} big\n" + "x" * MAX_FILE_BYTES, encoding="utf-8")
    (root / "blob.bin").write_bytes(b"\0\0" + NEEDLE.encode() + b" binary\n")

    yield from _install(root)


@pytest.fixture
def crowded(tmp_path: Path) -> Iterator[Workspace]:
    """More matches than the limit, spread over directories that sort."""
    root = tmp_path / "work"
    root.mkdir()
    for directory in ("alpha", "beta", "gamma"):
        (root / directory).mkdir()
        for name in ("f1.txt", "f2.txt"):
            lines = "".join(f"{NEEDLE} {index:02d}\n" for index in range(1, 10))
            (root / directory / name).write_text(lines, encoding="utf-8")
    yield from _install(root)


@pytest.fixture
def crowded_dot(tmp_path: Path) -> Iterator[Workspace]:
    """A refused branch holding thousands of entries, and two admitted files."""
    root = tmp_path / "work"
    root.mkdir()
    (root / "visible.txt").write_text(f"{NEEDLE} here\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "also.txt").write_text(f"{NEEDLE} there\n", encoding="utf-8")

    junk = root / ".junk"
    junk.mkdir()
    (junk / "deep").mkdir()
    for index in range(1_000):
        (junk / f"leaf-{index:04d}.txt").write_text(f"{NEEDLE}\n", encoding="utf-8")
        (junk / "deep" / f"leaf-{index:04d}.txt").write_text(f"{NEEDLE}\n", encoding="utf-8")
    yield from _install(root)


# --------------------------------------------------------------------------- #
# 1. the output does not change, byte for byte
# --------------------------------------------------------------------------- #

#: Captured by running the current implementation against the ``mixed``
#: fixture, not written from belief. Every part of it is a decision the walk
#: makes: ``sub/`` before ``top.txt`` is the global path sort, the two
#: ``top.txt`` lines are in line order, and ``.hidden/``, ``secret.key``,
#: ``big.txt`` and ``blob.bin`` are each absent for a different reason. The
#: count in the header is the number of files measured, which includes the
#: binary file that was opened and then rejected.
GOLDEN = (
    "3 matches for 'pruneme':\n"
    "sub/nested.txt:1: pruneme nested\n"
    "top.txt:1: pruneme one\n"
    "top.txt:3: pruneme two"
)


def test_search_text_output_is_byte_identical(mixed: Workspace) -> None:
    assert search_text(NEEDLE) == GOLDEN


# --------------------------------------------------------------------------- #
# 2. the order under truncation
# --------------------------------------------------------------------------- #

#: The exact matches a truncated search returns, captured from the current
#: implementation. This is the test that catches a walk that yields per
#: directory instead of sorting globally: there are 54 matches and the limit
#: is 50, so the last four are the ones the model never sees.
TRUNCATED: tuple[str, ...] = (
    "alpha/f1.txt:1: pruneme 01",
    "alpha/f1.txt:2: pruneme 02",
    "alpha/f1.txt:3: pruneme 03",
    "alpha/f1.txt:4: pruneme 04",
    "alpha/f1.txt:5: pruneme 05",
    "alpha/f1.txt:6: pruneme 06",
    "alpha/f1.txt:7: pruneme 07",
    "alpha/f1.txt:8: pruneme 08",
    "alpha/f1.txt:9: pruneme 09",
    "alpha/f2.txt:1: pruneme 01",
    "alpha/f2.txt:2: pruneme 02",
    "alpha/f2.txt:3: pruneme 03",
    "alpha/f2.txt:4: pruneme 04",
    "alpha/f2.txt:5: pruneme 05",
    "alpha/f2.txt:6: pruneme 06",
    "alpha/f2.txt:7: pruneme 07",
    "alpha/f2.txt:8: pruneme 08",
    "alpha/f2.txt:9: pruneme 09",
    "beta/f1.txt:1: pruneme 01",
    "beta/f1.txt:2: pruneme 02",
    "beta/f1.txt:3: pruneme 03",
    "beta/f1.txt:4: pruneme 04",
    "beta/f1.txt:5: pruneme 05",
    "beta/f1.txt:6: pruneme 06",
    "beta/f1.txt:7: pruneme 07",
    "beta/f1.txt:8: pruneme 08",
    "beta/f1.txt:9: pruneme 09",
    "beta/f2.txt:1: pruneme 01",
    "beta/f2.txt:2: pruneme 02",
    "beta/f2.txt:3: pruneme 03",
    "beta/f2.txt:4: pruneme 04",
    "beta/f2.txt:5: pruneme 05",
    "beta/f2.txt:6: pruneme 06",
    "beta/f2.txt:7: pruneme 07",
    "beta/f2.txt:8: pruneme 08",
    "beta/f2.txt:9: pruneme 09",
    "gamma/f1.txt:1: pruneme 01",
    "gamma/f1.txt:2: pruneme 02",
    "gamma/f1.txt:3: pruneme 03",
    "gamma/f1.txt:4: pruneme 04",
    "gamma/f1.txt:5: pruneme 05",
    "gamma/f1.txt:6: pruneme 06",
    "gamma/f1.txt:7: pruneme 07",
    "gamma/f1.txt:8: pruneme 08",
    "gamma/f1.txt:9: pruneme 09",
    "gamma/f2.txt:1: pruneme 01",
    "gamma/f2.txt:2: pruneme 02",
    "gamma/f2.txt:3: pruneme 03",
    "gamma/f2.txt:4: pruneme 04",
    "gamma/f2.txt:5: pruneme 05",
)


def test_truncation_keeps_the_sorted_order(crowded: Workspace) -> None:
    result = search_text(NEEDLE)
    header, *lines = result.splitlines()

    assert header.endswith("(stopped at the limit):")
    assert tuple(lines) == TRUNCATED


# --------------------------------------------------------------------------- #
# 3. nothing under a refused branch is resolved
# --------------------------------------------------------------------------- #


def test_a_refused_branch_is_not_resolved(
    crowded_dot: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of the change, asserted on calls rather than on a clock.

    A timing assertion would be flaky on CI. What is actually claimed is that
    the 2,001 entries under ``.junk`` are never named: the branch is refused
    once, at its root, and the walk does not descend.
    """
    # Guard the guard: this proves nothing if the branch were admitted.
    with pytest.raises(SandboxError):
        crowded_dot.resolve(".junk")

    asked: list[str] = []
    original = Workspace.resolve

    def recording(self: Workspace, candidate: str) -> Path:
        asked.append(candidate)
        return original(self, candidate)

    monkeypatch.setattr(Workspace, "resolve", recording)

    result = search_text(NEEDLE)

    assert "visible.txt" in result
    beneath = [candidate for candidate in asked if candidate.startswith(".junk/")]
    assert beneath == [], f"{len(beneath)} paths resolved under a refused branch"
    assert ".junk" in asked, "the branch itself has to be refused, not skipped by name"
    assert len(asked) < 10, f"only the admitted tree should be resolved, not {len(asked)} paths"
