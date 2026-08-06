"""
ThinkTank — Ollama AI backend.
Sends chat messages to a local Ollama instance and returns the response text.
Falls back to a clear error message if Ollama is not running.
"""

import json
import urllib.error
import urllib.request
from thinktank.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT


def _post(endpoint: str, payload: dict) -> dict:
    url  = f"{OLLAMA_BASE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat(messages: list[dict], model: str = OLLAMA_MODEL) -> str:
    """
    Send a list of {role, content} messages to Ollama and return the reply text.
    Raises OllamaError with a human-readable message on failure.
    """
    try:
        result = _post(
            "/api/chat",
            {"model": model, "messages": messages, "stream": False},
        )
        return result["message"]["content"].strip()
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
    """Return (True, '') if Ollama is up and model exists, else (False, reason)."""
    try:
        result = _post("/api/show", {"name": model})
        if "modelfile" in result or "details" in result:
            return True, ""
        return False, f"Model '{model}' not found. Run: ollama pull {model}"
    except urllib.error.URLError:
        return False, (
            "Ollama is not running. Start it with: ollama serve\n"
            f"Then pull the model with: ollama pull {model}"
        )
    except Exception as exc:
        return False, f"Could not connect to Ollama: {exc}"


class OllamaError(Exception):
    """Raised when the Ollama backend cannot fulfil a request."""
