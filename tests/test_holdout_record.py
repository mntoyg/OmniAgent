"""A held-out run record contains measurements, never the answer key."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from eval_scoring import Verdict
from holdout_eval import question_record


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
