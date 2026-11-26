"""Tests for Multi-Provider LLM Engine, Schema Normalization, Key Masking, and Agent Routing Fixes."""
import pytest
from types import SimpleNamespace
from fastapi.testclient import TestClient

from app.api.server import app
from app.agent.llm_provider import llm_manager, LLMManager
from app.agent.agent import DadusAgent
from app.agent.planner import task_planner
from app.memory.retrieval import MemoryRetriever
from app.config.settings import settings


@pytest.fixture
def client():
    return TestClient(app)


def test_tool_schema_normalization_for_strict_providers():
    """Verify Pydantic JSON schemas are flattened and stripped of $defs/anyOf/additionalProperties."""
    raw_tools = [
        {
            "type": "function",
            "function": {
                "name": "sample_tool",
                "description": "A sample tool",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "$defs": {"Sub": {"type": "string"}},
                    "properties": {
                        "query": {
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "description": "Search query"
                        }
                    },
                    "required": []
                }
            }
        }
    ]
    normalized = LLMManager.normalize_tools(raw_tools)
    params = normalized[0]["function"]["parameters"]
    assert "$defs" not in params
    assert "additionalProperties" not in params
    assert "anyOf" not in params["properties"]["query"]
    assert params["properties"]["query"]["type"] == "string"
    assert params["properties"]["query"]["description"] == "Search query"


def test_llm_direct_response_not_dropped_by_agent(monkeypatch):
    """Verify agent delivers LLM direct conversational replies instead of dropping them."""
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-valid-key-123456")

    def fake_chat_completion(messages, tools=None, backend_override=None):
        msg = SimpleNamespace(content="Quantum entanglement links two particles regardless of distance, boss.", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    monkeypatch.setattr(llm_manager, "chat_completion", fake_chat_completion)

    agent = DadusAgent()
    resp = agent.process_input("Explain quantum entanglement simply", session_id="test_llm_direct_reply")
    assert resp.status == "DONE"
    assert "Quantum entanglement" in resp.text


def test_llm_settings_api_masks_key_and_isolates_from_memory(client):
    """Verify /api/settings/llm saves config, masks API key, and never leaks into /api/memory or prompts."""
    save_resp = client.post("/api/settings/llm", json={
        "provider": "gemini",
        "api_key": "AIzaSyTestSecretKey12345678",
        "model": "gemini-2.5-flash"
    })
    assert save_resp.status_code == 200
    sdata = save_resp.json()
    assert sdata["success"] is True
    assert sdata["provider"] == "gemini"
    assert sdata["has_api_key"] is True
    assert sdata["api_key"].startswith("AIza")
    assert "TestSecretKey" not in sdata["api_key"]

    # Verify Neural Memory API and prompt retriever exclude system_config
    mem_resp = client.get("/api/memory")
    assert mem_resp.status_code == 200
    keys = [m["key"] for m in mem_resp.json()["memories"]]
    assert "__dadus_llm_config__" not in keys

    summary = MemoryRetriever.get_context_summary()
    assert "AIzaSyTestSecretKey" not in summary
    assert "__dadus_llm_config__" not in summary


def test_task_planner_does_not_falsely_split_conjunctions():
    """Verify non-command 'and' phrases are not misclassified as multi-step tool plans."""
    assert task_planner.is_multi_step_request("Explain AI and machine learning") is False
    assert task_planner.is_multi_step_request("Open Tom and Jerry") is False
    assert task_planner.is_multi_step_request("Open Chrome and set volume to 50") is True
    assert task_planner.is_multi_step_request("Open Chrome and then play Believer") is True
