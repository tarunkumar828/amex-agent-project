### Use Case Approval Orchestrator Agent (UCAOA) — Codebase Deep Dive

This document explains the generated codebase implementing the design in `amex-project-detailed-documentation.md`.

It is written as an internal engineering handoff: architecture boundaries, module responsibilities, and a “spec → code” mapping that points to the exact modules/functions implementing each agentic capability (LangGraph orchestration, tool calling, loops, HITL interrupts, persistence/checkpointing, auditability, JWT auth).

---

### 1) Executive overview

**What this service is**

- A **FastAPI** backend that accepts a GenAI use-case submission, persists it, and runs a **LangGraph** stateful orchestrator to drive the submission toward **approval-ready** status.
- The orchestrator coordinates with multiple “governance systems” via **tool calls**. In this repo, those systems are implemented as **dummy internal APIs** under `/internal/v1/*` and still require **JWT** like a real enterprise integration.

**Key enterprise design points**

- **Clear boundaries**: API layer → service layer → orchestrator → governance clients → persistence.
- **Typed state** for agent orchestration (`TypedDict`), deterministic routing, and testability.
- **Persistence-first**: use cases, runs, audit events, and artifacts stored in DB; long-running approvals supported.
- **JWT + RBAC**: role enforcement for public endpoints and internal tool endpoints.
- **Checkpointing**: run state is persisted after each node execution (LangGraph stream).

---

### 2) Repository structure (high-level)

Core layout uses a “src/” package style:

- `src/uca_orchestrator/api/`: FastAPI app, routers, dependencies
- `src/uca_orchestrator/auth/`: JWT validation, Principal model, RBAC dependencies
- `src/uca_orchestrator/db/`: SQLAlchemy async models + session wiring + repositories
- `src/uca_orchestrator/governance_clients/`: client used by orchestrator to call governance systems
- `src/uca_orchestrator/orchestrator/`: LangGraph typed state, nodes, routing, graph compilation, interrupts
- `src/uca_orchestrator/services/`: service layer coordinating DB + orchestrator runtime
- `src/uca_orchestrator/observability/`: structured logging + request context middleware
- `tests/`: smoke tests

Operational/support files:

- `requirements.txt`, `requirements-dev.txt`
- `Dockerfile`, `docker-compose.yml`
- `alembic/`, `alembic.ini` (migration scaffolding)
- `config/env.example` (safe-to-commit env template)

---

### 3) Runtime architecture & boundaries

The runtime is intentionally “enterprise layered”:

**API Layer (FastAPI routers)**

- Accepts external requests (use-case owner actions, governance reviewer actions).
- Enforces RBAC via dependencies.
- Calls the service layer.

**Service Layer**

- Owns transactional integrity (DB session).
- Creates runs, executes orchestrations, persists artifacts/audits, and handles interrupts/resume.
- The orchestrator itself is treated as a deterministic engine, not as “the app”.

**Orchestrator Layer (LangGraph)**

- Implements nodes and routing.
- Calls governance tools through a client boundary (`InternalApiClient`).
- Uses a typed state object (`UseCaseState`).
- Raises a specific interrupt exception to trigger HITL.

**Governance Tools Layer**

- Clients call internal endpoints with JWT (“tool auth”).
- Internal endpoints simulate enterprise governance systems (policy, approvals, evaluations, etc.).

**Persistence Layer**

- DB models: use cases, runs, artifacts, audit events.
- Repositories isolate data access.

---

### 4) Configuration & settings

**File**: `src/uca_orchestrator/settings.py`

- Central `Settings` object (Pydantic Settings) reads environment variables with prefix `UCA_`.
- Relevant config:
  - `UCA_DATABASE_URL` (SQLite by default; Postgres supported)
  - `UCA_JWT_*` (issuer/audience/secret/alg)
  - `UCA_MAX_REMEDIATION_ATTEMPTS`

**Example env template**: `config/env.example`

---

### 5) Observability: structured logs + request context

**Structured logging**

- **File**: `src/uca_orchestrator/observability/logging.py`
- Uses `structlog` JSON renderer with:
  - timestamps
  - log levels
  - logger name
  - service name
  - contextvars merge (so request metadata gets attached)

