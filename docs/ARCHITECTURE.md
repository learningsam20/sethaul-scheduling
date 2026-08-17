# SetuHaul Architecture & Technical Design

## 1. Executive Summary

**SetuHaul** is an enterprise-grade freight dock-scheduling and driver-exception resolution system. It automates delay reporting, dock re-allocation, appointment confirmations, and operational visibility across manufacturing and logistics hubs.

The system combines **FastAPI**, **React + TypeScript**, a **deterministic constraint-based scheduling engine**, a **LangGraph-powered conversational agent** with strict tool-calling guardrails, and a **SQLite (WAL) transactional database** with dual-layer observability (**In-App Analytics** and **AWS CloudWatch**).

---

## 2. High-Level System Architecture

```mermaid
flowchart TD
    subgraph ClientLayer ["Client Layer (Role-Based Web UI)"]
        UI_Driver["🚛 Driver Portal<br/>(Delay Reporting & Slot Booking)"]
        UI_Ops["🧑‍💼 Operations Queue<br/>(Exceptions & Priority Scheduler)"]
        UI_WH["🏭 Warehouse Manager<br/>(Dock Approvals & Soft-Holds)"]
        UI_Admin["👑 Admin Center<br/>(Measures, Master Data & Baselines)"]
    end

    subgraph APILayer ["API Gateway & Backend BFF (FastAPI)"]
        Auth["JWT & Role Authorization"]
        Router_Chat["Chat Router"]
        Router_Ops["Ops & Scheduler Router"]
        Router_Loc["Dual-ETA Location Router"]
        Router_Analytics["Analytics & Metrics Router"]
    end

    subgraph IntelligenceLayer ["Agent & Scheduling Engine"]
        Agent["LangGraph Exception Agent<br/>(Turn Output & Tool Routing)"]
        InsightsAgent["LangGraph Insights Agent<br/>(Anomaly & Trend Analyzer)"]
        Tools["Deterministic Tool Registry<br/>(Feasibility, Checkins, Rules)"]
        Scheduler["Greedy Dock Interval Scheduler<br/>(Priority Weights & Buffer Optimization)"]
    end

    subgraph DataLayer ["Transactional & Persistence Layer"]
        DB[(SQLite WAL Database<br/>`setuhaul_freight_operations.db`)]
        EBS[(AWS GP3 Persistent Volume)]
    end

    subgraph ObservabilityLayer ["Observability & Cloud Services"]
        CW["AWS CloudWatch<br/>(Live Dashboards & PutMetricData)"]
        LS["LangSmith<br/>(LLM Run Traces & Tool Evals)"]
        Geo["Geoapify Routing API<br/>(Live GPS Route ETA)"]
    end

    UI_Driver -->|REST + JWT| Router_Chat
    UI_Ops -->|REST + JWT| Router_Ops
    UI_WH -->|REST + JWT| Router_Ops
    UI_Admin -->|REST + JWT| Router_Analytics

    Router_Chat --> Agent
    Router_Ops --> Scheduler
    Router_Loc --> Geo
    Router_Analytics --> Router_Analytics

    Agent --> Tools
    Tools --> Scheduler
    Scheduler --> DB
    InsightsAgent --> DB

    DB --> EBS
    Router_Analytics --> CW
    Agent -.-> LS
```

---

## 3. Core Subsystems & Component Interaction

### 3.1 Backend Service (`backend/app/`)
* **FastAPI Application Framework**: Exposes REST endpoints grouped by business role (`/api/auth`, `/api/chat`, `/api/ops`, `/api/admin`, `/api/analytics`, `/api/location`, `/api/penalty`, `/api/messages`).
* **JWT Authentication & RBAC**: Enforces strict role-based access control for `DRIVER`, `OPERATIONS`, `WAREHOUSE`, `ADMIN`, `CARRIER`, and `CUSTOMER`.
* **Database Management (`app/db.py`)**: Manages SQLite connections with Write-Ahead Logging (`WAL`), automated schema creation, seed expansion, and atomic transaction locks.

### 3.2 LangGraph Exception Agent (`app/agent/`)
* **Deterministic Tool Grounding**: The LLM acts strictly as a communication and reasoning coordinator; all slot discoveries, soft-holds, driver verifications, and rule lookups are executed through deterministic Python tools in `app/agent/tools.py`.
* **Zero Hallucination Guarantee**: Every slot returned to the driver must have a verified `slot_id` issued by `find_matching_slots`. Hard gate evaluators reject any turn attempting to offer ungrounded timestamps.
* **Structured Output (`AgentTurnOutput`)**: Ensures predictable, schema-validated JSON turns containing message text, options list, actions required (e.g. `REQUEST_BROWSER_LOCATION`), and state flags.

---

## 4. Slot State Machine & Concurrency Control

```mermaid
stateDiagram-v2
    [*] --> SHOWN: Driver Reports Delay
    SHOWN --> SOFT_HOLD: Driver Selects Slot Option (5-min TTL)
    SOFT_HOLD --> PENDING_CONFIRMATION: Soft-Hold Placed
    PENDING_CONFIRMATION --> CONFIRMED: Warehouse Approves Appointment
    PENDING_CONFIRMATION --> REJECTED: Warehouse Rejects / Conflict
    SOFT_HOLD --> EXPIRED: TTL Expires (5 mins) without Action
    EXPIRED --> SHOWN: Regenerate Available Slots
    CONFIRMED --> IN_PROGRESS: Truck Checked-In at Gate
    IN_PROGRESS --> COMPLETED: Dock Unloading Complete
```

