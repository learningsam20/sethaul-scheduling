# SetuHaul Backend API & Exception Agent ⚙️🤖

> **FastAPI Backend BFF, LangGraph Intelligent Agent, Deterministic Schedulers, and SQLite Engine**

The SetuHaul backend provides high-performance REST APIs, an autonomous conversational agent with hard-gate guardrails, a greedy dock interval scheduler, and real-time observability pipelines.

---

## 🏗️ Backend Directory Structure

```
backend/
├── app/
│   ├── main.py             # FastAPI entrypoint, lifespan startup/seed hooks, static mount
│   ├── auth.py             # JWT token creation, password hashing (bcrypt), CurrentUser dependency
│   ├── config.py           # Pydantic BaseSettings loading from .env
│   ├── db.py               # SQLite connection pool (WAL mode), migrations runner, seed expander
│   ├── tracing.py          # LangSmith tracing & LangChain environment configuration
│   ├── agent/              # LangGraph Conversational Agent Subsystem
│   │   ├── graph.py        # LangGraph state machine & driver message router
│   │   ├── lc_tools.py     # LangChain Tool wrappers & regex entity extractors
│   │   ├── tools.py        # Deterministic Python tool implementations (feasibility, checkins)
│   │   ├── prompts.py      # System prompts & operational instructions
│   │   ├── schemas.py      # Pydantic schemas (AgentTurnOutput, SlotOption)
│   │   └── reply_format.py # Output formatting, tables, and internal leak guards
│   ├── routers/            # Role-Based REST Endpoints
│   │   ├── auth_router.py      # /api/auth (login, me, seed demo users)
│   │   ├── chat_router.py      # /api/chat (driver messaging, ops takeover, resolve)
│   │   ├── ops_router.py       # /api/ops (facilities, inbound, pending, scheduling)
│   │   ├── admin_router.py     # /api/admin (users CRUD, settings, baselines)
│   │   ├── analytics_router.py # /api/analytics (agent health, weekly WoW, CloudWatch)
│   │   ├── location_router.py  # /api/location (GPS coordinates, Geoapify dual ETA)
│   │   ├── penalty_router.py   # /api/penalty (carrier detention rules, disputes)
│   │   └── messages_router.py  # /api/messages (operational email/SMS logs)
│   └── services/           # Core Domain Services
│       ├── booking.py      # Greedy dock scheduler, slot holds, appointment states
│       ├── chat.py         # Thread storage, message persistence, deduplication
│       ├── eta.py          # Geoapify routing client, dual ETA ranking, buffers
│       ├── metrics.py      # case_metrics tracking, 6 challenge measures, CloudWatch payload
│       └── operational_messages.py # Carrier and warehouse operational notifications
├── tests/                  # Pytest Unit & Integration Test Suite (38 tests)
│   ├── test_booking.py
│   ├── test_chat.py
│   ├── test_eta.py
│   ├── test_scheduling.py
│   ├── test_evening_crunch.py
│   ├── test_duty_time_gating.py
│   ├── test_penalty_workflow.py
│   └── test_partial_day_rules.py
└── requirements.txt        # Python package dependencies
```

---

## ⚡ Core Domain Services

### 1. LangGraph Exception Agent (`app/agent/`)
* **Deterministic Tool Grounding**: Uses LangChain tool-calling to execute real operations (`record_exception_and_eta`, `rank_slots_with_eta_buffers`, `soft_hold_slot`, `confirm_driver_choice`).
* **Zero Hallucination Guard**: Offered appointment slots must match a valid `slot_id` produced by the dock engine.

### 2. Greedy Dock Interval Scheduler (`app/services/booking.py`)
* Computes non-overlapping time intervals per dock door in a facility (`FAC-JAI-01`, `FAC-GGN-01`).
* Enforces in-progress unload protection, carrier priority weighting, and driver mandatory rest shift limits.

### 3. Dual-ETA & Geoapify Routing (`app/services/eta.py`)
* Compares driver-declared delay estimates against real-time GPS route calculations.
* Applies separate traffic and facility check-in buffers.

### 4. Metrics & Evaluation Engine (`app/services/metrics.py`)
* Persists thread KPIs into `case_metrics`.
* Computes the **6 Challenge Evaluation Measures** with mathematical formulas and baseline comparisons.
* Exports metric streams for **AWS CloudWatch** (`PutMetricData`).

---

## 🧪 Testing & Execution

```bash
# 1. Activate Python virtual environment
source backend/.venv/bin/activate

# 2. Run all pytest test suites
PYTHONPATH=backend pytest -v

# 3. Start development server directly
PYTHONPATH=backend uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 📚 Cross-References to Documentation

* 🌐 **System Overview & Live Demo**: [`../README.md`](../README.md)
* 🎨 **Frontend Architecture & Portals**: [`../frontend/README.md`](../frontend/README.md)
* 📐 **High-Level Architecture & State Machine**: [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)
* 🛠️ **Full-Stack Setup & Deployment Guide**: [`../docs/SETUP.md`](../docs/SETUP.md)
* 🧪 **Stress Scenarios & Verification**: [`../docs/SCENARIOS.md`](../docs/SCENARIOS.md)
* 🗄️ **Database Schema & SQL Guide**: [`../docs/database_guide.md`](../docs/database_guide.md)