**Request context middleware**

- **File**: `src/uca_orchestrator/observability/middleware.py`
- Ensures every request has `x-request-id` and binds request metadata into structlog contextvars.

---

### 6) Authentication & Authorization (JWT + RBAC)

**Principal model**

- **File**: `src/uca_orchestrator/auth/models.py`
- `Principal(subject, roles)` is the typed identity injected into endpoints.

**JWT issue + decode/validate**

- **File**: `src/uca_orchestrator/auth/jwt.py`
- `decode_and_validate()` enforces:
  - issuer (`iss`)
  - audience (`aud`)
  - required claims (`exp`, `iat`, `sub`, etc.)

**FastAPI auth dependencies**

- **File**: `src/uca_orchestrator/auth/deps.py`
- `get_principal()` parses bearer token → validates JWT → returns `Principal`.
- `require_roles(*roles)` enforces RBAC. Admin bypass supported (`role=admin`).

**Dev-only token minting**

- **File**: `src/uca_orchestrator/api/routers/dev_auth.py`
- `POST /v1/dev/token` mints a token in non-prod envs.

Roles used in this codebase (minimum set):

- `use_case_owner`: can register and orchestrate their use case
- `governance_reviewer`: can resume interrupted runs (HITL)
- `internal_system`: used by tool calls against internal dummy governance endpoints
- `admin`: bypass role checks for debugging/ops

---

### 7) Persistence layer (DB models, sessions, repositories)

**DB engine + session maker**

- **File**: `src/uca_orchestrator/db/session.py`
- `create_engine(settings)`: async engine
- `create_sessionmaker(engine)`: async session factory

**DB init (dev/test convenience)**

- **File**: `src/uca_orchestrator/db/init_db.py`
- Creates tables automatically in `dev`/`test` environments (see app startup hook).
- Production expectation: use Alembic migrations.

**Schema**

- **File**: `src/uca_orchestrator/db/models.py`
- Key entities:
  - `UseCase`: owner, submission payload, classification snapshot, approvals snapshot, eval metrics snapshot, status/risk, missing artifacts snapshot
  - `Run`: execution status, persisted `state` (checkpointed), interruption payload, remediation attempts, errors
  - `Artifact`: generated artifacts persisted per use case (redaction plan, threat model, etc.)
  - `AuditEvent`: append-only record of system/agent actions

**Repository pattern**

- **Files**:
  - `src/uca_orchestrator/db/repositories/use_cases.py`
  - `src/uca_orchestrator/db/repositories/runs.py`
  - `src/uca_orchestrator/db/repositories/artifacts.py`
  - `src/uca_orchestrator/db/repositories/audit.py`

These encapsulate CRUD operations and provide a stable seam for future optimizations (indexes, pagination, caching, partitioning, etc.).

---

### 8) Internal “dummy governance systems” (tool endpoints)

The design doc expects multiple governance integrations (registration, policy, approvals, eval, netsec, firewall, hydra).
In this repo, we implement them as internal APIs and keep the integration boundary realistic via JWT auth:

**Router aggregator**

- **File**: `src/uca_orchestrator/api/routers/internal/router.py`
- Prefix: `/internal/v1`

**Systems**

- **Registration**: `src/uca_orchestrator/api/routers/internal/systems/registration.py`
  - `GET /internal/v1/registration/{use_case_id}/status`
- **Policy**: `src/uca_orchestrator/api/routers/internal/systems/policy.py`
  - `POST /internal/v1/policy/requirements`
- **Approvals**: `src/uca_orchestrator/api/routers/internal/systems/approvals.py`
  - `GET /internal/v1/approvals/{use_case_id}/status`
- **Evaluations**: `src/uca_orchestrator/api/routers/internal/systems/evaluations.py`
  - `POST /internal/v1/evaluations/{use_case_id}/trigger`
  - `GET /internal/v1/evaluations/{use_case_id}/status`
- **NetSec baseline**: `src/uca_orchestrator/api/routers/internal/systems/netsec.py`
  - `GET /internal/v1/netsec/{use_case_id}/baseline`
