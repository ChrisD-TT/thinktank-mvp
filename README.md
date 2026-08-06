# 🧠 ThinkTank MVP

**ThinkTank is my flagship project — a local-first AI decision engine and live collaboration platform built on Ollama. Submit ideas, run rapid analysis, structured scoring, and adversarial critique, then fire a Go/No-Go Gate decision. Host real-time group sessions in a password-protected room with an AI dealer and group voting. No API keys. No cloud. Just thinking, faster. Free. Private. Yours.**

---

## ✨ Features

| Tab | What it does |
|-----|---|
| **💬 Ask** | Multi-turn conversational AI with persistent chat memory |
| **💡 Ideas** | Submit ideas and run Rapid Bounce (wild / balanced / conservative reframes + experiments) |
| **📊 Analysis** | Refine, Score, and Critique any saved idea |
| **🚦 Gate** | AI-powered Go / No-Go verdict (✅ PROCEED / ⚠️ CAUTION / ❌ STOP) |
| **🎲 Room** | Collaborative room — up to 5 participants + 1 AI dealer, group voting, live gate |
| **⚙️ Admin** | Ollama health check, DB stats, config viewer |

---

## 🚀 Quick Start

### 1. Install Ollama
Download from [ollama.com/download](https://ollama.com/download) and install.

### 2. Pull a model
```bash
ollama pull llama3.2
```

### 3. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 4. Run ThinkTank
```bash
streamlit run app.py
```

Open **http://localhost:8501** in your browser.

---

## 📁 Project Structure

```
app.py                  # Streamlit entry point — run this
thinktank_room.py       # Room module (imported by app.py)
requirements.txt
thinktank/
├── config.py           # All settings (model, thresholds, DB path)
├── engine/
│   ├── ai.py           # Ollama API calls
│   ├── db.py           # SQLite persistence
│   ├── gate.py         # Gate decision engine
│   └── modes.py        # idea / refine / score / critique / gate / ask
└── ui/
    ├── components.py   # Shared UI helpers
    ├── ideas.py
    ├── analysis.py
    ├── gate_tab.py
    ├── ask_tab.py
    └── admin.py
```

---

## ⚙️ Configuration

Edit `thinktank/config.py` to change:

| Setting | Default | Description |
|---------|---------|-------------|
| `OLLAMA_MODEL` | `llama3.2` | Any model you have pulled |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_TIMEOUT` | `300` | Request timeout in seconds |
| `DB_PATH` | `./thinktank/thinktank.sqlite` | SQLite database location |
| `GATE_ABORT_RISK_AT_OR_ABOVE` | `4` | Risk threshold for STOP signal |
| `GATE_PROCEED_MIN_IMPACT` | `4` | Minimum impact for PROCEED |

### Switching models

```bash
ollama pull mistral     # or phi3, gemma2, deepseek-r1, etc.
```

Then in `thinktank/config.py`:
```python
OLLAMA_MODEL = "mistral"
```

---

## 🎲 Room Mode

The **Room** tab supports multi-user collaborative sessions:

- Create a room with a name and topic
- Up to **5 participants** can join and post messages, ideas, or questions
- The **AI dealer** silently facilitates, surfaces converging paths, and answers questions
- When enough ideas are posted, the dealer prompts the team to score
- All participants vote on ideas (Impact / Effort / Risk / Novelty, 1–5)
- When all seated participants have voted, the **Group Gate** fires automatically

---

## 📋 Requirements

- Python 3.11+
- [Ollama](https://ollama.com) running locally
- `streamlit >= 1.35.0`

---

## 📄 License

MIT — free to use, modify, and distribute.
