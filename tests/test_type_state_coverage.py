"""
Coverage tests for all ADO work item types and states found in this project.

Work item counts (as of pre-migration snapshot):
  Bug: Active×5, Closed×849, In Code Review×2, In Test×2, New×345
  Epic: Active×2, New×1
  Feature: Closed×12, New×1
  Feature Request: Active×1, Completed×13, Declined×9, New×35
  Issue: Active×1
  Task: Active×19, Closed×717, New×117, Removed×18
  Test Case: Design×12
  Test Plan: Active×2
  Test Suite: Completed×3, In Progress×3
  User Story: Active×14, Awaiting Test×2, Closed×281, In Code Review×2, New×180, Removed×18

  How to run?
    1. Install pytest: `pip install pytest`
    2. Run this test file: `pytest tests/test_type_state_coverage.py`
    3. All tests should pass. If any fail, investigate the failure and fix the
"""
import sys
import os

# Allow running from the repo root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapper import (
    resolve_github_type,
    resolve_github_issue_type_name,
    build_labels,
    should_close,
)
from config import STATE_LABELS, WORK_ITEM_TYPE_LABELS, CLOSED_STATES
from setup.setup_github import LABELS_TO_CREATE, _REQUIRED_LABELS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(wi_type: str, state: str, **extra_fields) -> dict:
    """Build a minimal work item dict with the given type and state."""
    fields = {
        "System.WorkItemType": wi_type,
        "System.State":        state,
        **extra_fields,
    }
    return {"id": 99999, "fields": fields}


def _make_task_with_scheduling(state: str) -> dict:
    return _make_item(
        "Task",
        state,
        **{"Microsoft.VSTS.Scheduling.OriginalEstimate": 8},
    )


def _make_feature_user_story(wi_type: str, state: str) -> dict:
    """Task or User Story with NO scheduling fields (maps to type: feature)."""
    return _make_item(wi_type, state)


VALID_GITHUB_ISSUE_TYPES = {"Bug", "Task", "Feature"}

# ---------------------------------------------------------------------------
# All (type, state) pairs present in the ADO project
# ---------------------------------------------------------------------------

ALL_TYPE_STATE_PAIRS = [
    # Bug
    ("Bug", "Active"),
    ("Bug", "Closed"),
    ("Bug", "In Code Review"),
    ("Bug", "In Test"),
    ("Bug", "New"),
    # Epic
    ("Epic", "Active"),
    ("Epic", "New"),
    # Feature (ADO native type)
    ("Feature", "Closed"),
    ("Feature", "New"),
    # Feature Request
    ("Feature Request", "Active"),
    ("Feature Request", "Completed"),
    ("Feature Request", "Declined"),
    ("Feature Request", "New"),
    # Issue
    ("Issue", "Active"),
    # Task
    ("Task", "Active"),
    ("Task", "Closed"),
    ("Task", "New"),
    ("Task", "Removed"),
    # Test Case
    ("Test Case", "Design"),
    # Test Plan
    ("Test Plan", "Active"),
    # Test Suite
    ("Test Suite", "Completed"),
    ("Test Suite", "In Progress"),
    # User Story
    ("User Story", "Active"),
    ("User Story", "Awaiting Test"),
    ("User Story", "Closed"),
    ("User Story", "In Code Review"),
    ("User Story", "New"),
    ("User Story", "Removed"),
]

# States that should cause a GitHub issue to be closed, per type
EXPECTED_CLOSED: set[tuple[str, str]] = {
    ("Bug",            "Closed"),
    ("Feature",        "Closed"),
    ("Feature Request","Completed"),
    ("Feature Request","Declined"),
    ("Epic",           "Closed"),
    ("Issue",          "Closed"),
    ("Task",           "Closed"),
    ("Task",           "Removed"),
    ("Test Case",      "Closed"),
    ("Test Plan",      "Closed"),
    ("Test Suite",     "Completed"),
    ("User Story",     "Closed"),
    ("User Story",     "Removed"),
}


# ===========================================================================
# 1. resolve_github_type — never returns "type: unknown" for known types
# ===========================================================================