### Concurrency & Double-Booking Protection:
* When multiple drivers request overlapping slots simultaneously, SQLite atomic transactions place a **soft-hold with a 5-minute TTL** on the first committed write.
* Competing drivers attempting to select the same slot are immediately notified of the conflict and provided with the next best available time window.

---

## 5. Greedy Dock Interval Scheduler

The scheduling engine (`backend/app/services/booking.py`) provides automated time-interval sequencing across all active dock doors in a facility:

### Objective Function:
$$\text{Score} = \text{Priority Weight} + \text{On-Site Bonus} - (\text{Lateness Penalty} \times \Delta t_{\text{delay}}) - (\text{Idle Gap Penalty} \times \Delta t_{\text{idle}})$$

### Core Scheduling Policies:
1. **Facility Scoping**: Schedules are strictly isolated per facility (`FAC-JAI-01`, `FAC-GGN-01`). Cross-facility appointments are rejected by design.
2. **In-Progress Protection**: Trucks currently docked or unloading cannot be bumped or preempted.
3. **Carrier Priority Tiering**: Critical/perishable shipments receive highest dock priority; normal freight fills remaining optimal intervals.
4. **Driver Duty Limits**: Hard-gate validation ensures no driver is scheduled past their mandatory maximum on-duty shift hours.

---

## 6. Dual ETA Architecture (Location Add-On)

To eliminate the discrepancy between subjective driver optimism and real-world traffic delays, SetuHaul maintains a **Dual ETA model**:

```mermaid
sequenceDiagram
    autonumber
    actor Driver
    participant App as React UI
    participant API as FastAPI BFF
    participant Agent as LangGraph Agent
    participant Geo as Geoapify API
    participant DB as SQLite DB

    Driver->>App: "Delayed by 2 hours, new ETA 14:00"
    App->>API: POST /api/chat/turn (Declared ETA: 14:00)
    API->>Agent: Parse exception & declared ETA
    Agent-->>App: Action: REQUEST_BROWSER_LOCATION
    App->>Driver: Request GPS Geolocation
    Driver->>App: Share GPS Coordinates (26.91, 75.78)
    App->>API: POST /api/location/resume (lat, lng)
    API->>Geo: Calculate Route Distance & Duration
    Geo-->>API: Route Duration = 145 min (Route ETA: 14:25)
    API->>DB: Record Declared ETA (14:00) & Route ETA (14:25)
    API->>Agent: Rank Slots with Dual Buffer
    Agent-->>App: Present Slot Options (14:30, 15:00) with GPS validation note
```

---

## 7. Observability & 6 Core Challenge Measures

SetuHaul instruments all operational events into the `case_metrics` table:

```mermaid
flowchart LR
    Event[Driver Thread / Checkin / Booking Event] --> Service[metrics.py]
    Service --> CM[(case_metrics table)]
    CM --> UI[In-App Analytics & Insights Dashboard]
    CM --> Push[push_cloudwatch_metrics.py]
    Push --> AWS_CW[AWS CloudWatch Metrics & Dashboard]
```

### The 6 Evaluation Measures:
1. **Time to Resolve the Case (`avg_resolve_min`)**: Time from initial delay report to confirmed/usable plan ($< 1.0\text{ min}$ automated vs $45.0\text{ min}$ manual).
2. **Human Help Needed (`human_help_rate`)**: Percentage of cases requiring operations manager takeover ($50.0\%$ vs $100.0\%$).
3. **Self-Service Rescheduling (`self_service_rate`)**: Share of driver requests completed end-to-end autonomously ($50.0\%$ vs $0.0\%$).
4. **ETA Error (`avg_eta_error_min`)**: Difference between predicted ETA and actual gate-in check-in timestamp.
5. **First Option Accepted (`fit`)**: Frequency with which drivers select Option #1 ($100.0\%$ vs $35.0\%$).
6. **Estimated Waiting Reduced (`avg_wait_reduced_min`)**: Yard dwell time saved by pre-allocating open dock windows.

---

## 8. AWS Cloud Deployment Architecture

The production environment is hosted on AWS using a CloudFormation template ([`deploy/aws-ec2-stack.yaml`](../deploy/aws-ec2-stack.yaml)):

```mermaid
flowchart TD
    subgraph VPC ["AWS VPC (10.0.0.0/16) - us-east-1"]
        IGW[Internet Gateway]
        PublicSubnet["Public Subnet (10.0.1.0/24)"]
        
        subgraph EC2Host ["EC2 Free Tier Instance (t2.micro)"]
            Docker[Docker Engine]
            Container["SetuHaul Production Container<br/>(FastAPI + Vite React SPA)"]
            Volume["EBS GP3 Persistent Volume<br/>(`/app/data/setuhaul_freight_operations.db`)"]
            
            Docker --> Container
            Container <--> Volume
        end
        
        PublicSubnet --> EC2Host
        IGW <--> PublicSubnet
    end

    subgraph AWS_Services ["Managed AWS Services"]
        ECR["AWS ECR (setuhaul-app:latest)"]
        CW_Dash["AWS CloudWatch Dashboard (SetuHaul-Operations)"]
        IAM["IAM Instance Role (ECR Pull + PutMetricData)"]
    end

    ECR -->|Pull Image| Docker
    Container -->|PutMetricData| CW_Dash
    IAM --> EC2Host
    User([User / Browser]) -->|HTTP Port 80| Container
```
