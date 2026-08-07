"""
ThinkTank — AI backend.
Priority order:
  1. Gemini (Google AI) — if GEMINI_API_KEY is set
  2. Groq               — if GROQ_API_KEY is set
  3. Ollama             — local fallback (free, no key needed)
"""

import json
import os
import urllib.error
import urllib.request

from thinktank.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT


GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

GROQ_MODEL    = os.environ.get("GROQ_MODEL", "llama3-8b-8192")
GROQ_API_URL  = "https://api.groq.com/openai/v1/chat/completions"


def _secret(key: str) -> str:
    """Read from Streamlit secrets first, fall back to environment variable.
    Called at request time (not import time) so secrets are always loaded."""
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        return val if val else os.environ.get(key, "")
    except Exception:
        return os.environ.get(key, "")


# ── Gemini ────────────────────────────────────────────────────────────────────
def _gemini_chat(messages: list[dict]) -> str:
    # Convert OpenAI-style messages to Gemini format
    contents = []
    for m in messages:
        role = "user" if m["role"] in ("user", "system") else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})

    payload = json.dumps({
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 2048},
    }).encode("utf-8")

    url = GEMINI_API_URL.format(model=GEMINI_MODEL, key=GEMINI_API_KEY)
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()


# ── Groq ──────────────────────────────────────────────────────────────────────
def _groq_chat(messages: list[dict]) -> str:
    payload = json.dumps({
        "model":    GROQ_MODEL,
        "messages": messages,
    }).encode("utf-8")
    req = urllib.request.Request(
        GROQ_API_URL,
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
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


# ── Public interface ──────────────────────────────────────────────────────────
def chat(messages: list[dict], model: str = OLLAMA_MODEL) -> str:
    """
    Send messages and return the reply text.
    Uses Gemini → Groq → Ollama in priority order.
    Raises OllamaError with a human-readable message on failure.
    """
    GEMINI_API_KEY = _secret("GEMINI_API_KEY")
    GROQ_API_KEY   = _secret("GROQ_API_KEY")
    if GEMINI_API_KEY:
        try:
            return _gemini_chat(messages)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise OllamaError(f"Gemini API error {e.code}: {body}")
        except Exception as exc:
            raise OllamaError(f"Gemini error: {exc}")
    elif GROQ_API_KEY:
        try:
            return _groq_chat(messages)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise OllamaError(f"Groq API error {e.code}: {body}")
        except Exception as exc:
            raise OllamaError(f"Groq error: {exc}")
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
    GEMINI_API_KEY = _secret("GEMINI_API_KEY")
    GROQ_API_KEY   = _secret("GROQ_API_KEY")
    if GEMINI_API_KEY:
        try:
            _gemini_chat([{"role": "user", "content": "ping"}])
            return True, ""
        except Exception as exc:
            return False, f"Gemini error: {exc}"
    elif GROQ_API_KEY:
        try:
            _groq_chat([{"role": "user", "content": "ping"}])
            return True, ""
        except Exception as exc:
            return False, f"Groq error: {exc}"
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
