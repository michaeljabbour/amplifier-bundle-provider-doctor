"""TDD tests for bundle.md and behaviors/provider-resilience.yaml.

Tests cover:
- bundle.md exists at repo root with bundle name 'provider-doctor' v0.1.0
- bundle.md description covers provider resilience, session repair, support tooling
- bundle.md includes section references behaviors/provider-resilience.yaml
- bundle.md agents section declares session-doctor, provider-health, support with paths
- behaviors/provider-resilience.yaml is valid YAML
- behaviors/provider-resilience.yaml has bundle name 'provider-resilience' v0.1.0
- behaviors/provider-resilience.yaml providers section mounts provider-failover from ./modules/provider-failover
- provider-failover config: probe_interval=5
- 3 tiers: provider-anthropic/claude-opus-4-6/opus, provider-anthropic/claude-sonnet-4-5/sonnet, provider-openai/gpt-5.4/openai-codex
"""

from __future__ import annotations

import os

import yaml

BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_bundle_md_frontmatter() -> tuple[dict, str]:
    """Parse YAML frontmatter from bundle.md, returning (parsed_dict, full_content)."""
    bundle_path = os.path.join(BUNDLE_ROOT, "bundle.md")
    assert os.path.exists(bundle_path), "bundle.md must exist at repo root"
    with open(bundle_path) as f:
        content = f.read()
    assert content.startswith("---"), "bundle.md must start with YAML frontmatter '---'"
    # Find the closing ---
    end_idx = content.index("---", 3)
    frontmatter_str = content[3:end_idx].strip()
    return yaml.safe_load(frontmatter_str), content


def _load_provider_resilience_yaml() -> dict:
    """Load and parse behaviors/provider-resilience.yaml."""
    yaml_path = os.path.join(BUNDLE_ROOT, "behaviors", "provider-resilience.yaml")
    assert os.path.exists(yaml_path), "behaviors/provider-resilience.yaml must exist"
    with open(yaml_path) as f:
        return yaml.safe_load(f)


def _get_failover_provider(data: dict) -> dict:
    """Extract the provider-failover entry from the providers list."""
    providers = data.get("providers", [])
    pf = next(
        (
            p
            for p in providers
            if isinstance(p, dict) and p.get("module") == "provider-failover"
        ),
        None,
    )
    assert pf is not None, (
        "providers section must contain a provider-failover module entry"
    )
    return pf


# ---------------------------------------------------------------------------
# Tests: bundle.md
# ---------------------------------------------------------------------------


class TestBundleMdFrontmatter:
    """Tests for bundle.md frontmatter at repo root."""

    def test_bundle_md_exists(self):
        """bundle.md exists at repo root."""
        bundle_path = os.path.join(BUNDLE_ROOT, "bundle.md")
        assert os.path.exists(bundle_path)

    def test_bundle_name_is_provider_doctor(self):
        """bundle.md frontmatter has bundle name 'provider-doctor'."""
        fm, _ = _parse_bundle_md_frontmatter()
        assert fm["bundle"]["name"] == "provider-doctor"

    def test_bundle_version_is_0_1_0(self):
        """bundle.md frontmatter has version '0.1.0'."""
        fm, _ = _parse_bundle_md_frontmatter()
        assert fm["bundle"]["version"] == "0.1.0"

    def test_bundle_description_mentions_provider_resilience(self):
        """bundle.md description covers provider resilience."""
        fm, _ = _parse_bundle_md_frontmatter()
        desc = fm["bundle"]["description"].lower()
        assert "provider" in desc
        assert "resilience" in desc or "resilient" in desc or "failover" in desc

    def test_bundle_description_mentions_session_repair(self):
        """bundle.md description mentions session repair."""
        fm, _ = _parse_bundle_md_frontmatter()
        desc = fm["bundle"]["description"].lower()
        assert "session" in desc
        assert "repair" in desc or "recovery" in desc or "recover" in desc

    def test_bundle_description_mentions_support_tooling(self):
        """bundle.md description mentions support tooling."""
        fm, _ = _parse_bundle_md_frontmatter()
        desc = fm["bundle"]["description"].lower()
        assert "support" in desc


