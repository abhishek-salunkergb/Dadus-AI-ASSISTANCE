"""Multi-provider LLM Engine & Zero-Key Local Auto-Discovery for DADUS.
Supports Bring-Your-Own-Key (Gemini, Groq, OpenAI, OpenRouter, Custom)
as well as Zero-Key local LLMs (Ollama) with runtime UI configuration.
"""
import os
import json
import time
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel

from app.config.settings import settings
from app.database.database import get_db_context
from app.database.models import SystemSetting
from app.security.crypto import encrypt_secret, decrypt_secret

logger = logging.getLogger("DADUS.LLMProvider")

LLM_CONFIG_SETTING_KEY = "llm_config"

PROVIDER_PRESETS: Dict[str, Dict[str, Any]] = {
    "auto": {
        "label": "Smart Auto (Local Ollama + Built-in Engine)",
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.2",
        "requires_key": False,
        "signup_url": "https://ollama.com/download",
        "description": "Zero API key needed. Uses local Ollama if running, otherwise DADUS built-in deterministic engine."
    },
    "gemini": {
        "label": "Google Gemini (Free Tier Available)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.5-flash",
        "requires_key": True,
        "signup_url": "https://aistudio.google.com/apikey",
        "description": "Generous free tier from Google AI Studio. Great for everyday reasoning and tool calling."
    },
    "groq": {
        "label": "Groq Cloud (Ultra-Fast Free Tier)",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "requires_key": True,
        "signup_url": "https://console.groq.com/keys",
        "description": "Extremely fast inference with a free developer tier."
    },
    "openai": {
        "label": "OpenAI (GPT-4o / GPT-4o-mini)",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "requires_key": True,
        "signup_url": "https://platform.openai.com/api-keys",
        "description": "Industry-standard OpenAI models (requires paid OpenAI credits)."
    },
    "openrouter": {
        "label": "OpenRouter (All Models)",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
        "requires_key": True,
        "signup_url": "https://openrouter.ai/keys",
        "description": "Access free and paid models from OpenAI, Anthropic, Google, and Meta with one key."
    },
    "ollama": {
        "label": "Ollama (100% Local & Private)",
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.2",
        "requires_key": False,
        "signup_url": "https://ollama.com/download",
        "description": "Runs completely offline on your PC. Zero cost, zero API key, maximum privacy."
    },
    "custom": {
        "label": "Custom OpenAI-Compatible Endpoint",
        "base_url": "http://localhost:1234/v1",
        "default_model": "local-model",
        "requires_key": False,
        "signup_url": "",
        "description": "Connect LM Studio, vLLM, LocalAI, or any custom OpenAI-compatible server."
    }
}


class LLMConfig(BaseModel):
    provider: str = "auto"
    api_key: Optional[str] = None
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.2


def _mask_key(key: Optional[str]) -> Optional[str]:
    if not key or len(key) < 8:
        return "****" if key else None
    return f"{key[:4]}...{key[-4:]}"


def _clean_schema_node(node: Any) -> Any:
    """Recursively strips Pydantic/JSON-schema keywords that strict providers (like Gemini) reject."""
    if isinstance(node, dict):
        cleaned: Dict[str, Any] = {}
        # Flatten simple anyOf: [{"type": "string"}, {"type": "null"}] -> {"type": "string"}
        if "anyOf" in node and isinstance(node["anyOf"], list):
            non_null = [item for item in node["anyOf"] if isinstance(item, dict) and item.get("type") != "null"]
            if non_null:
                merged = dict(non_null[0])
                for k in ("description", "default", "title"):
                    if k in node and k not in merged:
                        merged[k] = node[k]
                return _clean_schema_node(merged)

        for k, v in node.items():
            if k in ("$defs", "definitions", "additionalProperties", "title"):
                continue
            cleaned[k] = _clean_schema_node(v)
        return cleaned
    elif isinstance(node, list):
        return [_clean_schema_node(i) for i in node]
    return node


