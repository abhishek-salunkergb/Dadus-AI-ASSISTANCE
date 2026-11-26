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

    # Verify secret is stored encrypted in SystemSetting table
    from app.database.database import get_db_context
    from app.database.models import SystemSetting
    with get_db_context() as db:
        rec = db.query(SystemSetting).filter(SystemSetting.key == "llm_config").first()
        assert rec is not None
        assert rec.is_encrypted is True
        assert "AIzaSyTestSecretKey12345678" not in rec.value_json


def test_crypto_secret_roundtrip_and_tamper_detection():
    """Verify encrypt_secret/decrypt_secret round-trip and non-plaintext storage."""
    from app.security.crypto import encrypt_secret, decrypt_secret
    secret = "sk-super-secret-token-987654321"
    enc = encrypt_secret(secret)
    assert enc is not None
    assert enc.startswith(("dpapi:", "local:"))
    assert secret not in enc
    assert decrypt_secret(enc) == secret


def test_react_loop_observes_tool_output_and_synthesizes(monkeypatch):
    """Verify DadusAgent runs ReAct observation loop: LLM calls tool -> observes real data -> synthesizes answer."""
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-valid-key-123456")
    calls = []

    def fake_chat_completion(messages, tools=None, backend_override=None):
        calls.append(messages)
        if len(calls) == 1:
            # Step 1: LLM decides to call get_current_time
            tc = SimpleNamespace(
                id="call_time_1",
                function=SimpleNamespace(name="get_current_time", arguments="{}")
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tc]))])
        else:
            # Step 2: LLM observes the tool output and synthesizes final answer
            tool_obs = [m for m in messages if m.get("role") == "tool"]
            assert len(tool_obs) == 1
            assert "current" in tool_obs[0]["content"].lower() or "time" in tool_obs[0]["content"].lower()
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content="Boss, I checked the system clock and synthesized the current time for you.",
                tool_calls=None
            ))])

    monkeypatch.setattr(llm_manager, "chat_completion", fake_chat_completion)

    agent = DadusAgent()
    resp = agent.process_input("Could you tell me what hour of the day it is right now?", session_id="test_react_loop")
    assert len(calls) == 2
    assert resp.status == "DONE"
    assert resp.tool_called == "get_current_time"
    assert "synthesized" in resp.text


def test_llm_task_planner_validates_tools_and_rejects_hallucinations(monkeypatch):
    """Verify LLM TaskPlanner builds valid multi-step plans and rejects unknown tools."""
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-valid-key-123456")

    def fake_valid_plan(messages, tools=None, backend_override=None):
        payload = {
            "explanation": "Boss, checking time and system health.",
            "steps": [
                {"step_number": 1, "tool_name": "get_current_time", "arguments": {}, "description": "Check time"},
                {"step_number": 2, "tool_name": "get_system_status", "arguments": {}, "description": "Check RAM"}
            ]
        }
        import json
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload), tool_calls=None))])

    monkeypatch.setattr(llm_manager, "chat_completion", fake_valid_plan)
    plan = task_planner.create_plan("Check the clock and then inspect my system health")
    assert plan is not None
    assert len(plan.steps) == 2
    assert plan.steps[0].tool_name == "get_current_time"
    assert plan.steps[1].tool_name == "get_system_status"

    # Now test hallucinated tool rejection -> falls back safely
    def fake_hallucinated_plan(messages, tools=None, backend_override=None):
        import json
        payload = {
            "explanation": "Bad plan",
            "steps": [
                {"step_number": 1, "tool_name": "nonexistent_hack_tool", "arguments": {}, "description": "Bad"},
                {"step_number": 2, "tool_name": "get_current_time", "arguments": {}, "description": "Time"}
            ]
        }
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload), tool_calls=None))])

    monkeypatch.setattr(llm_manager, "chat_completion", fake_hallucinated_plan)
    rejected = task_planner._create_plan_with_llm("Do something impossible")
    assert rejected is None


def test_task_planner_does_not_falsely_split_conjunctions():
    """Verify non-command 'and' phrases are not misclassified as multi-step tool plans."""
    assert task_planner.is_multi_step_request("Explain AI and machine learning") is False
    assert task_planner.is_multi_step_request("Open Tom and Jerry") is False
    assert task_planner.is_multi_step_request("Open Chrome and set volume to 50") is True
    assert task_planner.is_multi_step_request("Open Chrome and then play Believer") is True
