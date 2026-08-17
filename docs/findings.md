# SetuHaul FDE — Findings (Requirements Gap Review)

**Scope:** `backend/` (agent, services, routers, db), `frontend/src/App.tsx`, `database/` (schema + seed), `specs.md` (derived from `SetuHaul_FDE_Challenge.md`), `findings.md` (prior review).
**Method:** Cross-referenced `SetuHaul_FDE_Challenge.md` requirements against existing implementation. Every claim references relevant markdown sections and code paths.

---

## 0. Verified Requirements Already Met

| Requirement | Evidence |
|-------------|----------|
| **Conversational exception intake** — free-text understanding, multi-turn context, clarification questions | `backend/app/agent/graph.py`, `backend/app/agent/lc_tools.py`, `backend/app/agent/prompts.py` |
| **Shipment disambiguation** — driver with >1 active shipment | Agent resolves via `resolve_driver_context` tool; thread tied to `shipment_id` |
| **Duplicate message detection** — weak connectivity retries | `backend/app/services/chat.py:148-164`; tested in `test_chat.py:4-8` |
| **Soft-hold with TTL** — atomic claim, exclusive per slot | `backend/app/services/booking.py:306-323`; unique index `ux_active_slot_hold` |
| **Warehouse confirmation flow** — `PENDING_CONFIRMATION` → `CONFIRMED`/`REJECTED` | `backend/app/services/booking.py`, `/ops/pending/{id}/decide` router |
| **Slot feasibility** — operating hours, dock compatibility, unloading duration, facility rules | `backend/app/services/booking.py:135-144,193-202,260-265` |
| **Concurrent request safety** — stale options, capacity reduction, cancellation race | `backend/app/services/booking.py:545-599`; stale-option warning in `graph.py` |
| **Facility scheduling engine** — concrete dock intervals, fixed-work set, rolling replan, utilisation + priority KPIs | `backend/app/services/scheduling.py:104-304` |
| **ETA management** — driver-declared, route-based, gate-in actual, drift detection, stale rejection, at-gate | `backend/app/services/eta.py`, `location_router.py` |
| **Location add-on** — one-time snapshot, Geoapify routing, dual ETA ranking, fallback on failure | `backend/app/services/eta.py`, `location_router.py`, frontend `App.tsx:830-831` |
| **Escalation paths** — no-feasible-slot, reefer gap, contradictory info | `backend/app/agent/lc_tools.py`, `backend/app/services/chat.py` |
| **Volume targets & stress scenarios** — 100 drivers, 720 shipments, 6 facilities, evening crunch | `backend/app/seed_expand.py`, `scripts/evening_crunch.py`, `test_evening_crunch.py` |
| **Metrics & analytics** — Trust/Autonomy/Fit, ETA error, wait reduced, WoW, vs-manual baseline | `backend/app/services/metrics.py`, `/api/analytics/*` routers |
| **LangSmith & CloudWatch** — traces, latency, scheduling duration, case outcomes | `backend/app/tracing.py`, `backend/app/services/metrics.py` |
| **Role-based UI** — driver, ops, warehouse, admin, carrier, customer | `frontend/src/App.tsx` role-tab mapping |
| **Operational messages** — warehouse/customer replies outside driver chat | `database/instructions/setuhaul_schema_and_seed.sql` has `operational_messages` table; not yet surfaced in UI |
| **Before/after comparison** — controlled test set with documented manual baseline | `backend/app/services/metrics.py:MANUAL_BASELINE` (hardcoded example values as per §2.3) |
| **Temperature control** — reefer compatibility checked | `backend/app/services/booking.py:reefer = shipment["temperature_control_required"]` |
| **Cancelled appointments visible in history** — §11.3 | `appointments` table stores `CANCELLED` with timestamp; views include them |
| **Showing ≠ reserving ≠ confirming** — three distinct states | Soft-hold (`PENDING_CONFIRMATION`) → warehouse decide → `CONFIRMED`/`REJECTED` |

---

## 1. Remaining Gaps (Priority Order)

### A. Carrier / Customer Exception Visibility & Messaging — **HIGH**
**Markdown ref:** §5.1 (Parties involved — dispatcher/carrier needs "revised plan and escalation status", consignee/customer needs "reliable revised arrival information"), §10.3 (`contacts` and `operational_messages` tables)
**Current state:** `CARRIER` and `CUSTOMER` roles exist with `inbound` + `analytics`/`dashboard` tabs only. `operational_messages` table exists in seed but is not used in any service or router. No carrier/customer notification flow for revised arrivals or exception updates.
**Gap:** Carriers cannot see their drivers' exceptions or receive escalation status. Customers cannot receive revised arrival estimates through the system.
**Impact:** High — §5.1 explicitly calls out these parties and their needs during exceptions. The communication loop is incomplete.