class TestBundleMdIncludes:
    """Tests for bundle.md includes section."""

    def test_includes_section_exists(self):
        """bundle.md has an includes section."""
        fm, _ = _parse_bundle_md_frontmatter()
        assert "includes" in fm, "bundle.md must have an 'includes' section"

    def test_includes_references_provider_resilience_behavior(self):
        """bundle.md includes section references behaviors/provider-resilience.yaml."""
        fm, _ = _parse_bundle_md_frontmatter()
        includes = fm.get("includes", [])
        # Look for an entry that references the behavior file by path
        behavior_refs = [
            entry
            for entry in includes
            if isinstance(entry, dict)
            and "behavior" in entry
            and "provider-resilience" in str(entry.get("behavior", ""))
        ]
        assert len(behavior_refs) > 0, (
            "includes must contain a 'behavior: behaviors/provider-resilience.yaml' entry"
        )

    def test_includes_provider_resilience_exact_path(self):
        """bundle.md includes behavior reference has exact path 'behaviors/provider-resilience.yaml'."""
        fm, _ = _parse_bundle_md_frontmatter()
        includes = fm.get("includes", [])
        found = any(
            isinstance(entry, dict)
            and entry.get("behavior") == "behaviors/provider-resilience.yaml"
            for entry in includes
        )
        assert found, (
            "includes must contain {behavior: behaviors/provider-resilience.yaml}"
        )


class TestBundleMdAgents:
    """Tests for bundle.md agents section."""

    def _get_agents_declare(self) -> list:
        fm, _ = _parse_bundle_md_frontmatter()
        agents = fm.get("agents", {})
        return agents.get("declare", [])

    def test_agents_section_exists(self):
        """bundle.md has an agents section."""
        fm, _ = _parse_bundle_md_frontmatter()
        assert "agents" in fm, "bundle.md must have an 'agents' section"

    def test_agents_declare_subsection_exists(self):
        """bundle.md agents section has a 'declare' subsection."""
        fm, _ = _parse_bundle_md_frontmatter()
        agents = fm.get("agents", {})
        assert "declare" in agents, "agents section must have a 'declare' list"

    def test_agents_declare_session_doctor(self):
        """bundle.md agents.declare includes session-doctor."""
        declare = self._get_agents_declare()
        names = [a.get("name", "") for a in declare if isinstance(a, dict)]
        assert "session-doctor" in names

    def test_agents_declare_provider_health(self):
        """bundle.md agents.declare includes provider-health."""
        declare = self._get_agents_declare()
        names = [a.get("name", "") for a in declare if isinstance(a, dict)]
        assert "provider-health" in names

    def test_agents_declare_support(self):
        """bundle.md agents.declare includes support."""
        declare = self._get_agents_declare()
        names = [a.get("name", "") for a in declare if isinstance(a, dict)]
        assert "support" in names

    def test_session_doctor_path(self):
        """session-doctor agent has path './agents/session-doctor.md'."""
        declare = self._get_agents_declare()
        sd = next(
            (
                a
                for a in declare
                if isinstance(a, dict) and a.get("name") == "session-doctor"
            ),
            None,
        )
        assert sd is not None
        assert sd.get("path") == "./agents/session-doctor.md"

    def test_provider_health_path(self):
        """provider-health agent has path './agents/provider-health.md'."""
        declare = self._get_agents_declare()
        ph = next(
            (
                a
                for a in declare
                if isinstance(a, dict) and a.get("name") == "provider-health"
            ),
            None,
        )
        assert ph is not None
        assert ph.get("path") == "./agents/provider-health.md"

    def test_support_path(self):
        """support agent has path './agents/support.md'."""
        declare = self._get_agents_declare()
        sup = next(
            (a for a in declare if isinstance(a, dict) and a.get("name") == "support"),
            None,
        )
        assert sup is not None
        assert sup.get("path") == "./agents/support.md"


# ---------------------------------------------------------------------------
# Tests: behaviors/provider-resilience.yaml
# ---------------------------------------------------------------------------


class TestProviderResilienceYamlExists:
    """Tests for existence and validity of behaviors/provider-resilience.yaml."""

    def test_yaml_file_exists(self):
        """behaviors/provider-resilience.yaml exists."""
        yaml_path = os.path.join(BUNDLE_ROOT, "behaviors", "provider-resilience.yaml")
        assert os.path.exists(yaml_path)

    def test_yaml_is_valid(self):
        """behaviors/provider-resilience.yaml is valid YAML (parseable)."""
        data = _load_provider_resilience_yaml()
        assert data is not None
        assert isinstance(data, dict)


class TestProviderResilienceYamlBundle:
    """Tests for the bundle metadata in provider-resilience.yaml."""

    def test_bundle_name_is_provider_resilience(self):
        """YAML bundle name is 'provider-resilience'."""
        data = _load_provider_resilience_yaml()
        assert data["bundle"]["name"] == "provider-resilience"

    def test_bundle_version_is_0_1_0(self):
        """YAML bundle version is '0.1.0'."""
        data = _load_provider_resilience_yaml()
        assert data["bundle"]["version"] == "0.1.0"