class TestResolveGithubType:

    def test_bug_returns_type_bug(self):
        item = _make_item("Bug", "Active")
        assert resolve_github_type(item) == "type: bug"

    def test_task_with_scheduling_returns_type_task(self):
        item = _make_task_with_scheduling("Active")
        assert resolve_github_type(item) == "type: task"

    def test_task_without_scheduling_returns_type_feature(self):
        item = _make_item("Task", "Active")
        assert resolve_github_type(item) == "type: feature"

    def test_user_story_returns_type_user_story(self):
        item = _make_item("User Story", "Active")
        assert resolve_github_type(item) == "type: user-story"

    def test_epic_returns_type_epic(self):
        item = _make_item("Epic", "Active")
        assert resolve_github_type(item) == "type: epic"

    def test_feature_returns_type_feature(self):
        # ADO native "Feature" type (not Task misclassified as Feature)
        item = _make_item("Feature", "New")
        assert resolve_github_type(item) == "type: feature"

    def test_feature_request_returns_type_feature_request(self):
        item = _make_item("Feature Request", "New")
        assert resolve_github_type(item) == "type: feature-request"

    def test_issue_returns_type_ado_issue(self):
        item = _make_item("Issue", "Active")
        assert resolve_github_type(item) == "type: ado-issue"

    def test_test_case_returns_type_test_case(self):
        item = _make_item("Test Case", "Design")
        assert resolve_github_type(item) == "type: test-case"

    def test_test_plan_returns_type_test_plan(self):
        item = _make_item("Test Plan", "Active")
        assert resolve_github_type(item) == "type: test-plan"

    def test_test_suite_returns_type_test_suite(self):
        item = _make_item("Test Suite", "In Progress")
        assert resolve_github_type(item) == "type: test-suite"

    def test_no_known_type_returns_type_unknown(self):
        item = _make_item("SomeFutureType", "New")
        assert resolve_github_type(item) == "type: unknown"

    def test_no_unknown_labels_for_all_known_types(self):
        """None of the actual ADO types should produce 'type: unknown'."""
        known_types = list(WORK_ITEM_TYPE_LABELS.keys())
        for wi_type in known_types:
            item = _make_item(wi_type, "New")
            label = resolve_github_type(item)
            assert label != "type: unknown", (
                f"resolve_github_type returned 'type: unknown' for '{wi_type}'"
            )


# ===========================================================================
# 2. resolve_github_issue_type_name — always returns a valid GitHub type
# ===========================================================================

class TestResolveGithubIssueTypeName:

    def test_bug_returns_Bug(self):
        assert resolve_github_issue_type_name(_make_item("Bug", "New")) == "Bug"

    def test_task_with_scheduling_returns_Task(self):
        assert resolve_github_issue_type_name(_make_task_with_scheduling("New")) == "Task"

    def test_task_without_scheduling_returns_Feature(self):
        assert resolve_github_issue_type_name(_make_item("Task", "New")) == "Feature"

    def test_user_story_returns_Feature(self):
        assert resolve_github_issue_type_name(_make_item("User Story", "New")) == "Feature"

    def test_epic_returns_Feature(self):
        assert resolve_github_issue_type_name(_make_item("Epic", "New")) == "Feature"

    def test_feature_ado_type_returns_Feature(self):
        assert resolve_github_issue_type_name(_make_item("Feature", "New")) == "Feature"

    def test_feature_request_returns_Feature(self):
        assert resolve_github_issue_type_name(_make_item("Feature Request", "New")) == "Feature"

    def test_issue_returns_Bug(self):
        assert resolve_github_issue_type_name(_make_item("Issue", "Active")) == "Bug"

    def test_test_case_returns_Task(self):
        assert resolve_github_issue_type_name(_make_item("Test Case", "Design")) == "Task"

    def test_test_plan_returns_Task(self):
        assert resolve_github_issue_type_name(_make_item("Test Plan", "Active")) == "Task"

    def test_test_suite_returns_Task(self):
        assert resolve_github_issue_type_name(_make_item("Test Suite", "In Progress")) == "Task"

    def test_all_known_types_return_valid_github_issue_type(self):
        """Every known ADO type must map to one of Bug / Task / Feature."""
        for wi_type in WORK_ITEM_TYPE_LABELS:
            result = resolve_github_issue_type_name(_make_item(wi_type, "New"))
            assert result in VALID_GITHUB_ISSUE_TYPES, (
                f"'{wi_type}' → '{result}' is not a valid GitHub issue type"
            )


