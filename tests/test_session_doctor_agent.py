"""TDD tests for agents/session-doctor.md (task-10).

Tests cover:
- agents/session-doctor.md exists
- Frontmatter meta.name == 'session-doctor'
- Description mentions diagnosing/repairing broken sessions, orphaned tool calls,
  ordering violations, oversized transcripts
- model_role is 'fast'
- Body contains Diagnosis Steps section
- Body covers session dir path ~/.amplifier/sessions/
- Body mentions metadata.json
- Body mentions events.jsonl
- Body checks for orphaned tool calls
- Body checks for ordering violations
- Body checks for oversized transcripts >500K chars
- Body checks for duplicate entries
- Body checks for truncated events
- Body reports with severity
- Body contains Repair Strategies section
- Body says always backup first
- Body shows backup pattern events.jsonl.bak.<timestamp>
- Body says prefer REPAIR over REWIND
- Body defines REPAIR as inject synthetic tool results
- Body defines REWIND as truncate transcript
- Body says only REWIND when explicitly requested
- Body says verify after repair
- Body contains Output Format section
- Output format shows Session, Status, Issues, Repair plan fields
"""

from __future__ import annotations

import os

import yaml

BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_PATH = os.path.join(BUNDLE_ROOT, "agents", "session-doctor.md")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_agent_frontmatter() -> tuple[dict, str]:
    """Parse YAML frontmatter from agents/session-doctor.md, returning (parsed_dict, full_content)."""
    assert os.path.exists(AGENT_PATH), "agents/session-doctor.md must exist"
    with open(AGENT_PATH) as f:
        content = f.read()
    assert content.startswith("---"), "agents/session-doctor.md must start with YAML frontmatter '---'"
    end_idx = content.index("---", 3)
    frontmatter_str = content[3:end_idx].strip()
    return yaml.safe_load(frontmatter_str), content


def _get_body(content: str) -> str:
    """Return the body content (after frontmatter)."""
    end_idx = content.index("---", 3)
    return content[end_idx + 3:].strip()


# ---------------------------------------------------------------------------
# Tests: File existence
# ---------------------------------------------------------------------------


class TestSessionDoctorExists:
    """Tests for file existence."""

    def test_file_exists(self):
        """agents/session-doctor.md exists."""
        assert os.path.exists(AGENT_PATH), "agents/session-doctor.md must exist"


# ---------------------------------------------------------------------------
# Tests: Frontmatter
# ---------------------------------------------------------------------------


class TestSessionDoctorFrontmatter:
    """Tests for frontmatter correctness."""

    def test_meta_name_is_session_doctor(self):
        """meta.name is 'session-doctor'."""
        fm, _ = _parse_agent_frontmatter()
        assert fm["meta"]["name"] == "session-doctor"

    def test_description_mentions_diagnosing(self):
        """Description mentions diagnosing broken sessions."""
        fm, _ = _parse_agent_frontmatter()
        desc = fm["meta"]["description"].lower()
        assert "diagnos" in desc

    def test_description_mentions_repairing(self):
        """Description mentions repairing broken sessions."""
        fm, _ = _parse_agent_frontmatter()
        desc = fm["meta"]["description"].lower()
        assert "repair" in desc

    def test_description_mentions_orphaned_tool_calls(self):
        """Description mentions orphaned tool calls."""
        fm, _ = _parse_agent_frontmatter()
        desc = fm["meta"]["description"].lower()
        assert "orphan" in desc

    def test_description_mentions_ordering_violations(self):
        """Description mentions ordering violations."""
        fm, _ = _parse_agent_frontmatter()
        desc = fm["meta"]["description"].lower()
        assert "order" in desc

    def test_description_mentions_oversized_transcripts(self):
        """Description mentions oversized transcripts."""
        fm, _ = _parse_agent_frontmatter()
        desc = fm["meta"]["description"].lower()
        assert "oversize" in desc or "oversized" in desc or "transcript" in desc

    def test_model_role_is_fast(self):
        """model_role is 'fast'."""
        fm, _ = _parse_agent_frontmatter()
        model_role = fm["meta"]["model_role"]
        # model_role can be a string or a list
        if isinstance(model_role, list):
            assert "fast" in model_role
        else:
            assert model_role == "fast"