class TestProviderResilienceYamlProviders:
    """Tests for the providers section in provider-resilience.yaml."""

    def test_providers_section_exists(self):
        """YAML has a 'providers' section."""
        data = _load_provider_resilience_yaml()
        assert "providers" in data, "YAML must have a 'providers' section"

    def test_provider_failover_module_present(self):
        """providers section contains a provider-failover module entry."""
        data = _load_provider_resilience_yaml()
        pf = _get_failover_provider(data)
        assert pf is not None

    def test_provider_failover_source_is_local(self):
        """provider-failover source points to ./modules/provider-failover."""
        data = _load_provider_resilience_yaml()
        pf = _get_failover_provider(data)
        assert pf.get("source") == "./modules/provider-failover"

    def test_provider_failover_config_probe_interval(self):
        """provider-failover config has probe_interval=5."""
        data = _load_provider_resilience_yaml()
        pf = _get_failover_provider(data)
        assert pf["config"]["probe_interval"] == 5

    def test_provider_failover_config_no_retry_params(self):
        """provider-failover config must NOT have max_failures or retry_base_delay.

        Provider-level retry is handled by each provider internally.
        These params were removed to prevent retry amplification.
        """
        data = _load_provider_resilience_yaml()
        pf = _get_failover_provider(data)
        config = pf["config"]
        assert "max_failures" not in config, (
            "max_failures removed — provider-level retry handled internally"
        )
        assert "retry_base_delay" not in config, (
            "retry_base_delay removed — provider-level retry handled internally"
        )


class TestProviderResilienceYamlTiers:
    """Tests for the tiers configuration in provider-resilience.yaml."""

    def test_tiers_count_is_3(self):
        """provider-failover config has exactly 3 tiers."""
        data = _load_provider_resilience_yaml()
        pf = _get_failover_provider(data)
        tiers = pf["config"]["tiers"]
        assert len(tiers) == 3

    def test_tier1_provider_is_anthropic(self):
        """First tier provider is 'provider-anthropic'."""
        data = _load_provider_resilience_yaml()
        pf = _get_failover_provider(data)
        assert pf["config"]["tiers"][0]["provider"] == "provider-anthropic"

    def test_tier1_model_is_claude_opus_4_6(self):
        """First tier model is 'claude-opus-4-6'."""
        data = _load_provider_resilience_yaml()
        pf = _get_failover_provider(data)
        assert pf["config"]["tiers"][0]["model"] == "claude-opus-4-6"

    def test_tier1_label_is_opus(self):
        """First tier label is 'opus'."""
        data = _load_provider_resilience_yaml()
        pf = _get_failover_provider(data)
        assert pf["config"]["tiers"][0]["label"] == "opus"

    def test_tier2_provider_is_anthropic(self):
        """Second tier provider is 'provider-anthropic'."""
        data = _load_provider_resilience_yaml()
        pf = _get_failover_provider(data)
        assert pf["config"]["tiers"][1]["provider"] == "provider-anthropic"

    def test_tier2_model_is_claude_sonnet_4_5(self):
        """Second tier model is 'claude-sonnet-4-5'."""
        data = _load_provider_resilience_yaml()
        pf = _get_failover_provider(data)
        assert pf["config"]["tiers"][1]["model"] == "claude-sonnet-4-5"

    def test_tier2_label_is_sonnet(self):
        """Second tier label is 'sonnet'."""
        data = _load_provider_resilience_yaml()
        pf = _get_failover_provider(data)
        assert pf["config"]["tiers"][1]["label"] == "sonnet"

    def test_tier3_provider_is_openai(self):
        """Third tier provider is 'provider-openai'."""
        data = _load_provider_resilience_yaml()
        pf = _get_failover_provider(data)
        assert pf["config"]["tiers"][2]["provider"] == "provider-openai"

    def test_tier3_model_is_gpt_5_4(self):
        """Third tier model is 'gpt-5.4'."""
        data = _load_provider_resilience_yaml()
        pf = _get_failover_provider(data)
        assert pf["config"]["tiers"][2]["model"] == "gpt-5.4"

    def test_tier3_label_is_openai_codex(self):
        """Third tier label is 'openai-codex'."""
        data = _load_provider_resilience_yaml()
        pf = _get_failover_provider(data)
        assert pf["config"]["tiers"][2]["label"] == "openai-codex"
