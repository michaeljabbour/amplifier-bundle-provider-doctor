"""Tests for context/support-template.md.

Validates:
- File exists at correct path
- All required sections are present
- All required template variables ({{var}} syntax) are present
- Header fields exist
- Diagnosis fields exist
- Session State fields exist
- Provider Health section exists
- Steps to Reproduce section exists
- Attachments checklist items exist
- File is valid markdown (non-empty, uses markdown headings)
"""

import os
import re

import pytest

BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(BUNDLE_ROOT, "context", "support-template.md")


@pytest.fixture(scope="module")
def template_content() -> str:
    with open(TEMPLATE_PATH) as f:
        return f.read()


class TestSupportTemplateExists:
    def test_file_exists(self):
        assert os.path.isfile(TEMPLATE_PATH), "context/support-template.md must exist"

    def test_file_is_non_empty(self, template_content: str):
        assert len(template_content.strip()) > 0, "Template file must not be empty"

    def test_file_is_markdown(self, template_content: str):
        # Valid markdown must contain at least one heading
        assert re.search(r"^#{1,6}\s+\S", template_content, re.MULTILINE), (
            "Template must contain at least one markdown heading"
        )


class TestSupportTemplateHeaderSection:
    def test_has_date_field(self, template_content: str):
        assert re.search(r"^\| Date\b", template_content, re.MULTILINE), (
            "Header must contain a Date table row"
        )

    def test_has_session_id_field(self, template_content: str):
        assert "Session ID" in template_content, (
            "Header must contain a Session ID field"
        )

    def test_has_project_field(self, template_content: str):
        assert "Project" in template_content, "Header must contain a Project field"

    def test_has_bundle_field(self, template_content: str):
        assert re.search(r"^\| Bundle\b", template_content, re.MULTILINE), (
            "Header must contain a Bundle table row"
        )


class TestSupportTemplateErrorObservedSection:
    def test_has_error_observed_section(self, template_content: str):
        assert re.search(r"error observed", template_content, re.IGNORECASE), (
            "Template must contain an Error Observed section"
        )

    def test_has_error_description_variable(self, template_content: str):
        assert "{{error_description}}" in template_content, (
            "Template must contain {{error_description}} variable"
        )


class TestSupportTemplateDiagnosisSection:
    def test_has_diagnosis_section(self, template_content: str):
        assert re.search(r"diagnosis", template_content, re.IGNORECASE), (
            "Template must contain a Diagnosis section"
        )

    def test_has_provider_field(self, template_content: str):
        assert re.search(r"^\| Provider\b", template_content, re.MULTILINE), (
            "Diagnosis section must contain a Provider table row"
        )

    def test_has_error_type_field(self, template_content: str):
        assert re.search(r"error type", template_content, re.IGNORECASE), (
            "Diagnosis section must contain an Error type field"
        )

    def test_has_retryable_field(self, template_content: str):
        assert re.search(r"retryable", template_content, re.IGNORECASE), (
            "Diagnosis section must contain a Retryable field"
        )

    def test_has_failover_attempted_field(self, template_content: str):
        assert re.search(r"failover attempted", template_content, re.IGNORECASE), (
            "Diagnosis section must contain a Failover attempted field"
        )

    def test_has_tiers_tried_field(self, template_content: str):
        assert re.search(r"tiers tried", template_content, re.IGNORECASE), (
            "Diagnosis section must contain a Tiers tried field"
        )


class TestSupportTemplateSessionStateSection:
    def test_has_session_state_section(self, template_content: str):
        assert re.search(r"session state", template_content, re.IGNORECASE), (
            "Template must contain a Session State section"
        )

    def test_has_transcript_size_field(self, template_content: str):
        assert re.search(r"transcript size", template_content, re.IGNORECASE), (
            "Session State section must contain a Transcript size field"
        )

    def test_has_turn_count_field(self, template_content: str):
        assert re.search(r"turn count", template_content, re.IGNORECASE), (
            "Session State section must contain a Turn count field"
        )

    def test_has_last_successful_provider_call_field(self, template_content: str):
        assert re.search(
            r"last successful provider call", template_content, re.IGNORECASE
        ), "Session State section must contain a Last successful provider call field"


class TestSupportTemplateProviderHealthSection:
    def test_has_provider_health_section(self, template_content: str):
        assert re.search(r"provider health", template_content, re.IGNORECASE), (
            "Template must contain a Provider Health section"
        )

    def test_has_provider_health_results_variable(self, template_content: str):
        assert "{{provider_health_results}}" in template_content, (
            "Template must contain {{provider_health_results}} variable"
        )


class TestSupportTemplateStepsToReproduceSection:
    def test_has_steps_to_reproduce_section(self, template_content: str):
        assert re.search(r"steps to reproduce", template_content, re.IGNORECASE), (
            "Template must contain a Steps to Reproduce section"
        )

    def test_has_reproduction_steps_variable(self, template_content: str):
        assert "{{reproduction_steps}}" in template_content, (
            "Template must contain {{reproduction_steps}} variable"
        )


class TestSupportTemplateAttachmentsSection:
    def test_has_attachments_section(self, template_content: str):
        assert re.search(r"attachments", template_content, re.IGNORECASE), (
            "Template must contain an Attachments section"
        )

    def test_has_session_metadata_checklist_item(self, template_content: str):
        assert re.search(r"session metadata", template_content, re.IGNORECASE), (
            "Attachments must include Session metadata checklist item"
        )

    def test_has_error_logs_checklist_item(self, template_content: str):
        assert re.search(r"error logs", template_content, re.IGNORECASE), (
            "Attachments must include Error logs checklist item"
        )

    def test_has_events_jsonl_reference(self, template_content: str):
        assert "events.jsonl" in template_content, (
            "Attachments must reference events.jsonl (last 50 lines)"
        )

    def test_has_last_50_lines_reference(self, template_content: str):
        assert re.search(r"last 50 lines", template_content, re.IGNORECASE), (
            "Attachments error logs item must mention last 50 lines"
        )

    def test_has_provider_diagnosis_output_checklist_item(self, template_content: str):
        assert re.search(
            r"provider diagnosis output", template_content, re.IGNORECASE
        ), "Attachments must include Provider diagnosis output checklist item"