### B. Driver Duty Time & Next Assignment Constraints — **MEDIUM**
**Markdown ref:** §9.2 (Allocation policy — "Driver duty time and next assignment"), §10.1 (`drivers` table)
**Current state:** No tracking of driver hours-of-service, remaining duty time, or next pickup commitment. Scheduler ranks by priority, at-facility status, and ETA only.
**Gap:** The scheduler does not consider whether the driver has enough remaining legal operating time to complete the unload + reach the next assignment.
**Impact:** Medium — §9.2 explicitly lists this as a possible consideration for allocation policy.

### C. Commercial Penalty / Compensation Approval Workflow — **MEDIUM**
**Markdown ref:** §9.3 (Human control — "Commercial penalties, compensation and customer commitments require authorised approval"), §12.3 (Out of scope — "Commercial penalty approval")
**Current state:** No workflow for penalty approval, compensation offers, or customer commitment breaches.
**Gap:** When a delay causes a customer commitment breach, there is no structured path to request authorised approval for penalties or compensation.
**Impact:** Medium — explicitly required by §9.3, though the final output is deferred to human approval.

### D. Explicit Allocation Policy Exposure in UI — **MEDIUM**
**Markdown ref:** §9.2 ("Students must expose the trade-offs and propose a defensible policy rather than hiding the decision inside a prompt")
**Current state:** Scheduler has explicit scoring (`priority + at_facility + in_progress - unload`) and reports `priority_violations`, but the ops UI does not surface the policy rationale or trade-offs.
**Gap:** The allocation policy exists in code but is not clearly visible to operations coordinators during decision-making.
**Impact:** Medium — the system is auditable in logs but not transparent in the workflow as required.

### E. Partial-Day Facility Rules Enforcement — **LOW**
**Markdown ref:** §11.3 ("Facility rules effective only during part of the day"), §10.2 (`facility_rules` with `effective_from`, `effective_to`)
**Current state:** `facility_rules` table has `effective_from` / `effective_to` columns. The `_facility_rules` function in `booking.py` filters by date (`effective_to >= date(?)`) but **does not filter by time-of-day**.
**Gap:** A rule active only 14:00–18:00 would be applied at 10:00 AM if it hasn't expired by date.
**Impact:** Low — existing tests pass because seed rules are `effective_from='2026-01-01'` with no `effective_to`.

### F. Optional Enrichment Tables Missing — **LOW**
**Markdown ref:** §10.4 (Optional enrichment data)
**Current state:** `customer_commitments`, `appointment_history`, and `facility_capacity_changes` tables are not created in any migration. `scheduling_runs` exists in migration 001. `operational_messages` exists in seed but is unused.
**Gap:** Three of the five optional enrichment tables are missing.
**Impact:** Low — explicitly optional in §10.4.

### G. Wait Projection Display in Chat UI — **LOW**
**Markdown ref:** §12.2 ("The driver is shown what happens when an option changes or disappears"), §2.3 (What to measure — "Old and new projected waiting time")
**Current state:** Backend computes old and new projected waiting (`record_wait_projection`), but the frontend chat does not clearly display the wait delta when options become stale.
**Gap:** The metric is recorded but not surfaced in the driver-facing conversation.
**Impact:** Low — data is collected, but the demo value is reduced.

### H. Stale-Option Explanation Not Fully Documented — **LOW**
**Markdown ref:** §12.2 ("The driver is shown what happens when an option changes or disappears"), §11.2 ("A shown slot disappears before confirmation")
**Current state:** The system warns about stale options and drops invalid ones, but the chat UI only shows a generic flash banner. The specific slot that disappeared and why is not clearly explained.
**Gap:** The driver sees "options changed" but not "SLOT-1938 is no longer available because DOCK-04 was blocked for maintenance."
**Impact:** Low — the mechanism works, but the transparency could be stronger.

---

## 2. Partial Implementations

### 2.1 Allocation Policy (Implemented but Not Exposed)
- **What works:** Scheduler uses explicit priority weights (`CRITICAL=20`, `HIGH=15`, `NORMAL=10`), protects in-progress work (+1000 score boost), penalises long unloads, and reports `priority_violations` + `slot_utilisation_pct`.
- **What's missing:** Ops cannot see or tune the policy during a scheduling run. The rationale ("priority then at-facility then ETA") is a comment, not a UI feature. This violates §9.2's requirement to "expose the trade-offs."