# ---------------------------------------------------------------------------
# Tests: Diagnosis Steps
# ---------------------------------------------------------------------------


class TestSessionDoctorDiagnosisSteps:
    """Tests for Diagnosis Steps section in the body."""

    def test_diagnosis_steps_section_exists(self):
        """Body contains a Diagnosis Steps section."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "diagnosis" in body and "step" in body

    def test_mentions_session_dir_path(self):
        """Body mentions ~/.amplifier/sessions/ session directory path."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "~/.amplifier/sessions" in body

    def test_mentions_metadata_json(self):
        """Body mentions reading metadata.json."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "metadata.json" in body

    def test_mentions_events_jsonl(self):
        """Body mentions analyzing events.jsonl."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "events.jsonl" in body

    def test_checks_orphaned_tool_calls(self):
        """Body checks for orphaned tool calls."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "orphan" in body

    def test_checks_ordering_violations(self):
        """Body checks for ordering violations."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "order" in body and "violation" in body

    def test_checks_oversized_transcripts(self):
        """Body checks for oversized transcripts >500K chars."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "500" in body

    def test_checks_duplicate_entries(self):
        """Body checks for duplicate entries."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "duplicate" in body

    def test_checks_truncated_events(self):
        """Body checks for truncated events."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "truncat" in body

    def test_reports_with_severity(self):
        """Body reports issues with severity."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "severity" in body


# ---------------------------------------------------------------------------
# Tests: Repair Strategies
# ---------------------------------------------------------------------------


class TestSessionDoctorRepairStrategies:
    """Tests for Repair Strategies section in the body."""

    def test_repair_strategies_section_exists(self):
        """Body contains a Repair Strategies section."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "repair" in body and "strateg" in body

    def test_always_backup_first(self):
        """Body says to always backup first."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "backup" in body

    def test_backup_pattern_with_timestamp(self):
        """Body shows backup file pattern events.jsonl.bak.<timestamp>."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "events.jsonl.bak" in body

    def test_prefer_repair_over_rewind(self):
        """Body says to prefer REPAIR over REWIND."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).upper()
        assert "REPAIR" in body
        assert "REWIND" in body

    def test_repair_defined_as_inject_synthetic_tool_results(self):
        """Body defines REPAIR as injecting synthetic tool results."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "synthetic" in body
        assert "inject" in body or "injection" in body

    def test_rewind_defined_as_truncate_transcript(self):
        """Body defines REWIND as truncating the transcript."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "truncat" in body

    def test_rewind_only_when_explicitly_requested(self):
        """Body says only REWIND when explicitly requested."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "explicit" in body

    def test_verify_after_repair(self):
        """Body says to verify after repair."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "verify" in body


# ---------------------------------------------------------------------------
# Tests: Output Format
# ---------------------------------------------------------------------------


class TestSessionDoctorOutputFormat:
    """Tests for Output Format section in the body."""

    def test_output_format_section_exists(self):
        """Body contains an Output Format section."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "output" in body and "format" in body

    def test_output_shows_session_field(self):
        """Output format template shows a Session field."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "Session" in body or "session" in body.lower()

    def test_output_shows_status_field(self):
        """Output format template shows a Status field."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "Status" in body or "status" in body.lower()

    def test_output_shows_issues_field(self):
        """Output format template shows an Issues field."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "Issues" in body or "issues" in body.lower()

    def test_output_shows_repair_plan_field(self):
        """Output format template shows a Repair plan field."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "repair" in body and ("plan" in body or "repair plan" in body)
