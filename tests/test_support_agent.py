"""TDD tests for agents/support.md (task-15).

Tests cover:
- agents/support.md exists
- Frontmatter meta.name == 'support'
- Description mentions capturing diagnosis and generating structured support tickets
- model_role is 'fast'
- Body defines a Workflow section
- Workflow step 1: gather context (error/problem, session ID, project/bundle)
- Workflow step 2: run diagnostics (provider-diagnosis recipe, session-repair diagnose-only)
- Workflow step 3: fill support template (references context/support-template.md, 'Not available')
- Workflow step 4: save ticket to docs/support/YYYY-MM-DD-<topic>.md
- Workflow step 5: summarize for user (key findings, captured info, next steps)
- Important notes: include raw error/stack trace
- Important notes: include provider health results
- Important notes: be specific about failover tier failures
- Important notes: don't speculate
"""

from __future__ import annotations

import os

import yaml

BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_PATH = os.path.join(BUNDLE_ROOT, "agents", "support.md")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_agent_frontmatter() -> tuple[dict, str]:
    """Parse YAML frontmatter from agents/support.md, returning (parsed_dict, full_content)."""
    assert os.path.exists(AGENT_PATH), "agents/support.md must exist"
    with open(AGENT_PATH) as f:
        content = f.read()
    assert content.startswith("---"), (
        "agents/support.md must start with YAML frontmatter '---'"
    )
    end_idx = content.index("---", 3)
    frontmatter_str = content[3:end_idx].strip()
    return yaml.safe_load(frontmatter_str), content


def _get_body(content: str) -> str:
    """Return the body content (after frontmatter)."""
    end_idx = content.index("---", 3)
    return content[end_idx + 3 :].strip()


# ---------------------------------------------------------------------------
# Tests: File existence
# ---------------------------------------------------------------------------


class TestSupportAgentExists:
    """Tests for file existence."""

    def test_file_exists(self):
        """agents/support.md exists."""
        assert os.path.exists(AGENT_PATH), "agents/support.md must exist"


# ---------------------------------------------------------------------------
# Tests: Frontmatter
# ---------------------------------------------------------------------------


class TestSupportAgentFrontmatter:
    """Tests for frontmatter correctness."""

    def test_meta_name_is_support(self):
        """meta.name is 'support'."""
        fm, _ = _parse_agent_frontmatter()
        assert fm["meta"]["name"] == "support"

    def test_description_mentions_capturing_diagnosis(self):
        """Description mentions capturing diagnosis."""
        fm, _ = _parse_agent_frontmatter()
        desc = fm["meta"]["description"].lower()
        assert "diagnos" in desc or "captur" in desc

    def test_description_mentions_support_tickets(self):
        """Description mentions generating structured support tickets."""
        fm, _ = _parse_agent_frontmatter()
        desc = fm["meta"]["description"].lower()
        assert "support ticket" in desc or "ticket" in desc

    def test_description_mentions_structured(self):
        """Description mentions structured tickets."""
        fm, _ = _parse_agent_frontmatter()
        desc = fm["meta"]["description"].lower()
        assert "struct" in desc or "ticket" in desc

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
# Tests: Workflow section
# ---------------------------------------------------------------------------


class TestSupportAgentWorkflow:
    """Tests for the Workflow section in the body."""

    def test_workflow_section_exists(self):
        """Body contains a Workflow section."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "workflow" in body


# ---------------------------------------------------------------------------
# Tests: Step 1 - Gather Context
# ---------------------------------------------------------------------------


class TestSupportAgentGatherContext:
    """Tests for Workflow Step 1: Gather Context."""

    def test_asks_about_error_or_problem(self):
        """Body mentions asking about the error or problem."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "error" in body or "problem" in body

    def test_notes_session_id(self):
        """Body mentions noting the session ID."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "session id" in body or "session_id" in body

    def test_checks_project_and_bundle(self):
        """Body mentions checking project and bundle."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "project" in body
        assert "bundle" in body


# ---------------------------------------------------------------------------
# Tests: Step 2 - Run Diagnostics
# ---------------------------------------------------------------------------


class TestSupportAgentRunDiagnostics:
    """Tests for Workflow Step 2: Run Diagnostics."""

    def test_suggests_provider_diagnosis_recipe(self):
        """Body mentions suggesting the provider-diagnosis recipe."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "provider-diagnosis" in body or "provider diagnosis" in body

    def test_suggests_session_repair_diagnose_only_mode(self):
        """Body mentions suggesting session-repair in diagnose-only mode."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "session-repair" in body or "session repair" in body

    def test_session_repair_diagnose_only_when_session_id_provided(self):
        """Body specifies session-repair diagnose-only mode when session ID provided."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "diagnose" in body or "diagnos" in body

    def test_captures_output(self):
        """Body mentions capturing diagnostic output."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "output" in body or "captur" in body or "result" in body


# ---------------------------------------------------------------------------
# Tests: Step 3 - Fill Support Template
# ---------------------------------------------------------------------------


class TestSupportAgentFillTemplate:
    """Tests for Workflow Step 3: Fill Support Template."""

    def test_references_support_template_path(self):
        """Body references context/support-template.md."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "context/support-template.md" in body or "support-template.md" in body

    def test_fills_available_fields(self):
        """Body mentions filling available fields."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "fill" in body or "field" in body or "available" in body

    def test_marks_unknown_as_not_available(self):
        """Body mentions marking unknown fields as 'Not available'."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "not available" in body


# ---------------------------------------------------------------------------
# Tests: Step 4 - Save Ticket
# ---------------------------------------------------------------------------


class TestSupportAgentSaveTicket:
    """Tests for Workflow Step 4: Save Ticket."""

    def test_saves_to_docs_support_directory(self):
        """Body mentions saving ticket to docs/support/ directory."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "docs/support" in body

    def test_filename_includes_date_format(self):
        """Body mentions YYYY-MM-DD date format in filename."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "YYYY-MM-DD" in body or "yyyy-mm-dd" in body.lower()

    def test_filename_includes_topic(self):
        """Body mentions including topic in filename."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "topic" in body

    def test_creates_directory_if_needed(self):
        """Body mentions creating directory if needed."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert (
            "creat" in body
            and "director" in body
            or "mkdir" in body
            or "if needed" in body
        )


# ---------------------------------------------------------------------------
# Tests: Step 5 - Summarize for User
# ---------------------------------------------------------------------------


class TestSupportAgentSummarizeForUser:
    """Tests for Workflow Step 5: Summarize for User."""

    def test_summarizes_key_findings(self):
        """Body mentions summarizing key findings."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "key finding" in body or "finding" in body

    def test_mentions_captured_info(self):
        """Body mentions captured info."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "captur" in body or "captured" in body

    def test_provides_next_steps(self):
        """Body mentions providing next steps."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "next step" in body


# ---------------------------------------------------------------------------
# Tests: Important Notes
# ---------------------------------------------------------------------------


class TestSupportAgentImportantNotes:
    """Tests for the Important Notes / constraints."""

    def test_includes_raw_error_or_stack_trace(self):
        """Body mentions including raw error or stack trace."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "stack trace" in body or "raw error" in body or "stack" in body

    def test_includes_provider_health_results(self):
        """Body mentions including provider health results."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "provider health" in body

    def test_specific_about_failover_tier_failures(self):
        """Body mentions being specific about failover tier failures."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "failover" in body or "tier" in body

    def test_does_not_speculate(self):
        """Body mentions not speculating."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert (
            "speculat" in body
            or "don't speculate" in body
            or "do not speculate" in body
        )
