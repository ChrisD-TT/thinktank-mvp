"""
ThinkTank — AI backend.
Priority order:
  1. Gemini (Google AI) — if GEMINI_API_KEY is set
  2. Ollama             — local fallback (free, no key needed)
"""

import json
import os
import urllib.error
import urllib.request

from thinktank.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT


GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")


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
    """Use google-generativeai SDK — supports both AIza and AQ. key formats."""
    import google.generativeai as genai

    api_key = _secret("GEMINI_API_KEY").strip()
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    # Convert to SDK format — system messages become first user turn
    history = []
    prompt  = ""
    for m in messages:
        if m["role"] == "system":
            # Prepend system content to first user message
            prompt = m["content"] + "\n\n"
        elif m["role"] == "user":
            history.append({"role": "user", "parts": [prompt + m["content"]]})
            prompt = ""
        elif m["role"] == "assistant":
            history.append({"role": "model", "parts": [m["content"]]})

    if not history:
        history = [{"role": "user", "parts": ["Hello"]}]

    # Last message is the actual prompt; rest is history
    last    = history[-1]["parts"][0]
    past    = history[:-1]

    chat    = model.start_chat(history=past)
    resp    = chat.send_message(last)
    return resp.text.strip()


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
    Uses Gemini → Ollama in priority order.
    Raises OllamaError with a human-readable message on failure.
    """
    gemini_key = _secret("GEMINI_API_KEY")
    if gemini_key:
        try:
            return _gemini_chat(messages)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise OllamaError(f"Gemini API error {e.code}: {body}")
        except Exception as exc:
            raise OllamaError(f"Gemini error: {exc}")
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
    gemini_key = _secret("GEMINI_API_KEY")
    if gemini_key:
        try:
            _gemini_chat([{"role": "user", "content": "ping"}])
            return True, ""
        except Exception as exc:
            return False, f"Gemini error: {exc}"
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
