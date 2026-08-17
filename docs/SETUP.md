# SetuHaul Setup & Operational Guide

This document provides step-by-step instructions for running, testing, building, and deploying the **SetuHaul** platform locally and on AWS.

---

## 1. Prerequisites

Ensure you have the following installed on your machine:

* **Python 3.12+** (with `venv` and `pip`)
* **Node.js 18+** (with `npm`)
* **Docker & Docker Compose** (for containerized local run and AWS image packaging)
* **AWS CLI v2** (optional, required only for AWS cloud deployment)
* **SQLite 3** (bundled with Python)

---

## 2. One-Click Local Quickstart

The fastest way to launch the full stack (FastAPI backend + Vite React frontend + SQLite database) is using the automated startup script:

```bash
# 1. Clone or navigate to the repository
cd /path/to/project2

# 2. Start the application
./scripts/start.sh
```

### What `start.sh` does automatically:
1. Copies `.env.example` to `.env` (if not already present).
2. Creates the Python virtual environment under `backend/.venv` and installs all dependencies.
3. Installs frontend npm packages under `frontend/node_modules`.
4. Runs database schema creation, seed expansion, and migrations.
5. Kills any stale processes on ports `8000` (API) and `5173` (UI).
6. Starts the FastAPI server on `http://127.0.0.1:8000` with hot-reloading.
7. Starts the Vite React UI on `http://127.0.0.1:5173`.

---

## 3. Demo User Accounts

The system seeds default test accounts for all standard logistics roles:

| Role | Username | Purpose & Capabilities |
|---|---|---|
| 👑 **Admin** | **`admin`** | Full access: Evaluation Measures & Reasoning, Master Tables, Baseline configuration, User Management |
| 🧑‍💼 **Operations** | **`ops`** | Exception Queue, Priority Dock Scheduler, Penalties & Policies |
| 🏭 **Warehouse** | **`warehouse.jai`** / `warehouse.ggn` | Review Soft-Holds, Approve / Reject Appointments, Inbound Dock Status |
| 🚛 **Driver** | **`driver.ravi`** / `driver.amit` | Exception Reporting, Verified Slot Booking, Live GPS Dual ETA |
| 🏢 **Carrier** | **`carrier.bluedart`** / `carrier.vtrans` | Inbound Shipments, Carrier Analytics, Operational Messaging |

---

## 4. Environment Variables (`.env`)

Configure optional integrations in `.env`:

```ini
# Application Configuration
APP_NAME=SetuHaul
HOST=127.0.0.1
PORT=8000
CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173,http://localhost:8000

# Classroom Clock (Simulated Time for Deterministic Testing)
CLASSROOM_NOW=2026-08-04T09:40:00+05:30

# Database Storage Path
DATABASE_PATH=data/setuhaul_freight_operations.db

# Seed Expansion: full (spec volume ~20 loads), crunch (10-driver evening crunch), or off
EXPAND_SEED=full

# Optional: OpenRouter API Key for Natural Language Agent Polish
OPENROUTER_API_KEY=

# Optional: Geoapify API Key for Real-Time Route ETA Calculations
GEOAPIFY_API_KEY=

# Optional: LangSmith Tracing
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=setuhaul-dev
LANGCHAIN_TRACING_V2=false

# Optional: AWS Region for CloudWatch / Deployment
AWS_REGION=us-east-1
```

---

## 5. Automation & Testing Scripts

SetuHaul provides a comprehensive suite of shell and Python scripts under `scripts/`:

```
scripts/
├── start.sh                 # Launches local FastAPI + Vite React UI
├── stop.sh                  # Gracefully terminates all background services on 8000 & 5173
├── reset_db.sh              # Rebuilds SQLite database from schema, seed, and migrations
├── build.sh                 # Installs dependencies & compiles production frontend into frontend/dist
├── package.sh               # Packages deployable tarball bundle under dist/
├── deploy_aws.sh            # 1-click AWS EC2 + ECR + CloudWatch deployment script
├── run_scenarios.sh         # Executes end-to-end automated scenario verification suite
├── run_scenarios.py         # Python scenario runner for 6 golden paths
├── concurrency_demo.sh      # Dual-driver same-slot race condition check
├── concurrency_demo.py      # Concurrency demonstration test script
├── evening_crunch.py        # Simulates 10 delayed drivers competing for 4 evening slots
└── push_cloudwatch_metrics.py # Scrapes & pushes KPIs to AWS CloudWatch
```

### Running Backend Tests:
```bash
# Run full pytest suite (38 passing unit & integration tests)
make test
# OR directly:
PYTHONPATH=backend backend/.venv/bin/pytest
```

### Running Automated Scenario Verifications:
```bash
# Executes 6 challenge scenarios: standard delay, early arrival, no-slot overflow, dual-ETA, race condition
./scripts/run_scenarios.sh
```

### Running Concurrency & Race Condition Verification:
```bash
# Proves that when two drivers request the same dock slot, one gets the soft-hold and the other is safely rejected
./scripts/concurrency_demo.sh
```

### Running Evening Crunch Capacity Stress Test:
```bash
# Simulates 10 delayed drivers arriving simultaneously against 4 evening slots at FAC-JAI-01
PYTHONPATH=backend backend/.venv/bin/python scripts/evening_crunch.py
```

---

## 6. Local Docker Deployment

To run the complete production container locally:

```bash
# Build and run the single containerized stack
docker compose up --build

# Open the app in your browser:
# http://127.0.0.1:8000
```

---

## 7. AWS Cloud Deployment (Free Tier)

SetuHaul includes an automated, production-ready AWS CloudFormation stack ([`deploy/aws-ec2-stack.yaml`](file:///Users/sameer_j/Documents/coding/fde/project2/deploy/aws-ec2-stack.yaml)):

### Prerequisites for AWS:
1. Authenticate with your AWS account:
   ```bash
   aws login
   # OR:
   aws configure
   ```
2. Run the deployment script:
   ```bash
   ./scripts/deploy_aws.sh
   ```

### What the AWS Deployment Creates:
* **AWS ECR Repository**: `setuhaul-app` storing the multi-arch Linux/amd64 production container.
* **AWS EC2 Free Tier Instance**: `t2.micro` running Amazon Linux 2023 with Docker.
* **Persistent Storage**: 20GB GP3 EBS volume mounted directly to `/app/data` for native SQLite ACID durability.
* **Security Group & VPC**: Ingress on HTTP Ports `80` & `8000`, egress to internet.
* **IAM Role & Instance Profile**: ECR Pull + CloudWatch `PutMetricData` + SSM Management permissions.
* **AWS CloudWatch Dashboard**: `SetuHaul-Operations` with real-time graphs for all 6 evaluation measures.

---

## 8. Stopping the Services

To cleanly terminate all running local servers:

```bash
./scripts/stop.sh
```
