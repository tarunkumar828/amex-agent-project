## Use Case Approval Orchestrator Agent (UCAOA)

Enterprise-grade, LangGraph-powered orchestration service that drives a GenAI use case submission to **approval-ready** status by coordinating across governance systems (dummy APIs in this repo).

### What’s in this repo

- **FastAPI service** with JWT auth + RBAC
- **LangGraph orchestrator** (typed state, conditional routing, loops, HITL interrupts, persistence)
- **Persistence layer** (use cases, runs, artifacts, audit log)
- **Dummy internal APIs** behind clean client interfaces (JWT-authenticated)
- **Operational basics**: structured JSON logs, health endpoints, Docker/Compose, test scaffold

### Quickstart (dev)

1) Create env file:

```bash
cp config/env.example .env
```

2) Create a venv and install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3) Run the API (SQLite by default):

```bash
make dev
```

4) Explore docs:

- Swagger: `http://localhost:8080/docs`

### Local Postgres (optional)

```bash
docker compose up -d postgres
export UCA_DATABASE_URL='postgresql+asyncpg://uca:uca@localhost:5432/uca'
make dev
```

### Notes

- This codebase is intentionally **structured for scale** (clear boundaries: API/auth/db/clients/orchestrator/services).
- The “internal governance systems” are implemented as **dummy providers** to support end-to-end execution and testing.