### 2.2 Location Add-On (Implemented but Demo Scripts Not Explicit)
- **What works:** One-time location, Geoapify routing, dual ETA ranking, stale/at-gate/hard-outage handling, frontend `REQUEST_BROWSER_LOCATION` action.
- **What's missing:** Scenario scripts (`run_scenarios.sh`, `evening_crunch.py`) do not explicitly demonstrate the advanced add-on cases (location improves ETA, location fails with fallback, original vs driver vs route vs gate-in ETAs).

### 2.3 Before/After Baseline (Implemented as Hardcoded Example)
- **What works:** `vs_manual` function exists and is surfaced in weekly reports.
- **What's missing:** The `MANUAL_BASELINE` values are hardcoded constants rather than configurable per-facility or per-scenario. The markdown says "Students can use historical data or a controlled test set" (§2.3), implying the baseline should be adjustable.

---

## 3. Non-Gaps (Previously Questioned, Now Verified)

| Prior Concern | Resolution |
|---------------|------------|
| No `options_generated_at` | Migrations add `options_generated_at` / `displayed_options_json` / `options_stale`; `record_options_generated` called in agent and location flow |
| Location ETA source not recorded | `record_predicted_eta` for ROUTE/GATE_IN called from `location_router.py:101,112-116` |
| Soft-hold race | Atomic `INSERT … WHERE NOT EXISTS` + partial unique index |
| 10-driver evening crunch | Seeded `SHP1101–SHP1110` vs 4 free 19:00 standard slots |
| Capacity cut after options shown | `record_dock_event` releases holds + stales options + replans |
| Runtime cancellation frees slot | `cancel_appointment` wired via `/ops/appointments/{id}/cancel` |
| Duplicate-message runtime handling | `is_duplicate` detection in `chat.py` |
| 90-min delay ≠ ETA shift | `record_driver_eta` computes implied ETA and flags mismatch |
| Operating hours not enforced | `find_feasible_slots` filters on `open_time/close_time` |
| Product/carrier restrictions unused | `_facility_rules` + blocked product/carrier checks |
| Runtime constraints not persisted | `persist_exception_constraints` wired via `eta.py` |
| Scheduler was score-and-sort | Concrete dock-interval assignment with gap-walking, fixed-work set, cost objective |
| Location capture time missing | Frontend sends `captured_at` + `client_now`; router stores it |
| Stale / hard-outage / at-gate cases | `eta.py` handles all three; tests cover them |
| `operational_messages` missing | Table exists in seed schema (`database/instructions/setuhaul_schema_and_seed.sql`); not yet wired to services |

---

## 4. Recommendations

1. **Build carrier/customer notification flow** — add endpoints and UI for carriers to view driver exceptions and for customers to receive revised arrival estimates; wire `operational_messages` to the messaging system.
2. **Implement driver duty-time tracking** — add `duty_start_ts`, `max_daily_hours`, and `remaining_duty_minutes` to `drivers` or a new table; gate slot feasibility on remaining duty.
3. **Add carrier fairness metric** — track per-carrier slot consumption rate; flag when one carrier dominates scarce capacity (§9.2).
4. **Build penalty approval workflow** — add `penalty_requests` table with `status` (`PENDING`, `APPROVED`, `REJECTED`), link to `customer_commitments`, route approvals to ops/admin (§9.3).
5. **Expose allocation policy in ops UI** — add a "Scheduler Policy" panel showing priority weights, in-progress protection, and objective function (§9.2).
6. **Fix partial-day rule filtering** — update `_facility_rules` to filter by time-of-day: `effective_from <= :now AND (effective_to IS NULL OR effective_to >= :now)` (§11.3).
7. **Add optional enrichment tables** — `customer_commitments`, `appointment_history`, `facility_capacity_changes` via a new migration (§10.4).
8. **Enhance stale-option UI** — when options are invalidated, show which slot disappeared, why, and the new projected wait vs old projected wait in the chat bubble (§12.2).
9. **Add advanced demo scripts** — extend `run_scenarios.sh` with location-improvement, location-fallback, and before/after comparison demos.
10. **Make baseline configurable** — allow ops/admin to update `MANUAL_BASELINE` values via settings rather than hardcoded constants (§2.3).