- **AI Firewall check**: `src/uca_orchestrator/api/routers/internal/systems/firewall.py`
  - `GET /internal/v1/firewall/{use_case_id}/check`
- **Hydra readiness**: `src/uca_orchestrator/api/routers/internal/systems/hydra.py`
  - `GET /internal/v1/hydra/{use_case_id}/readiness`
- **Artifact status tool** (used for gap analysis): `src/uca_orchestrator/api/routers/internal/systems/artifacts.py`
  - `GET /internal/v1/artifacts/{use_case_id}/status`

All of these are protected by:

- `Depends(require_roles("internal_system"))`

…so the orchestrator must authenticate like any other internal service would.

---

### 9) Governance client boundary (tool calling)

**File**: `src/uca_orchestrator/governance_clients/internal_http.py`

The orchestrator never calls internal endpoints “directly”; it calls a client boundary that:

- Mints a short-lived JWT with role `internal_system`
- Attaches `Authorization: Bearer ...`
- Calls `/internal/v1/*` endpoints using `httpx.AsyncClient`

This is a deliberate enterprise seam: you can replace this client with real network calls to real services later (same interface), or split internal tools into separate microservices.

---

### 10) Orchestrator: state, nodes, routing, loops, HITL

#### 10.1 Typed state schema

**File**: `src/uca_orchestrator/orchestrator/state.py`

Matches the doc’s `UseCaseState` concept: submission, classification, missing artifacts, approval/eval snapshots, risk level, remediation attempts, audit log, HITL payload.

Implementation details (important):

- State keys that may be updated by multiple parallel nodes use **reducers** (via `typing.Annotated[...]`) so merges are deterministic:
  - `audit_log`: append-only reducer
  - `classification`, `approval_status`, `eval_metrics`: dict merge reducer
- Additional keys used by the implementation:
  - `policy`: policy requirements snapshot
  - `artifact_types_present`: artifact type list (for accurate gap analysis)
  - `generated_artifacts`: artifacts generated by the graph (persisted by service layer)
  - `eval_failed` / `approval_rejected`: explicit routing flags

**Reducers file**: `src/uca_orchestrator/orchestrator/reducers.py`

#### 10.2 Interrupt / HITL mechanism

**File**: `src/uca_orchestrator/orchestrator/interrupts.py`

- `HumanInterrupt(reason, payload)` is raised by the graph when escalation is required.
- The service layer catches it and persists the interruption context into `runs.interrupted_*`.

#### 10.3 Nodes and “agent logic”

**File**: `src/uca_orchestrator/orchestrator/nodes.py`

This is where the doc’s node responsibilities are implemented:

- **Entry node** (`entry_node`)
  - Validates minimum state and initializes defaults.
- **Classification node** (`classify_node`)
  - Determines PCI / deployment / provider, and derives a risk level.
- **Parallel fetch stage (true LangGraph fan-out/fan-in)**
  - Implemented as separate fetch nodes (run in parallel by the graph scheduler):
    - `fetch_registration_node`
    - `fetch_policy_node`
    - `fetch_approvals_node`
    - `fetch_eval_status_node`
    - `fetch_artifacts_status_node`
  - These nodes return **partial state updates** (deltas), merged by reducers at fan-in.
- **Gap analysis node** (`gap_analysis_node`)
  - Computes missing artifacts from policy requirements vs artifacts present.
- **Artifact generation node** (`artifact_generation_node`)
  - Generates requested artifacts (dummy generation in this repo) and stores them in state as `generated_artifacts` so the service layer can persist them.
- **Evaluation check node** (`eval_check_node`)
  - Ensures required evals exist; triggers missing ones; applies threshold logic (example: toxicity).
- **Approval check node** (`approval_check_node`)
  - Pulls approval status and detects rejections.
- **Remediation node** (`remediation_node`)
  - Increments remediation counter and plans corrective action (dummy logic here).
- **Escalation node** (`escalation_node`)
  - Raises `HumanInterrupt` if risk is HIGH or attempts exceed cap.

#### 10.4 Conditional routing and remediation loop

**File**: `src/uca_orchestrator/orchestrator/nodes.py`