# ===========================================================================
# 3. STATE_LABELS — every observed state has an entry
# ===========================================================================

class TestStateLabelCoverage:

    ALL_OBSERVED_STATES = {
        # Bug
        "Active", "Closed", "In Code Review", "In Test", "New",
        # Epic / Feature / Feature Request
        "Completed", "Declined",
        # Task
        "Removed",
        # Test Case
        "Design",
        # Test Suite
        "In Progress",
        # User Story
        "Awaiting Test",
        # Shared
        "Resolved", "Done", "Open",
    }

    def test_all_observed_states_have_a_label(self):
        missing = [s for s in self.ALL_OBSERVED_STATES if s not in STATE_LABELS]
        assert not missing, f"States missing from STATE_LABELS: {missing}"

    def test_in_code_review_label(self):
        assert STATE_LABELS["In Code Review"] == "state: in-code-review"

    def test_in_test_label(self):
        assert STATE_LABELS["In Test"] == "state: in-test"

    def test_completed_label(self):
        assert STATE_LABELS["Completed"] == "state: completed"

    def test_declined_label(self):
        assert STATE_LABELS["Declined"] == "state: declined"

    def test_awaiting_test_label(self):
        assert STATE_LABELS["Awaiting Test"] == "state: awaiting-test"

    def test_design_label(self):
        assert STATE_LABELS["Design"] == "state: design"


# ===========================================================================
# 4. should_close — correct for all type×state pairs in the dataset
# ===========================================================================

class TestShouldClose:

    def test_bug_closed_state_closes(self):
        assert should_close(_make_item("Bug", "Closed")) is True

    def test_bug_active_state_stays_open(self):
        assert should_close(_make_item("Bug", "Active")) is False

    def test_bug_in_code_review_stays_open(self):
        assert should_close(_make_item("Bug", "In Code Review")) is False

    def test_bug_in_test_stays_open(self):
        assert should_close(_make_item("Bug", "In Test")) is False

    def test_task_closed_closes(self):
        assert should_close(_make_task_with_scheduling("Closed")) is True

    def test_task_removed_closes(self):
        assert should_close(_make_task_with_scheduling("Removed")) is True

    def test_task_active_stays_open(self):
        assert should_close(_make_task_with_scheduling("Active")) is False

    def test_feature_request_completed_closes(self):
        assert should_close(_make_item("Feature Request", "Completed")) is True

    def test_feature_request_declined_closes(self):
        assert should_close(_make_item("Feature Request", "Declined")) is True

    def test_feature_request_active_stays_open(self):
        assert should_close(_make_item("Feature Request", "Active")) is False

    def test_feature_request_new_stays_open(self):
        assert should_close(_make_item("Feature Request", "New")) is False

    def test_test_suite_completed_closes(self):
        assert should_close(_make_item("Test Suite", "Completed")) is True

    def test_test_suite_in_progress_stays_open(self):
        assert should_close(_make_item("Test Suite", "In Progress")) is False

    def test_user_story_closed_closes(self):
        assert should_close(_make_item("User Story", "Closed")) is True

    def test_user_story_removed_closes(self):
        assert should_close(_make_item("User Story", "Removed")) is True

    def test_user_story_awaiting_test_stays_open(self):
        assert should_close(_make_item("User Story", "Awaiting Test")) is False

    def test_user_story_in_code_review_stays_open(self):
        assert should_close(_make_item("User Story", "In Code Review")) is False

    def test_epic_active_stays_open(self):
        assert should_close(_make_item("Epic", "Active")) is False

    def test_test_case_design_stays_open(self):
        assert should_close(_make_item("Test Case", "Design")) is False

    def test_all_pairs_match_expected(self):
        """
        Cross-check every observed (type, state) pair against the expected
        closed/open classification table.
        """
        failures = []
        for wi_type, state in ALL_TYPE_STATE_PAIRS:
            item = _make_item(wi_type, state)
            # Tasks need scheduling fields to be treated as real tasks
            if wi_type == "Task":
                item["fields"]["Microsoft.VSTS.Scheduling.OriginalEstimate"] = 4
            expected = (wi_type, state) in EXPECTED_CLOSED
            actual = should_close(item)
            if actual != expected:
                failures.append(
                    f"({wi_type!r}, {state!r}): expected closed={expected}, got {actual}"
                )
        assert not failures, "should_close mismatches:\n" + "\n".join(failures)


