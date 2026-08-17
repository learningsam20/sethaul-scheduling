# SetuHaul Development & Scaling Roadmap

This document outlines the shipped capabilities, immediate enhancements, and long-term enterprise scalability milestones for the **SetuHaul** platform.

---

## 🗺️ Milestone Matrix

```mermaid
gantt
    title SetuHaul Development Phases
    dateFormat  YYYY-MM-DD
    section Phase 1 (Shipped)
    Core Agent & Deterministic Tools     :done, p1_1, 2026-07-01, 2026-08-05
    Slot State Machine & Concurrency     :done, p1_2, 2026-08-01, 2026-08-10
    Multi-Role Portals & 6 Measures UI  :done, p1_3, 2026-08-08, 2026-08-15
    AWS EC2 & CloudWatch Live Deploy    :done, p1_4, 2026-08-15, 2026-08-17
    section Phase 2 (Near-Term)
    Telematics / ELD Live Webhooks       :active, p2_1, 2026-08-20, 2026-09-10
    Automated Carrier Penalty Contracts :p2_2, 2026-09-01, 2026-09-25
    SMS / WhatsApp Driver Chatbot Channel:p2_3, 2026-09-15, 2026-10-10
    section Phase 3 (Enterprise Scale)
    PostgreSQL / Aurora Migration        :p3_1, 2026-10-01, 2026-11-01
    Distributed Redis Soft-Hold Locks   :p3_2, 2026-10-15, 2026-11-15
    Multi-Region EKS / ECS Cluster       :p3_3, 2026-11-01, 2026-12-15
```

---

## 1. Phase 1: Core System & Classroom Challenge (Shipped ✅)

- [x] **FastAPI BFF + React SPA**: High-performance backend paired with dark/light themed, responsive role-based frontend.
- [x] **Deterministic Dock Scheduling Engine**: Greedy time-interval allocation respecting priority tiers, shift limits, and facility operating windows.
- [x] **LangGraph Exception Agent**: Natural language delay parsing with strict deterministic tool-calling guardrails (zero ungrounded/hallucinated slots).
- [x] **4-Phase Slot Lifecycle**: `SHOWN` $\rightarrow$ `SOFT_HOLD (5-min TTL)` $\rightarrow$ `PENDING_CONFIRMATION` $\rightarrow$ `CONFIRMED`.
- [x] **Dual ETA Resolution**: Driver-declared arrival times combined with Geoapify GPS routing calculations.
- [x] **Multi-Facility Scoping**: Strict isolation across regional facilities (`FAC-JAI-01`, `FAC-GGN-01`).
- [x] **6 Core Evaluation Measures & Reasoning**: Full mathematical tracking and visual UI cards for Resolution Time, Human Help %, Self-Service %, ETA Error, Fit %, and Wait Time Savings.
- [x] **AWS Cloud Deployment**: Production AWS EC2 Free Tier stack (`t2.micro` + EBS persistent volume) with live CloudWatch dashboard.

---

## 2. Phase 2: Operational Enhancements (Near-Term 🔄)

- [ ] **ELD / Telematics Webhook Ingestion**: Ingest live GPS coordinates and engine diagnostics from Samsara, Geotab, or Trimble devices automatically.
- [ ] **Automated Penalty & SLA Enforcement**: Automated detention fee calculation and dispute resolution workflows for chronic carrier delays.
- [ ] **Omnichannel Driver Interface**: Expand beyond web chat to native **WhatsApp Business API** and two-way SMS interfaces for drivers on the road.
- [ ] **Voice-to-Text Driver Exception Reporting**: Enable hands-free voice notes for drivers reporting highway breakdowns or traffic congestion.

---

## 3. Phase 3: Enterprise Scale & Multi-Region (Future 🚀)

- [ ] **Distributed Database Layer**: Migrate SQLite single-writer to **Amazon Aurora PostgreSQL Serverless v2** for multi-region active-active replication.
- [ ] **Redis Distributed Locking (Redlock)**: Replace in-database soft-holds with high-throughput Redis TTL keys for sub-millisecond slot reservations.
- [ ] **Multi-Facility Cross-Docking**: Intelligent re-routing between nearby facilities when one hub hits 100% capacity during emergency storms or peak seasons.
- [ ] **Machine Learning Dwell-Time Forecasting**: Predictive models to adjust standard dock turnaround times based on cargo SKU weight, carrier historical unloading speed, and weather.