- `route_after_gap`: if missing → artifact generation, else eval check
- `route_after_eval`: if eval failed → remediation, else approval check
- `route_after_approval`: if approval rejected → remediation, else finish
- `route_after_remediation`: loops back to generate artifacts or re-run evals

#### 10.5 Graph compilation

**File**: `src/uca_orchestrator/orchestrator/graph.py`

- `build_graph(client, max_attempts)` wires node edges and conditional routing.

---

### 11) “Persistence & checkpointing” (per-node checkpoints)

The design doc calls out checkpoints that enable:

- multi-day runs
- crash recovery
- audit replay

**Where implemented**

- **File**: `src/uca_orchestrator/services/orchestration_service.py`
- Method: `_execute_with_checkpoints(...)`

**How it works**

- Runs the compiled LangGraph graph using `graph.astream(..., stream_mode="updates")`
- After each yielded update (i.e., after each node execution), it:
  - writes the updated state into `runs.state`
  - writes newly appended audit entries into `audit_events`
  - commits the transaction (so the checkpoint is durable)

This is the durable “checkpoint per node” implementation.

---

### 12) Service layer: orchestration lifecycle

**File**: `src/uca_orchestrator/services/orchestration_service.py`

Key entry points:

- `start(use_case_id, actor)`:
  - creates a `Run` with initial state derived from `UseCase`
  - creates an `AuditEvent` `RUN_CREATED`
- `execute(run_id, actor)`:
  - builds `InternalApiClient` and LangGraph
  - executes with checkpoint persistence
  - on success: persists snapshots + artifacts + audit log + marks `UseCaseStatus=APPROVAL_READY`
  - on interrupt: persists interruption payload and marks `UseCaseStatus=INTERRUPTED`
- `resume(run_id, actor, decision)`:
  - merges HITL decision into state
  - marks run running
  - re-invokes `execute`

This is the canonical “enterprise orchestration engine” boundary where transactions and durable history are enforced.

---

### 13) Public API surface (external endpoints)

#### 13.1 Health endpoints

- **File**: `src/uca_orchestrator/api/routers/health.py`
- `/healthz`: liveness
- `/readyz`: DB connectivity probe (`SELECT 1`)

#### 13.2 Use-case owner endpoints

- **File**: `src/uca_orchestrator/api/routers/use_cases.py`

Endpoints:

- `POST /v1/use-cases/register` (RBAC: `use_case_owner`)
  - Creates a use case + creates an initial run (`OrchestrationService.start`)
- `POST /v1/use-cases/{use_case_id}/orchestrate` (RBAC: `use_case_owner`)
  - Executes the latest run (or creates one if missing)
  - Uses in-process `httpx.ASGITransport` so tool calls hit the internal endpoints without external networking
- `GET /v1/use-cases/{use_case_id}` (RBAC: `use_case_owner`)
  - Returns current snapshot fields
- `GET /v1/use-cases/{use_case_id}/audit` (RBAC: `use_case_owner`)
  - Lists audit events
- `GET /v1/use-cases/{use_case_id}/artifacts` (RBAC: `use_case_owner`)
  - Lists stored artifacts

#### 13.3 Governance reviewer endpoint (resume HITL)

- **File**: `src/uca_orchestrator/api/routers/runs.py`
- `POST /v1/runs/{run_id}/resume` (RBAC: `governance_reviewer`)

---

### 14) Where each “agentic capability” is implemented (spec → code map)

This is the “what you asked for” index: each major capability from the design doc and where it lives.

- **Typed state**
  - `src/uca_orchestrator/orchestrator/state.py` (`UseCaseState`)
- **Entry validation + initialization**
  - `src/uca_orchestrator/orchestrator/nodes.py` (`entry_node`)
- **Classification**
  - `src/uca_orchestrator/orchestrator/nodes.py` (`classify_node`)
- **Tool calling / governance system orchestration**
  - Client boundary: `src/uca_orchestrator/governance_clients/internal_http.py` (`InternalApiClient`)
  - Tools (dummy): `src/uca_orchestrator/api/routers/internal/systems/*`
  - Node fanout: `src/uca_orchestrator/orchestrator/graph.py` (fan-out into `fetch_*` nodes)
