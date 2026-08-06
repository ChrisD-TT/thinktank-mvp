"""
ThinkTank — AI backend.
Uses Groq cloud API (free tier) when GROQ_API_KEY is set,
falls back to local Ollama otherwise.
"""

import json
import os
import urllib.error
import urllib.request

from thinktank.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT

GROQ_API_KEY  = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL    = os.environ.get("GROQ_MODEL", "llama3-8b-8192")
GROQ_API_URL  = "https://api.groq.com/openai/v1/chat/completions"


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
    Uses Groq if GROQ_API_KEY is set, otherwise falls back to local Ollama.
    Raises OllamaError with a human-readable message on failure.
    """
    if GROQ_API_KEY:
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
    if GROQ_API_KEY:
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
