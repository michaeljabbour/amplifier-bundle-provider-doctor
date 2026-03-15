"""TDD tests for agents/provider-health.md (task-12).

Tests cover:
- agents/provider-health.md exists
- Frontmatter meta.name == 'provider-health'
- Description mentions testing connectivity and responsiveness with minimal test requests
- model_role is 'fast'
- Body contains What To Test section
- What To Test covers: connectivity, authentication, credentials validity, responsiveness/latency, model availability
- Body contains How To Test section
- How To Test mentions sending minimal request 'Respond with exactly: OK'
- How To Test mentions measuring wall-clock time
- How To Test mentions catching/classifying errors
- How To Test mentions reporting HTTP status codes
- Body contains Report Format section (table with Provider/Model/Status/Latency/Details columns)
- Summary line in report format
- Recommendation for failing providers in report format
"""

from __future__ import annotations

import os

import yaml

BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_PATH = os.path.join(BUNDLE_ROOT, "agents", "provider-health.md")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_agent_frontmatter() -> tuple[dict, str]:
    """Parse YAML frontmatter from agents/provider-health.md, returning (parsed_dict, full_content)."""
    assert os.path.exists(AGENT_PATH), "agents/provider-health.md must exist"
    with open(AGENT_PATH) as f:
        content = f.read()
    assert content.startswith("---"), (
        "agents/provider-health.md must start with YAML frontmatter '---'"
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


class TestProviderHealthExists:
    """Tests for file existence."""

    def test_file_exists(self):
        """agents/provider-health.md exists."""
        assert os.path.exists(AGENT_PATH), "agents/provider-health.md must exist"


# ---------------------------------------------------------------------------
# Tests: Frontmatter
# ---------------------------------------------------------------------------


class TestProviderHealthFrontmatter:
    """Tests for frontmatter correctness."""

    def test_meta_name_is_provider_health(self):
        """meta.name is 'provider-health'."""
        fm, _ = _parse_agent_frontmatter()
        assert fm["meta"]["name"] == "provider-health"

    def test_description_mentions_connectivity(self):
        """Description mentions testing connectivity."""
        fm, _ = _parse_agent_frontmatter()
        desc = fm["meta"]["description"].lower()
        assert "connect" in desc

    def test_description_mentions_responsiveness(self):
        """Description mentions testing responsiveness."""
        fm, _ = _parse_agent_frontmatter()
        desc = fm["meta"]["description"].lower()
        assert "responsiv" in desc or "latency" in desc or "response" in desc

    def test_description_mentions_minimal_test_requests(self):
        """Description mentions minimal test requests."""
        fm, _ = _parse_agent_frontmatter()
        desc = fm["meta"]["description"].lower()
        assert "minimal" in desc or "minimum" in desc

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
# Tests: What To Test section
# ---------------------------------------------------------------------------


class TestProviderHealthWhatToTest:
    """Tests for What To Test section in the body."""

    def test_what_to_test_section_exists(self):
        """Body contains a What To Test section."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "what to test" in body

    def test_what_to_test_mentions_connectivity(self):
        """What To Test covers connectivity."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "connect" in body

    def test_what_to_test_mentions_authentication(self):
        """What To Test covers authentication."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "auth" in body

    def test_what_to_test_mentions_credentials(self):
        """What To Test covers credentials validity."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "credential" in body

    def test_what_to_test_mentions_responsiveness_or_latency(self):
        """What To Test covers responsiveness/latency."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "responsiv" in body or "latency" in body

    def test_what_to_test_mentions_model_availability(self):
        """What To Test covers model availability."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "model" in body and ("availab" in body or "access" in body)

    def test_what_to_test_mentions_failover_chain(self):
        """What To Test references each provider in the failover chain."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "failover" in body or "chain" in body or "provider" in body


# ---------------------------------------------------------------------------
# Tests: How To Test section
# ---------------------------------------------------------------------------


class TestProviderHealthHowToTest:
    """Tests for How To Test section in the body."""

    def test_how_to_test_section_exists(self):
        """Body contains a How To Test section."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "how to test" in body

    def test_how_to_test_minimal_request_ok(self):
        """How To Test mentions sending minimal request 'Respond with exactly: OK'."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert (
            "Respond with exactly: OK" in body
            or "respond with exactly: ok" in body.lower()
        )

    def test_how_to_test_measures_wall_clock_time(self):
        """How To Test mentions measuring wall-clock time."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert (
            "wall" in body
            and "clock" in body
            or "wall-clock" in body
            or ("wall" in body and "time" in body)
        )

    def test_how_to_test_catches_classifies_errors(self):
        """How To Test mentions catching and classifying errors."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "catch" in body or "classif" in body

    def test_how_to_test_reports_http_status_codes(self):
        """How To Test mentions reporting HTTP status codes."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "http" in body and ("status" in body or "code" in body)


# ---------------------------------------------------------------------------
# Tests: Report Format section
# ---------------------------------------------------------------------------


class TestProviderHealthReportFormat:
    """Tests for Report Format section in the body."""

    def test_report_format_section_exists(self):
        """Body contains a Report Format section."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "report" in body and "format" in body

    def test_report_table_has_provider_column(self):
        """Report format table has a Provider column."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "Provider" in body

    def test_report_table_has_model_column(self):
        """Report format table has a Model column."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "Model" in body

    def test_report_table_has_status_column(self):
        """Report format table has a Status column."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "Status" in body

    def test_report_table_has_latency_column(self):
        """Report format table has a Latency column."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "Latency" in body

    def test_report_table_has_details_column(self):
        """Report format table has a Details column."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content)
        assert "Details" in body

    def test_report_format_has_summary_line(self):
        """Report format has a summary line."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "summary" in body

    def test_report_format_has_recommendation_for_failing_providers(self):
        """Report format has recommendation for failing providers."""
        _, content = _parse_agent_frontmatter()
        body = _get_body(content).lower()
        assert "recommend" in body
        assert "fail" in body
