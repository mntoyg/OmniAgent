"""A held-out run record contains measurements, never the answer key."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from eval_scoring import Verdict
from holdout_eval import (
    PROJECT,
    _append_question_record,
    _tree_clean,
    question_record,
)


def test_question_record_has_only_index_tools_steps_and_verdict_booleans() -> None:
    verdict = Verdict(
        checkable=True,
        correct=True,
        tool_expected=True,
        right_tool=False,
        honest_expected=False,
        admitted=False,
    )

    record = question_record(7, verdict, 4, ["read_file", "search_text"])

    assert record == {
        "index": 7,
        "tools": ["read_file", "search_text"],
        "steps": 4,
        "checkable": True,
        "correct": True,
        "tool_expected": True,
        "right_tool": False,
        "honest_expected": False,
        "admitted": False,
    }
    assert not {"question", "text", "expect", "expectation"} & record.keys()


def test_appended_run_record_carries_cleanliness_separately(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    measurement = question_record(
        7,
        Verdict(True, True, True, True, True, True),
        4,
        ["read_file"],
    )

    _append_question_record(measurement, "fixture-model", "abc1234", True, path)

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["clean"] is True
    assert stored["commit"] == "abc1234"
    assert "clean" not in measurement


def test_tree_cleanliness_is_unknown_when_git_status_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = Mock(return_value=Mock(stdout="", returncode=0))
    monkeypatch.setattr(subprocess, "run", runner)

    assert _tree_clean() is True
    command = runner.call_args.args[0]
    options = runner.call_args.kwargs
    assert command == ["git", "-C", str(PROJECT), "status", "--porcelain"]
    assert options["check"] is True
    assert options["timeout"] == 10
    assert "shell" not in options

    runner.return_value = Mock(stdout=" M scripts/holdout_eval.py\n", returncode=0)
    assert _tree_clean() is False

    runner.side_effect = FileNotFoundError("git unavailable")
    assert _tree_clean() == "unknown"
