from agents import AGENT_REGISTRY


EXPECTED_AGENTS = {
    "pii_redaction",
    "pii_detection",
    "image_redaction",
    "content_safety",
    "prompt_injection_detection",
    "secret_credential_detection",
    "dlp_compliance",
    "human_review",
    "audit_compliance",
}


def test_registry_contains_expected_agents():
    assert EXPECTED_AGENTS.issubset(AGENT_REGISTRY.keys())


def test_registry_builds_agent_instances():
    for name in EXPECTED_AGENTS:
        agent = AGENT_REGISTRY[name]()
        result = agent.run("sample")
        assert result["agent"] == name
