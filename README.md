# General Prime Secure (GPS)

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Local-first, privacy-first multi-agent AI system. Configurable via `profile.yaml`.

## Prerequisites

- Python 3.11+
- Node 18+
- macOS or Linux
- An LLM backend (LM Studio, Ollama, or llama.cpp)

## Quick Start

### 1. Run the setup wizard
```bash
cd scripts
python setup.py
```
This auto-detects LLM backends, generates `profile.yaml`, and creates a launch daemon.

### 2. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 3. Start the system
```bash
./start.sh
```

### 4. Open UI
http://localhost:3000

## Docker Quickstart

```bash
cp profile.yaml.example profile.yaml
# Edit profile.yaml with your LLM backend settings

docker compose up --build
```
The app will be available at http://localhost:8000.

## Architecture

- **Multi-backend inference** — supports LM Studio / vLLM (OpenAI-compatible), Ollama, and llama.cpp
- **Profile-driven config** — all models, agents, SMTP, CORS, and plugins configured in `profile.yaml`
- **Plugin system** — optional CRM plugin for outreach, campaigns, and content marketing
- **Agent orchestration** — classifier routes queries to specialist agents via message bus
- **Modular routes** — API endpoints split into `backend/routes/` for maintainability

## Agent System

| Agent | Role | Tools |
|-------|------|-------|
| Classifier | Fast-path query routing (TRIVIAL/SIMPLE/COMPLEX) | None |
| Hermes | Deep reasoning, complex analysis | All execution tools |
| Coder | Code generation, debugging, refactoring | File ops, shell, web, DB |
| Math | Math, logic, data analysis | None (pure reasoning) |
| Reasoner | Planning, multi-step logic | None (planning only) |
| Security | Security monitoring, advisory screening | None (advisory) |
| Claude | External API escalation for complex tasks | None |

Optional (CRM plugin):
| Outreach | Campaign management, prospect research | Campaign, email, web |
| Content | Content creation and publishing | Content drafting tools |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/query` | POST | Chat query |
| `/api/task` | POST | Start background task |
| `/api/tasks` | GET | List background tasks |
| `/api/models` | GET | Model status |
| `/api/memory` | GET | Search semantic memory |
| `/api/agents` | GET | List agents and state |
| `/api/channels` | GET | Agent communication channels |
| `/api/briefings` | GET | Task briefings |
| `/api/config` | GET | System configuration (no auth) |
| `/api/key/rotate` | POST | Rotate API key |
| `/conversations` | GET | List conversations |
| `/ws` | WebSocket | Live updates and streaming |

## Files

```
General Prime Secure/
├── backend/
│   ├── main.py              # FastAPI app creation, lifespan, CORS, static mount
│   ├── schema.py            # Database schema (all CREATE TABLE statements)
│   ├── models.py            # Pydantic request/response models
│   ├── auth.py              # API key auth, input sanitization
│   ├── routes/              # API route modules
│   │   ├── chat.py          # /api/query, /ws
│   │   ├── conversations.py # /conversations/*
│   │   ├── tasks.py         # /api/task*, /api/briefings*
│   │   ├── agents.py        # /api/agents*, /api/missions*
│   │   ├── memory.py        # /api/memory
│   │   ├── files.py         # /api/upload, /api/files/*
│   │   ├── channels.py      # /api/channels/*
│   │   ├── approvals.py     # /api/approve/*, /api/desktop/*
│   │   ├── overlays.py      # /api/overlay*
│   │   ├── marketing.py     # /api/marketing/*, /api/campaigns/*, /api/content/*, /api/personas/*
│   │   ├── email.py         # /api/smtp/*, /api/leads/inbound
│   │   ├── jobs.py          # /api/scheduled-jobs/*
│   │   └── health.py        # /health, /api/config, /api/key/rotate
│   ├── core.py              # AgentCore orchestration engine
│   ├── config.py            # Profile-driven configuration
│   ├── profile.py           # Profile loader (profile.yaml)
│   ├── db.py                # SQLite connection management
│   ├── inference/            # Multi-backend inference adapters
│   ├── memory.py            # Vector memory (embeddings)
│   ├── tools.py             # Tool functions for agents
│   ├── agents/              # Agent implementations
│   ├── orchestration/       # Message bus, scheduler, channels
│   ├── plugins/             # Plugin system (CRM)
│   └── tests/               # Security test suite
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Main application
│   │   ├── contexts/        # React contexts
│   │   ├── components/      # UI components
│   │   └── hooks/           # API and marketing hooks
│   └── package.json
├── scripts/
│   ├── setup.py             # Interactive setup wizard
│   └── install-daemon.sh    # macOS launchd installer
├── profile.yaml.example     # Reference configuration
├── start.sh                 # Startup script
└── com.gps.backend.plist.template
```

## Testing

```bash
pip install -r backend/requirements-dev.txt
python -m pytest backend/tests/ -v
```

## Configuration

Copy `profile.yaml.example` to `profile.yaml` and customize, or run `scripts/setup.py`.

Key sections:
- `system.name` — display name shown in the UI
- `inference.backends` — LLM server endpoints
- `inference.models` — model assignments (primary, classifier, security, embedder)
- `agents` — enable/disable individual agents
- `plugins` — enable/disable plugins (e.g., CRM)
- `smtp` — email configuration for outreach

## Security

- API key authentication on all endpoints (auto-generated on first run)
- WebSocket origin validation against configured CORS origins
- SQL query sandboxing (read-only, blocked dangerous keywords)
- Path traversal prevention on file operations
- Rate limiting with persistent storage
- Memory pollution prevention (tag validation, source tracking)

## Contributing

Contributions are welcome! Please open an issue to discuss proposed changes before submitting a pull request.

## License

General Prime Secure is licensed under the [Apache License 2.0](LICENSE).