- **Parallel execution**
  - `src/uca_orchestrator/orchestrator/graph.py` (true fan-out/fan-in) + reducers
- **Reducers (safe merge at fan-in)**
  - `src/uca_orchestrator/orchestrator/reducers.py`
  - `src/uca_orchestrator/orchestrator/state.py` (`Annotated[...]` on merge-sensitive keys)
- **Gap analysis**
  - `src/uca_orchestrator/orchestrator/nodes.py` (`gap_analysis_node`)
  - Tool for “what exists”: `src/uca_orchestrator/api/routers/internal/systems/artifacts.py`
- **Artifact generation**
  - `src/uca_orchestrator/orchestrator/nodes.py` (`artifact_generation_node`)
  - Persistence: `src/uca_orchestrator/services/orchestration_service.py` (`_persist_artifacts`)
  - Storage: `src/uca_orchestrator/db/models.py` (`Artifact`)
- **Evaluation validation**
  - Node logic: `src/uca_orchestrator/orchestrator/nodes.py` (`eval_check_node`)
  - Dummy evaluation tool: `src/uca_orchestrator/api/routers/internal/systems/evaluations.py`
- **Approval monitoring**
  - Node logic: `src/uca_orchestrator/orchestrator/nodes.py` (`approval_check_node`)
  - Dummy approvals tool: `src/uca_orchestrator/api/routers/internal/systems/approvals.py`
- **Remediation loop**
  - Looping routes: `route_after_eval`, `route_after_approval`, `route_after_remediation`
  - Counter: `remediation_attempts` in state and `runs.remediation_attempts`
- **Escalation interrupt**
  - `src/uca_orchestrator/orchestrator/nodes.py` (`escalation_node` raising `HumanInterrupt`)
- **HITL resume**
  - API: `src/uca_orchestrator/api/routers/runs.py` (`/resume`)
  - Service: `src/uca_orchestrator/services/orchestration_service.py` (`resume`)
- **Persistence**
  - Schema: `src/uca_orchestrator/db/models.py`
  - Repos: `src/uca_orchestrator/db/repositories/*`
- **Checkpointing**
  - `src/uca_orchestrator/services/orchestration_service.py` (`_execute_with_checkpoints`)
- **Audit trace**
  - State-level: `audit_log` appended via deltas + reducer (append-only)
  - Durable: `AuditEvent` persisted in `_execute_with_checkpoints` and `_persist_audit`
- **JWT auth**
  - `src/uca_orchestrator/auth/jwt.py`, `src/uca_orchestrator/auth/deps.py`
- **RBAC**
  - `require_roles(...)` usage across routers (public + internal tools)

---

### 15) Example end-to-end flow (user input → response, and what happens in between)

This is one representative flow for a use case owner.

#### Step A — Mint a dev token (non-prod only)

1) Call:
   - `POST /v1/dev/token`
2) Body example:
   - subject: `"alice"`
   - roles: `["use_case_owner"]`
3) Response:
   - `{ "access_token": "...", "token_type": "bearer" }`

**What happens**

- Router: `src/uca_orchestrator/api/routers/dev_auth.py`
- Token minted by: `src/uca_orchestrator/auth/jwt.py` (`issue_token`)

#### Step B — Register a use case

1) Call:
   - `POST /v1/use-cases/register`
2) Header:
   - `Authorization: Bearer <token>`
3) Body example:
   - `submission_payload`:
     - `data_classification: "PCI"`
     - `deployment_target: "CLOUD"`
     - `model_provider: "EXTERNAL"`
4) Response:
   - `{ "use_case_id": "...", "run_id": "..." }`

**What happens**

- API: `src/uca_orchestrator/api/routers/use_cases.py` (`register_use_case`)
- DB write:
  - `UseCaseRepo.create()` → `use_cases` row
  - `OrchestrationService.start()` → `runs` row with initial state + `RUN_CREATED` audit
  - `USE_CASE_REGISTERED` audit event written

#### Step C — Start orchestration

1) Call:
   - `POST /v1/use-cases/{use_case_id}/orchestrate`
2) Header:
   - `Authorization: Bearer <token>`
