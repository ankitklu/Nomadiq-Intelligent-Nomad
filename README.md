# Nomadiq AI: Intelligent Nomad

An AI travel planner. Describe a trip in plain English, for example *"7 days in Luxembourg from Delhi under ₹10 lakhs"*. Nomadiq searches live flights, finds hotels, drafts a day-by-day itinerary and combines everything into one plan you can read, copy or download as a PDF.

## Features

- **Multi-agent pipeline** built with [LangGraph](https://github.com/langchain-ai/langgraph). Four agents run in sequence: flights → hotels → itinerary → final plan.
- **Live flight data** from the [Aviationstack](https://aviationstack.com/) API. Cities and countries in your request are mapped to airport codes automatically.
- **Hotel and destination research** through [Tavily](https://tavily.com/) web search.
- **Fast LLM responses** from [Groq](https://groq.com/) (`openai/gpt-oss-20b`).
- **Conversation memory** stored in PostgreSQL by a LangGraph checkpointer, so you can ask follow-up questions about the same trip.
- **Web UI**
  - Supports light and dark mode and works on phones.
  - A progress card shows each agent step while the plan is generated.
  - Results are split into tabs: Plan, Itinerary, Flights and Hotels.
  - You can copy any tab or download the plan as an A4 PDF.
- **Optional tracing** with [LangSmith](https://smith.langchain.com/).

## How it works

```text
User request
     │
     ▼
┌──────────────┐   ┌─────────────┐   ┌─────────────────┐   ┌─────────────┐
│ Flight agent │──▶│ Hotel agent │──▶│ Itinerary agent │──▶│ Final agent │──▶ Trip plan
│ Aviationstack│   │   Tavily    │   │    Groq LLM     │   │  Groq LLM   │
└──────────────┘   └─────────────┘   └─────────────────┘   └─────────────┘
                                │
                     PostgreSQL checkpointer
                     (memory for each thread_id)
```

## Project structure

```text
.
├── app.py               # FastAPI server: serves the UI and the /api/chat endpoint
├── backend.py           # LangGraph agents, graph wiring, Postgres checkpointer
├── test.py              # Scratch script for running the agent from the terminal
├── tools/
│   ├── flight_tool.py   # Aviationstack flight search + airport/country resolution
│   └── tavily_tool.py   # Tavily web search for hotels
├── templates/
│   └── index.html       # UI markup
├── static/
│   ├── style.css        # UI styles (light/dark themes, PDF layout)
│   └── script.js        # Chat logic, result tabs, copy and PDF export
└── requirements.txt
```

## Getting started

### Prerequisites

- Python 3.11
- [Conda](https://docs.conda.io/) (or any virtual environment tool)
- A PostgreSQL database. A free hosted one from Render, Neon or Supabase works.
- API keys for Groq, Tavily and Aviationstack

### 1. Create the environment

```bash
conda create -n nomadiq python=3.11 -y
```

### 2. Activate the environment

```bash
conda activate nomadiq
```

### 3. Install the requirements

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY="your-groq-key"
TAVILY_API_KEY="your-tavily-key"
AVIATIONSTACK_API_KEY="your-aviationstack-key"
DATABASE_URL="postgresql://user:password@host:5432/dbname"

# Optional: default departure airport when the request names only a destination
DEFAULT_ORIGIN_IATA="DEL"

# Optional: LangSmith tracing
LANGSMITH_TRACING="true"
LANGSMITH_ENDPOINT="https://api.smith.langchain.com"
LANGSMITH_API_KEY="your-langsmith-key"
LANGSMITH_PROJECT="nomadiq"
```

| Variable | Required | Description |
| --- | --- | --- |
| `GROQ_API_KEY` | Yes | Key for the Groq LLM API |
| `TAVILY_API_KEY` | Yes | Key for Tavily web search |
| `AVIATIONSTACK_API_KEY` | Yes | Key for live flight data |
| `DATABASE_URL` | Yes | PostgreSQL connection string. `sslmode=require` is added automatically if it's missing. |
| `DEFAULT_ORIGIN_IATA` | No | Fallback departure airport (default: `DAC`) |
| `LANGSMITH_*` | No | Turns on LangSmith tracing. Set `LANGSMITH_TRACING="false"` to turn it off. |

> `.env` is listed in `.gitignore`. Never commit your keys.

### 5. Run the app

```bash
python app.py
```

Open **http://localhost:8000** and describe your trip, or click one of the suggested trips.

To run the server with uvicorn directly:

```bash
uvicorn app:app --reload --port 8000
```

## API

### `POST /api/chat`

Runs the full agent pipeline for one message.

**Request**

```json
{
  "message": "Plan a 5-day Bali honeymoon from Mumbai under ₹2.5 lakhs",
  "thread_id": null
}
```

To start a new conversation, pass `thread_id: null`. To ask a follow-up about the same trip, pass the `thread_id` returned by the previous response.

**Response**

```json
{
  "thread_id": "user_3f2a…",
  "answer": "# 5-Day Bali Honeymoon …",
  "itinerary": "…",
  "flight_results": "…",
  "hotel_results": "…",
  "llm_calls": 4
}
```

Errors return a non-2xx status code with an `{"error": "..."}` body.

## Troubleshooting

| Error | Fix |
| --- | --- |
| `database "...postgresql://..." does not exist` | `DATABASE_URL` is malformed. Make sure it contains exactly one `postgresql://` URL. |
| `model ... does not exist or you do not have access to it` | Groq has retired that model. Update `model=` in `backend.py` to one listed in your [Groq console](https://console.groq.com/docs/models). |
| `Failed to resolve 'api.langsmith.com'` | Set `LANGSMITH_ENDPOINT="https://api.smith.langchain.com"`, or set `LANGSMITH_TRACING="false"`. |
| PDF download does nothing | The PDF library loads from cdnjs the first time you use it, so it needs internet access. |

## Tech stack

FastAPI · LangGraph · LangChain · Groq · Tavily · Aviationstack · PostgreSQL · vanilla HTML/CSS/JS · marked + DOMPurify · html2pdf.js

## License

[MIT](LICENSE) © 2026 Ankit Kumar Mishra

Live:- https://nomadiq-intelligent-nomad.onrender.com/