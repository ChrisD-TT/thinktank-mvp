"""
ThinkTank — AI backend.
Priority order:
  1. OpenAI (gpt-4o-mini) — if OPENAI_API_KEY is set
  2. Ollama               — local fallback (free, no key needed)
"""

import json
import os
import urllib.error
import urllib.request

from thinktank.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT


OPENAI_MODEL     = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_ASK_MODEL = os.environ.get("OPENAI_ASK_MODEL", "gpt-4o")  # full model for Ask/chat
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


def _secret(key: str) -> str:
    """Read from Streamlit secrets first, fall back to environment variable."""
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        return val if val else os.environ.get(key, "")
    except Exception:
        return os.environ.get(key, "")


def _get_openai_key() -> str:
    """Get the OpenAI key — checks OPENAI_API_KEY and GEMINI_API_KEY (alias)."""
    return _secret("OPENAI_API_KEY") or _secret("GEMINI_API_KEY")


# ── OpenAI ────────────────────────────────────────────────────────────────────
def _openai_chat(messages: list[dict], temperature: float = 1.0) -> str:
    api_key = _get_openai_key().strip()
    payload = json.dumps({
        "model":      OPENAI_MODEL,
        "messages":   messages,
        "max_tokens": 2048,
        "temperature": temperature,
    }).encode("utf-8")
    req = urllib.request.Request(
        OPENAI_API_URL,
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"].strip()


# ── Ollama (local fallback) ───────────────────────────────────────────────────
def _ollama_chat(messages: list[dict], model: str = OLLAMA_MODEL) -> str:
    url  = f"{OLLAMA_BASE_URL}/api/chat"
    data = json.dumps({"model": model, "messages": messages, "stream": False}).encode("utf-8")
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["message"]["content"].strip()


# ── Ask-specific chat (uses gpt-4o at higher creativity) ────────────────────
def ask_chat(messages: list[dict]) -> str:
    """High-intelligence chat for the Ask tab. Uses gpt-4o at temp 1.2."""
    openai_key = _get_openai_key()
    if openai_key:
        api_key = openai_key.strip()
        payload = json.dumps({
            "model":       OPENAI_ASK_MODEL,
            "messages":    messages,
            "max_tokens":  4096,
            "temperature": 1.2,
        }).encode("utf-8")
        req = urllib.request.Request(
            OPENAI_API_URL,
            data=payload,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
        except Exception:
            pass  # fall through to standard chat
    return chat(messages)


# ── Public interface ──────────────────────────────────────────────────────────
def chat(messages: list[dict], model: str = OLLAMA_MODEL, temperature: float = 1.0) -> str:
    """
    Send messages and return the reply text.
    Uses OpenAI → Ollama in priority order.
    Raises OllamaError with a human-readable message on failure.
    """
    openai_key = _get_openai_key()
    if openai_key:
        try:
            return _openai_chat(messages, temperature=temperature)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise OllamaError(f"OpenAI API error {e.code}: {body}")
        except Exception as exc:
            raise OllamaError(f"OpenAI error: {exc}")
    else:
        try:
            return _ollama_chat(messages, model)
        except urllib.error.URLError:
            raise OllamaError(
                "Cannot reach Ollama. Make sure it is running (`ollama serve`) "
                f"and that the model is pulled (`ollama pull {model}`)."
            )
        except KeyError:
            raise OllamaError("Unexpected response format from Ollama.")
        except Exception as exc:
            raise OllamaError(f"Ollama error: {exc}")


def is_available(model: str = OLLAMA_MODEL) -> tuple[bool, str]:
    """Return (True, '') if the AI backend is reachable."""
    openai_key = _get_openai_key()
    if openai_key:
        try:
            _openai_chat([{"role": "user", "content": "ping"}])
            return True, ""
        except Exception as exc:
            return False, f"OpenAI error: {exc}"
    else:
        try:
            url  = f"{OLLAMA_BASE_URL}/api/show"
            data = json.dumps({"name": model}).encode("utf-8")
            req  = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            if "modelfile" in result or "details" in result:
                return True, ""
            return False, f"Model '{model}' not found. Run: ollama pull {model}"
        except urllib.error.URLError:
            return False, (
                "Ollama is not running. Start it with: ollama serve\n"
                f"Then pull the model: ollama pull {model}"
            )
        except Exception as exc:
            return False, f"Could not connect to Ollama: {exc}"


class OllamaError(Exception):
    """Raised when the AI backend cannot fulfil a request."""