# ===========================================================================
# 5. build_labels — no "type: unknown" in any label list
# ===========================================================================

class TestBuildLabels:

    def test_no_unknown_type_label_for_any_known_type(self):
        failures = []
        for wi_type in WORK_ITEM_TYPE_LABELS:
            item = _make_item(wi_type, "New")
            labels = build_labels(item)
            if "type: unknown" in labels:
                failures.append(wi_type)
        assert not failures, (
            f"build_labels returned 'type: unknown' for: {failures}"
        )

    def test_feature_request_gets_correct_label(self):
        item = _make_item("Feature Request", "New")
        assert "type: feature-request" in build_labels(item)

    def test_user_story_gets_correct_label(self):
        item = _make_item("User Story", "Active")
        assert "type: user-story" in build_labels(item)

    def test_state_in_code_review_produces_label(self):
        item = _make_item("Bug", "In Code Review")
        labels = build_labels(item)
        assert "state: in-code-review" in labels

    def test_state_in_test_produces_label(self):
        item = _make_item("Bug", "In Test")
        labels = build_labels(item)
        assert "state: in-test" in labels

    def test_state_completed_produces_label(self):
        item = _make_item("Feature Request", "Completed")
        labels = build_labels(item)
        # "state: completed" is the label; "closed" is filtered out from labels
        assert "state: completed" in labels

    def test_state_declined_produces_label(self):
        item = _make_item("Feature Request", "Declined")
        labels = build_labels(item)
        assert "state: declined" in labels

    def test_state_awaiting_test_produces_label(self):
        item = _make_item("User Story", "Awaiting Test")
        labels = build_labels(item)
        assert "state: awaiting-test" in labels

    def test_state_design_produces_label(self):
        item = _make_item("Test Case", "Design")
        labels = build_labels(item)
        assert "state: design" in labels


# ===========================================================================
# 6. setup_github.py — LABELS_TO_CREATE covers every label migration will emit
# ===========================================================================

class TestLabelsCoverage:

    def _label_names(self) -> set[str]:
        return {name for name, _, _ in LABELS_TO_CREATE}

    def test_type_user_story_in_labels_to_create(self):
        assert "type: user-story" in self._label_names()

    def test_type_feature_request_in_labels_to_create(self):
        assert "type: feature-request" in self._label_names()

    def test_state_in_code_review_in_labels_to_create(self):
        assert "state: in-code-review" in self._label_names()

    def test_state_in_test_in_labels_to_create(self):
        assert "state: in-test" in self._label_names()

    def test_state_completed_in_labels_to_create(self):
        assert "state: completed" in self._label_names()

    def test_state_declined_in_labels_to_create(self):
        assert "state: declined" in self._label_names()

    def test_state_awaiting_test_in_labels_to_create(self):
        assert "state: awaiting-test" in self._label_names()

    def test_state_design_in_labels_to_create(self):
        assert "state: design" in self._label_names()

    def test_required_labels_are_all_in_labels_to_create(self):
        """
        _REQUIRED_LABELS is computed from config at import time.
        Every required label must exist in LABELS_TO_CREATE so setup_github.py
        can create it before migration runs.
        """
        label_names = self._label_names()
        missing = sorted(_REQUIRED_LABELS - label_names)
        assert not missing, (
            f"Labels required by migration but absent from LABELS_TO_CREATE:\n"
            + "\n".join(f"  {m}" for m in missing)
        )
