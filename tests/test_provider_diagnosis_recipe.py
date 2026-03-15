"""TDD tests for recipes/provider-diagnosis.yaml (task-13).

Tests cover:
- recipes/provider-diagnosis.yaml exists
- Valid YAML (parseable)
- name == 'provider-diagnosis'
- description mentions testing providers and health status
- Has exactly two steps: 'test-providers' and 'recommend'
- 'test-providers' step uses agent 'provider-doctor:provider-health'
- 'test-providers' step instruction mentions Anthropic claude-opus-4-6
- 'test-providers' step instruction mentions Anthropic claude-sonnet-4-5
- 'test-providers' step instruction mentions OpenAI gpt-5.4
- 'test-providers' step instruction mentions sending minimal request
- 'test-providers' step instruction mentions measuring response time
- 'test-providers' step instruction mentions reporting as table
- 'recommend' step uses agent 'provider-doctor:provider-health'
- 'recommend' step instruction mentions which providers are healthy
- 'recommend' step instruction mentions failover chain
- 'recommend' step instruction mentions action items for failing providers
- 'recommend' step instruction mentions API keys
- 'recommend' step instruction mentions quotas
- 'recommend' step instruction mentions model availability
- 'recommend' step instruction mentions network
- 'recommend' step instruction mentions resilience assessment
"""

from __future__ import annotations

import os

import yaml

BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPE_PATH = os.path.join(BUNDLE_ROOT, "recipes", "provider-diagnosis.yaml")

# Module-level cache — loaded once, reused across all 26 tests in the module.
_recipe_cache: dict | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_recipe() -> dict:
    """Load and parse recipes/provider-diagnosis.yaml (cached at module level)."""
    global _recipe_cache
    if _recipe_cache is None:
        assert os.path.exists(RECIPE_PATH), "recipes/provider-diagnosis.yaml must exist"
        with open(RECIPE_PATH) as f:
            data = yaml.safe_load(f)
        assert data is not None, "recipes/provider-diagnosis.yaml must not be empty"
        assert isinstance(data, dict), (
            "recipes/provider-diagnosis.yaml must be a YAML mapping"
        )
        _recipe_cache = data
    return _recipe_cache


def _get_step(data: dict, step_id: str) -> dict:
    """Return the step dict with the given id, or fail with a clear message."""
    steps = data.get("steps", [])
    step = next(
        (s for s in steps if isinstance(s, dict) and s.get("id") == step_id),
        None,
    )
    assert step is not None, f"steps must contain a step with id='{step_id}'"
    return step


def _get_instruction(step: dict) -> str:
    """Return the instruction/prompt text from a step."""
    return step.get("prompt", step.get("instruction", "")) or ""


# ---------------------------------------------------------------------------
# Tests: File existence and validity
# ---------------------------------------------------------------------------


class TestProviderDiagnosisRecipeExists:
    """Tests for file existence and YAML validity."""

    def test_file_exists(self):
        """recipes/provider-diagnosis.yaml exists."""
        assert os.path.exists(RECIPE_PATH), "recipes/provider-diagnosis.yaml must exist"

    def test_is_yaml_mapping(self):
        """recipes/provider-diagnosis.yaml parses to a dict (YAML mapping)."""
        data = _load_recipe()
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Tests: Top-level metadata
# ---------------------------------------------------------------------------


class TestProviderDiagnosisRecipeMetadata:
    """Tests for top-level recipe metadata fields."""

    def test_name_is_provider_diagnosis(self):
        """Recipe name is 'provider-diagnosis'."""
        data = _load_recipe()
        assert data.get("name") == "provider-diagnosis"

    def test_description_mentions_providers(self):
        """Recipe description mentions providers."""
        data = _load_recipe()
        desc = (data.get("description") or "").lower()
        assert "provider" in desc

    def test_description_mentions_health(self):
        """Recipe description mentions health status."""
        data = _load_recipe()
        desc = (data.get("description") or "").lower()
        assert "health" in desc


# ---------------------------------------------------------------------------
# Tests: Steps structure
# ---------------------------------------------------------------------------


class TestProviderDiagnosisRecipeSteps:
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

    def test_first_step_id_is_test_providers(self):
        """First step has id='test-providers'."""
        data = _load_recipe()
        assert data["steps"][0].get("id") == "test-providers"

    def test_second_step_id_is_recommend(self):
        """Second step has id='recommend'."""
        data = _load_recipe()
        assert data["steps"][1].get("id") == "recommend"


# ---------------------------------------------------------------------------
# Tests: 'test-providers' step
# ---------------------------------------------------------------------------


