"""Smoke test confirming agent.py imports cleanly under pytest and that the
sys.path resolution (agent/ directory vs. the agent module colliding names)
actually resolves `import agent` to agent/agent.py, not a namespace package."""
from __future__ import annotations

import agent


def test_agent_module_imports_and_has_expected_symbols():
    assert hasattr(agent, "_HANGUP_RE")
    assert hasattr(agent, "entrypoint")
    assert callable(agent.entrypoint)
