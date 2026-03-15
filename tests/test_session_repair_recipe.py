"""TDD tests for recipes/session-repair.yaml (task-11).

Tests cover:
- recipes/session-repair.yaml exists
- Valid YAML (parseable)
- name == 'session-repair'
- description mentions diagnosing and repairing a broken Amplifier session
- Has exactly two steps: 'diagnose' and 'repair'
- 'diagnose' step is unconditional (no condition field)
- 'diagnose' step uses agent 'provider-doctor:session-doctor'
- 'diagnose' step instruction references {{session_id}}
- 'diagnose' step instruction mentions orphaned tool calls
- 'diagnose' step instruction mentions ordering violations
- 'diagnose' step instruction mentions oversized transcripts
- 'diagnose' step instruction mentions truncated/malformed events
- 'diagnose' step instruction mentions severity
- 'diagnose' step instruction mentions needs_repair=true for critical/warning
- 'repair' step has condition referencing diagnose.needs_repair
- 'repair' step uses agent 'provider-doctor:session-doctor'
- 'repair' step instruction mentions backup
- 'repair' step instruction mentions inject synthetic results
- 'repair' step instruction mentions verify repair
- 'repair' step instruction mentions report changes
"""

from __future__ import annotations

import os

import yaml

BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPE_PATH = os.path.join(BUNDLE_ROOT, "recipes", "session-repair.yaml")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_recipe() -> dict:
    """Load and parse recipes/session-repair.yaml."""
    assert os.path.exists(RECIPE_PATH), "recipes/session-repair.yaml must exist"
    with open(RECIPE_PATH) as f:
        data = yaml.safe_load(f)
    assert data is not None, "recipes/session-repair.yaml must not be empty"
    assert isinstance(data, dict), "recipes/session-repair.yaml must be a YAML mapping"
    return data


def _get_step(data: dict, step_id: str) -> dict:
    """Return the step dict with the given id, or fail with a clear message."""
    steps = data.get("steps", [])
    step = next(
        (s for s in steps if isinstance(s, dict) and s.get("id") == step_id),
        None,
    )
    assert step is not None, f"steps must contain a step with id='{step_id}'"
    return step


# ---------------------------------------------------------------------------
# Tests: File existence and validity
# ---------------------------------------------------------------------------


class TestSessionRepairRecipeExists:
    """Tests for file existence and YAML validity."""

    def test_file_exists(self):
        """recipes/session-repair.yaml exists."""
        assert os.path.exists(RECIPE_PATH), "recipes/session-repair.yaml must exist"

    def test_is_yaml_mapping(self):
        """recipes/session-repair.yaml parses to a dict (YAML mapping)."""
        data = _load_recipe()
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Tests: Top-level metadata
# ---------------------------------------------------------------------------


class TestSessionRepairRecipeMetadata:
    """Tests for top-level recipe metadata fields."""

    def test_name_is_session_repair(self):
        """Recipe name is 'session-repair'."""
        data = _load_recipe()
        assert data.get("name") == "session-repair"

    def test_description_mentions_diagnose(self):
        """Recipe description mentions diagnosing."""
        data = _load_recipe()
        desc = (data.get("description") or "").lower()
        assert "diagnos" in desc

    def test_description_mentions_repair(self):
        """Recipe description mentions repair."""
        data = _load_recipe()
        desc = (data.get("description") or "").lower()
        assert "repair" in desc

    def test_description_mentions_session(self):
        """Recipe description mentions session."""
        data = _load_recipe()
        desc = (data.get("description") or "").lower()
        assert "session" in desc


# ---------------------------------------------------------------------------
# Tests: Steps structure
# ---------------------------------------------------------------------------


class TestSessionRepairRecipeSteps:
    """Tests for the steps list structure."""

    def test_steps_section_exists(self):
        """Recipe has a 'steps' section."""
        data = _load_recipe()
        assert "steps" in data, "Recipe must have a 'steps' section"

    def test_steps_is_a_list(self):
        """steps is a list."""
        data = _load_recipe()
        assert isinstance(data["steps"], list)

    def test_exactly_two_steps(self):
        """Recipe has exactly two steps."""
        data = _load_recipe()
        assert len(data["steps"]) == 2, (
            f"Recipe must have exactly 2 steps, found {len(data['steps'])}"
        )

    def test_first_step_id_is_diagnose(self):
        """First step has id='diagnose'."""
        data = _load_recipe()
        assert data["steps"][0].get("id") == "diagnose"

    def test_second_step_id_is_repair(self):
        """Second step has id='repair'."""
        data = _load_recipe()
        assert data["steps"][1].get("id") == "repair"


# ---------------------------------------------------------------------------
# Tests: 'diagnose' step
# ---------------------------------------------------------------------------