3) Response:
   - Either:
     - `{ "status": "APPROVAL_READY", ... }`
   - Or:
     - `{ "status": "INTERRUPTED", "reason": "Human approval required", ... }`

**What happens in between (the important part)**

1) **API layer** calls service:
   - Router: `src/uca_orchestrator/api/routers/use_cases.py` (`orchestrate_use_case`)
   - It creates an in-process HTTP client:
     - `httpx.ASGITransport(app=request.app)`
     - This allows “tool calls” to hit internal endpoints without real network.

2) **Service layer** executes the run:
   - `OrchestrationService.execute(...)` in `src/uca_orchestrator/services/orchestration_service.py`

3) **LangGraph is built**:
   - `build_graph(...)` in `src/uca_orchestrator/orchestrator/graph.py`

4) **Graph execution begins with checkpoint streaming**:
   - `_execute_with_checkpoints(...)` iterates:
     - `graph.astream(state, stream_mode="updates")`
   - After each node update, it:
     - persists `runs.state` (checkpoint)
     - persists newly appended `audit_log` entries into `audit_events`
     - commits the DB transaction

5) **Nodes run (typical order)**:

- `ENTRY` (`entry_node`)
  - validates/initializes state
- `CLASSIFY` (`classify_node`)
  - computes risk level (PCI/EXTERNAL → HIGH)
- `FETCH_*` (parallel fan-out stage)
  - parallel tool calls via `InternalApiClient` (fan-out/fan-in modeled in the graph):
    - `fetch_registration_node`
    - `fetch_policy_node`
    - `fetch_approvals_node`
    - `fetch_eval_status_node`
    - `fetch_artifacts_status_node`
  - Each tool call is a **JWT-authenticated request** to `/internal/v1/*`
  - Reducers merge partial updates safely at fan-in (especially `audit_log`)
- `GAP_ANALYSIS` (`gap_analysis_node`)
  - compares policy required artifacts vs artifact types present
- if missing → `ARTIFACT_GENERATION` (`artifact_generation_node`)
  - generates artifacts into state (`generated_artifacts`)
- `EVAL_CHECK` (`eval_check_node`)
  - triggers missing evaluations via internal eval tool
  - checks metrics (example: toxicity threshold)
- `APPROVAL_CHECK` (`approval_check_node`)
  - reads approvals snapshot and determines rejected/pending/ok
- if rejected or eval failed → `REMEDIATION` → `ESCALATION` → loop or interrupt

6) **Possible outcomes**

- **Approval-ready path**
  - service persists:
    - `UseCaseStatus=APPROVAL_READY`
    - artifacts into `artifacts` table
    - full audit log into `audit_events`
  - API returns: `{"status":"APPROVAL_READY", ...}`

- **HITL interrupt path**
  - `escalation_node` raises `HumanInterrupt`
  - service catches it, stores:
    - `runs.status=INTERRUPTED`
    - `runs.interrupted_reason/payload`
    - `UseCaseStatus=INTERRUPTED`
  - API returns: `{"status":"INTERRUPTED", "reason":"Human approval required", ...}`

#### Step D — Governance reviewer resumes

1) Governance reviewer gets a token with role `governance_reviewer`.
2) Calls:
   - `POST /v1/runs/{run_id}/resume`
3) Body example:
   - `decision`: `{ "approve_exception": true, "notes": "Approved PCI exception" }`

**What happens**

- API: `src/uca_orchestrator/api/routers/runs.py`
- Service: `OrchestrationService.resume(...)`
  - merges decision into state under `state["hitl"]["decision"]`
  - sets run running and re-executes

---

### 16) Notes / known enterprise follow-ups (not yet implemented)

These are explicitly called out in your design doc but not implemented yet:

- **Encryption at rest** for run state and artifacts (envelope encryption / KMS integration)
- **Immutable approval metadata** / ledger semantics (WORM storage or append-only snapshots)
- **Retry policies** and tool failure strategy (timeouts, backoff, circuit-breaking)
- **Metrics/KPIs export** (node counts, loop depth, time-to-approval, etc.)
- **FastAPI lifespan migration** (replace deprecated `@app.on_event`)

If you want, I can extend the codebase to include these production-grade controls while keeping the same architecture boundaries.