class LLMManager:
    """Manages multi-provider LLM configuration, local Ollama auto-detection, and execution."""

    def __init__(self):
        self._ollama_cache_ts: float = 0.0
        self._ollama_models: List[str] = []

    def probe_ollama(self, force: bool = False) -> Tuple[bool, List[str]]:
        """Fast check (<400ms) for a local Ollama daemon."""
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return False, []

        now = time.time()
        if not force and (now - self._ollama_cache_ts) < 60.0:
            return len(self._ollama_models) > 0, list(self._ollama_models)

        self._ollama_cache_ts = now
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=0.4) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name") for m in data.get("models", []) if m.get("name")]
                    self._ollama_models = models
                    return len(models) > 0, models
        except Exception:
            self._ollama_models = []
        return False, []

    def _load_db_config(self) -> Optional[Dict[str, Any]]:
        try:
            with get_db_context() as db:
                rec = db.query(SystemSetting).filter(SystemSetting.key == LLM_CONFIG_SETTING_KEY).first()
                if rec and rec.value_json:
                    data = json.loads(rec.value_json)
                    if data.get("api_key"):
                        data["api_key"] = decrypt_secret(data["api_key"])
                    return data
        except Exception as ex:
            logger.debug(f"Could not load persisted LLM config: {ex}")
        return None

    def get_config(self, include_secret: bool = False) -> Dict[str, Any]:
        """Returns active LLM configuration, prioritizing DB-saved UI config over .env defaults."""
        in_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))
        db_cfg = None if in_pytest else self._load_db_config()

        if db_cfg:
            provider = db_cfg.get("provider", "auto")
            api_key = db_cfg.get("api_key")
            base_url = db_cfg.get("base_url") or PROVIDER_PRESETS.get(provider, {}).get("base_url", settings.OPENAI_BASE_URL)
            model = db_cfg.get("model") or PROVIDER_PRESETS.get(provider, {}).get("default_model", settings.LLM_MODEL)
            temperature = float(db_cfg.get("temperature", settings.LLM_TEMPERATURE))
        else:
            env_key = settings.OPENAI_API_KEY
            has_env_key = bool(env_key and env_key.strip() and not env_key.startswith("your_"))
            if has_env_key:
                provider = "openai" if "openai.com" in settings.OPENAI_BASE_URL else (
                    "gemini" if "generativelanguage.googleapis.com" in settings.OPENAI_BASE_URL else (
                        "groq" if "groq.com" in settings.OPENAI_BASE_URL else "custom"
                    )
                )
                api_key = env_key
            else:
                provider = "auto"
                api_key = None
            base_url = settings.OPENAI_BASE_URL
            model = settings.LLM_MODEL
            temperature = settings.LLM_TEMPERATURE

        ollama_running, ollama_models = self.probe_ollama()

        return {
            "provider": provider,
            "api_key": api_key if include_secret else _mask_key(api_key),
            "has_api_key": bool(api_key and api_key.strip() and not api_key.startswith("your_")),
            "base_url": base_url,
            "model": model,
            "temperature": temperature,
            "ollama_detected": ollama_running,
            "ollama_models": ollama_models,
            "presets": PROVIDER_PRESETS,
        }

    def save_config(
        self,
        provider: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2
    ) -> Dict[str, Any]:
        """Persists user LLM settings to SQLite and updates live runtime settings."""
        preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["custom"])
        existing = self._load_db_config() or {}

        # Preserve existing API key if UI sends masked key or empty placeholder during update
        resolved_key = api_key
        if resolved_key is not None and ("..." in resolved_key or resolved_key == "****"):
            resolved_key = existing.get("api_key")
        elif resolved_key is not None:
            resolved_key = resolved_key.strip() or None

        resolved_url = (base_url or preset["base_url"]).strip()
        resolved_model = (model or preset["default_model"]).strip()

        encrypted_key = encrypt_secret(resolved_key) if resolved_key else None
        payload = {
            "provider": provider,
            "api_key": encrypted_key,
            "base_url": resolved_url,
            "model": resolved_model,
            "temperature": temperature,
        }

        with get_db_context() as db:
            rec = db.query(SystemSetting).filter(SystemSetting.key == LLM_CONFIG_SETTING_KEY).first()
            if rec:
                rec.value_json = json.dumps(payload)
                rec.is_encrypted = bool(encrypted_key)
            else:
                db.add(SystemSetting(
                    key=LLM_CONFIG_SETTING_KEY,
                    value_json=json.dumps(payload),
                    is_encrypted=bool(encrypted_key)
                ))

        # Sync live settings in-memory
        settings.OPENAI_API_KEY = resolved_key
        settings.OPENAI_BASE_URL = resolved_url
        settings.LLM_MODEL = resolved_model
        settings.LLM_TEMPERATURE = temperature

        logger.info(f"Updated active LLM config: provider={provider}, model={resolved_model}")
        return self.get_config(include_secret=False)

    def resolve_active_backend(self) -> Optional[Dict[str, Any]]:
        """
        Determines whether an LLM backend (Cloud BYOK or Local Ollama) is ready to serve requests.
        Returns connection dict {api_key, base_url, model, provider, temperature} or None.
        """
        cfg = self.get_config(include_secret=True)
        provider = cfg["provider"]

        # Test isolation guard: if pytest explicitly cleared OPENAI_API_KEY, don't hit external networks
        if os.environ.get("PYTEST_CURRENT_TEST") and not cfg["has_api_key"]:
            return None

        if provider == "auto":
            if cfg["has_api_key"]:
                return {
                    "provider": "cloud",
                    "api_key": cfg["api_key"],
                    "base_url": cfg["base_url"],
                    "model": cfg["model"],
                    "temperature": cfg["temperature"],
                }
            ollama_ok, ollama_models = self.probe_ollama()
            if ollama_ok and ollama_models:
                return {
                    "provider": "ollama",
                    "api_key": "ollama",
                    "base_url": "http://localhost:11434/v1",
                    "model": ollama_models[0],
                    "temperature": cfg["temperature"],
                }
            return None

        if provider == "ollama":
            ollama_ok, ollama_models = self.probe_ollama()
            if not ollama_ok:
                return None
            chosen_model = cfg["model"] if cfg["model"] in ollama_models else (ollama_models[0] if ollama_models else cfg["model"])
            return {
                "provider": "ollama",
                "api_key": "ollama",
                "base_url": cfg["base_url"] or "http://localhost:11434/v1",
                "model": chosen_model,
                "temperature": cfg["temperature"],
            }

        if provider == "custom":
            return {
                "provider": "custom",
                "api_key": cfg["api_key"] or "custom-local",
                "base_url": cfg["base_url"],
                "model": cfg["model"],
                "temperature": cfg["temperature"],
            }

        # Cloud BYOK providers (gemini, groq, openai, openrouter)
        if cfg["has_api_key"]:
            return {
                "provider": provider,
                "api_key": cfg["api_key"],
                "base_url": cfg["base_url"],
                "model": cfg["model"],
                "temperature": cfg["temperature"],
            }
        return None

    @staticmethod
    def normalize_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sanitize OpenAI tool schemas for cross-provider compatibility (Gemini, Groq, Ollama)."""
        normalized = []
        for tool in tools:
            fn = tool.get("function", {})
            params = fn.get("parameters", {})
            clean_params = _clean_schema_node(params)
            if not clean_params.get("properties"):
                # Some providers (e.g. Gemini) reject empty properties without type/object
                clean_params = {"type": "object", "properties": {}}
            normalized.append({
                "type": "function",
                "function": {
                    "name": fn.get("name"),
                    "description": fn.get("description", ""),
                    "parameters": clean_params,
                }
            })
        return normalized

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        backend_override: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Executes a chat completion using the active or overridden LLM backend."""
        from openai import OpenAI

        backend = backend_override or self.resolve_active_backend()
        if not backend:
            raise RuntimeError("No active LLM backend configured.")

        client = OpenAI(
            api_key=backend["api_key"],
            base_url=backend["base_url"],
            timeout=settings.LLM_TIMEOUT_SECONDS
        )

        kwargs: Dict[str, Any] = {
            "model": backend["model"],
            "messages": messages,
            "temperature": backend.get("temperature", settings.LLM_TEMPERATURE),
        }
        if tools:
            kwargs["tools"] = self.normalize_tools(tools)
            kwargs["tool_choice"] = "auto"

        return client.chat.completions.create(**kwargs)

    def test_connection(
        self,
        provider: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Verifies connectivity and credentials for a given LLM configuration."""
        preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["custom"])
        existing = self._load_db_config() or {}

        resolved_key = api_key
        if resolved_key and ("..." in resolved_key or resolved_key == "****"):
            resolved_key = existing.get("api_key")

        if preset["requires_key"] and not (resolved_key and resolved_key.strip()):
            return {
                "success": False,
                "message": f"An API key is required for {preset['label']}. You can get one at {preset['signup_url']}."
            }

        if provider in ("auto", "ollama"):
            ok, models = self.probe_ollama(force=True)
            if not ok:
                return {
                    "success": False,
                    "message": "Local Ollama was not detected on localhost:11434. DADUS will use its built-in deterministic engine, or you can select Gemini/Groq for cloud AI."
                }
            test_model = model if model in models else models[0]
            backend = {
                "provider": "ollama",
                "api_key": "ollama",
                "base_url": base_url or "http://localhost:11434/v1",
                "model": test_model,
                "temperature": 0.1,
            }
        else:
            backend = {
                "provider": provider,
                "api_key": (resolved_key or "custom-local").strip(),
                "base_url": (base_url or preset["base_url"]).strip(),
                "model": (model or preset["default_model"]).strip(),
                "temperature": 0.1,
            }

        try:
            resp = self.chat_completion(
                messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                tools=None,
                backend_override=backend
            )
            reply = (resp.choices[0].message.content or "").strip()
            return {
                "success": True,
                "message": f"Connected to {backend['model']} successfully! Response: {reply[:40]}",
                "model": backend["model"]
            }
        except Exception as ex:
            return {
                "success": False,
                "message": f"Connection failed: {str(ex)}"
            }


llm_manager = LLMManager()