class TestDiagnoseStep:
    """Tests for the 'diagnose' step."""

    def test_diagnose_is_unconditional(self):
        """diagnose step has no 'condition' field (runs unconditionally)."""
        data = _load_recipe()
        step = _get_step(data, "diagnose")
        assert "condition" not in step, (
            "diagnose step must be unconditional (no 'condition' field)"
        )

    def test_diagnose_uses_session_doctor_agent(self):
        """diagnose step uses agent 'provider-doctor:session-doctor'."""
        data = _load_recipe()
        step = _get_step(data, "diagnose")
        agent = step.get("agent", "")
        assert agent == "provider-doctor:session-doctor", (
            f"diagnose agent must be 'provider-doctor:session-doctor', got '{agent}'"
        )

    def test_diagnose_instruction_references_session_id(self):
        """diagnose instruction references {{session_id}}."""
        data = _load_recipe()
        step = _get_step(data, "diagnose")
        instruction = step.get("prompt", step.get("instruction", ""))
        assert "session_id" in instruction, (
            "diagnose instruction must reference session_id"
        )

    def test_diagnose_instruction_mentions_orphaned_tool_calls(self):
        """diagnose instruction mentions orphaned tool calls."""
        data = _load_recipe()
        step = _get_step(data, "diagnose")
        instruction = (step.get("prompt", step.get("instruction", "")) or "").lower()
        assert "orphan" in instruction, (
            "diagnose instruction must mention orphaned tool calls"
        )

    def test_diagnose_instruction_mentions_ordering_violations(self):
        """diagnose instruction mentions ordering violations."""
        data = _load_recipe()
        step = _get_step(data, "diagnose")
        instruction = (step.get("prompt", step.get("instruction", "")) or "").lower()
        assert "order" in instruction and "violation" in instruction, (
            "diagnose instruction must mention ordering violations"
        )

    def test_diagnose_instruction_mentions_oversized_transcripts(self):
        """diagnose instruction mentions oversized transcripts."""
        data = _load_recipe()
        step = _get_step(data, "diagnose")
        instruction = (step.get("prompt", step.get("instruction", "")) or "").lower()
        assert "oversize" in instruction or "oversized" in instruction, (
            "diagnose instruction must mention oversized transcripts"
        )

    def test_diagnose_instruction_mentions_truncated_or_malformed_events(self):
        """diagnose instruction mentions truncated or malformed events."""
        data = _load_recipe()
        step = _get_step(data, "diagnose")
        instruction = (step.get("prompt", step.get("instruction", "")) or "").lower()
        assert "truncat" in instruction or "malform" in instruction, (
            "diagnose instruction must mention truncated/malformed events"
        )

    def test_diagnose_instruction_mentions_severity(self):
        """diagnose instruction mentions reporting with severity."""
        data = _load_recipe()
        step = _get_step(data, "diagnose")
        instruction = (step.get("prompt", step.get("instruction", "")) or "").lower()
        assert "severity" in instruction, (
            "diagnose instruction must mention reporting with severity"
        )

    def test_diagnose_instruction_mentions_needs_repair(self):
        """diagnose instruction mentions setting needs_repair=true."""
        data = _load_recipe()
        step = _get_step(data, "diagnose")
        instruction = step.get("prompt", step.get("instruction", "")) or ""
        assert "needs_repair" in instruction, (
            "diagnose instruction must mention needs_repair"
        )

    def test_diagnose_instruction_mentions_critical_or_warning(self):
        """diagnose instruction mentions critical or warning severity."""
        data = _load_recipe()
        step = _get_step(data, "diagnose")
        instruction = (step.get("prompt", step.get("instruction", "")) or "").lower()
        assert "critical" in instruction or "warning" in instruction, (
            "diagnose instruction must mention critical/warning severity triggers"
        )


# ---------------------------------------------------------------------------
# Tests: 'repair' step
# ---------------------------------------------------------------------------


class TestRepairStep:
    """Tests for the 'repair' step."""

    def test_repair_has_condition(self):
        """repair step has a 'condition' field."""
        data = _load_recipe()
        step = _get_step(data, "repair")
        assert "condition" in step, "repair step must have a 'condition' field"

    def test_repair_condition_references_diagnose_needs_repair(self):
        """repair condition references diagnose.needs_repair."""
        data = _load_recipe()
        step = _get_step(data, "repair")
        condition = step.get("condition", "")
        assert "diagnose.needs_repair" in condition, (
            f"repair condition must reference 'diagnose.needs_repair', got '{condition}'"
        )

    def test_repair_uses_session_doctor_agent(self):
        """repair step uses agent 'provider-doctor:session-doctor'."""
        data = _load_recipe()
        step = _get_step(data, "repair")
        agent = step.get("agent", "")
        assert agent == "provider-doctor:session-doctor", (
            f"repair agent must be 'provider-doctor:session-doctor', got '{agent}'"
        )

    def test_repair_instruction_mentions_backup(self):
        """repair instruction mentions creating a backup."""
        data = _load_recipe()
        step = _get_step(data, "repair")
        instruction = (step.get("prompt", step.get("instruction", "")) or "").lower()
        assert "backup" in instruction, (
            "repair instruction must mention creating a backup"
        )

    def test_repair_instruction_mentions_inject_synthetic(self):
        """repair instruction mentions injecting synthetic results."""
        data = _load_recipe()
        step = _get_step(data, "repair")
        instruction = (step.get("prompt", step.get("instruction", "")) or "").lower()
        assert "inject" in instruction or "synthetic" in instruction, (
            "repair instruction must mention inject synthetic results"
        )

    def test_repair_instruction_mentions_verify(self):
        """repair instruction mentions verifying the repair."""
        data = _load_recipe()
        step = _get_step(data, "repair")
        instruction = (step.get("prompt", step.get("instruction", "")) or "").lower()
        assert "verify" in instruction, (
            "repair instruction must mention verifying the repair"
        )

    def test_repair_instruction_mentions_report_changes(self):
        """repair instruction mentions reporting changes."""
        data = _load_recipe()
        step = _get_step(data, "repair")
        instruction = (step.get("prompt", step.get("instruction", "")) or "").lower()
        assert "report" in instruction or "changes" in instruction, (
            "repair instruction must mention reporting changes"
        )