class TestTestProvidersStep:
    """Tests for the 'test-providers' step."""

    def test_test_providers_uses_provider_health_agent(self):
        """test-providers step uses agent 'provider-doctor:provider-health'."""
        data = _load_recipe()
        step = _get_step(data, "test-providers")
        agent = step.get("agent", "")
        assert agent == "provider-doctor:provider-health", (
            f"test-providers agent must be 'provider-doctor:provider-health', got '{agent}'"
        )

    def test_test_providers_mentions_claude_opus(self):
        """test-providers instruction mentions Anthropic claude-opus-4-6."""
        data = _load_recipe()
        step = _get_step(data, "test-providers")
        instruction = _get_instruction(step)
        assert (
            "claude-opus-4-6" in instruction or "claude-opus" in instruction.lower()
        ), "test-providers instruction must mention claude-opus-4-6"

    def test_test_providers_mentions_claude_sonnet(self):
        """test-providers instruction mentions Anthropic claude-sonnet-4-5."""
        data = _load_recipe()
        step = _get_step(data, "test-providers")
        instruction = _get_instruction(step)
        assert (
            "claude-sonnet-4-5" in instruction or "claude-sonnet" in instruction.lower()
        ), "test-providers instruction must mention claude-sonnet-4-5"

    def test_test_providers_mentions_openai_gpt(self):
        """test-providers instruction mentions OpenAI gpt-5.4."""
        data = _load_recipe()
        step = _get_step(data, "test-providers")
        instruction = _get_instruction(step)
        assert "gpt-5.4" in instruction or "gpt" in instruction.lower(), (
            "test-providers instruction must mention gpt-5.4"
        )

    def test_test_providers_mentions_minimal_request(self):
        """test-providers instruction mentions sending a minimal request."""
        data = _load_recipe()
        step = _get_step(data, "test-providers")
        instruction = _get_instruction(step).lower()
        assert "minimal" in instruction or "minimum" in instruction, (
            "test-providers instruction must mention sending a minimal request"
        )

    def test_test_providers_mentions_response_time(self):
        """test-providers instruction mentions measuring response time."""
        data = _load_recipe()
        step = _get_step(data, "test-providers")
        instruction = _get_instruction(step).lower()
        assert (
            "response time" in instruction
            or "latency" in instruction
            or "measure" in instruction
        ), "test-providers instruction must mention measuring response time"

    def test_test_providers_mentions_table(self):
        """test-providers instruction mentions reporting as table."""
        data = _load_recipe()
        step = _get_step(data, "test-providers")
        instruction = _get_instruction(step).lower()
        assert "table" in instruction, (
            "test-providers instruction must mention reporting as table"
        )


# ---------------------------------------------------------------------------
# Tests: 'recommend' step
# ---------------------------------------------------------------------------


class TestRecommendStep:
    """Tests for the 'recommend' step."""

    def test_recommend_uses_provider_health_agent(self):
        """recommend step uses agent 'provider-doctor:provider-health'."""
        data = _load_recipe()
        step = _get_step(data, "recommend")
        agent = step.get("agent", "")
        assert agent == "provider-doctor:provider-health", (
            f"recommend agent must be 'provider-doctor:provider-health', got '{agent}'"
        )

    def test_recommend_mentions_healthy_providers(self):
        """recommend instruction mentions which providers are healthy."""
        data = _load_recipe()
        step = _get_step(data, "recommend")
        instruction = _get_instruction(step).lower()
        assert "health" in instruction, (
            "recommend instruction must mention healthy/unhealthy providers"
        )

    def test_recommend_mentions_failover_chain(self):
        """recommend instruction mentions the failover chain."""
        data = _load_recipe()
        step = _get_step(data, "recommend")
        instruction = _get_instruction(step).lower()
        assert (
            "failover" in instruction
            or "fail-over" in instruction
            or "chain" in instruction
        ), "recommend instruction must mention the failover chain"

    def test_recommend_mentions_action_items(self):
        """recommend instruction mentions specific action items."""
        data = _load_recipe()
        step = _get_step(data, "recommend")
        instruction = _get_instruction(step).lower()
        assert (
            "action" in instruction
            or "specific" in instruction
            or "item" in instruction
        ), "recommend instruction must mention action items"

    def test_recommend_mentions_api_keys(self):
        """recommend instruction mentions API keys."""
        data = _load_recipe()
        step = _get_step(data, "recommend")
        instruction = _get_instruction(step).lower()
        assert (
            "api key" in instruction
            or "api_key" in instruction
            or "api keys" in instruction
        ), "recommend instruction must mention API keys"

    def test_recommend_mentions_quotas(self):
        """recommend instruction mentions quotas."""
        data = _load_recipe()
        step = _get_step(data, "recommend")
        instruction = _get_instruction(step).lower()
        assert "quota" in instruction, "recommend instruction must mention quotas"

    def test_recommend_mentions_model_availability(self):
        """recommend instruction mentions model availability."""
        data = _load_recipe()
        step = _get_step(data, "recommend")
        instruction = _get_instruction(step).lower()
        assert "model" in instruction and (
            "availab" in instruction or "access" in instruction
        ), "recommend instruction must mention model availability"

    def test_recommend_mentions_network(self):
        """recommend instruction mentions network."""
        data = _load_recipe()
        step = _get_step(data, "recommend")
        instruction = _get_instruction(step).lower()
        assert "network" in instruction, "recommend instruction must mention network"

    def test_recommend_mentions_resilience(self):
        """recommend instruction mentions overall resilience assessment."""
        data = _load_recipe()
        step = _get_step(data, "recommend")
        instruction = _get_instruction(step).lower()
        assert "resilien" in instruction, (
            "recommend instruction must mention resilience assessment"
        )
