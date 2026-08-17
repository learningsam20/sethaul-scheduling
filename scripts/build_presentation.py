#!/usr/bin/env python3
"""Build the final presentation HTML with embedded images and render to PDF."""
from __future__ import annotations

import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SS = ASSETS / "screenshots"


def b64(name: str) -> str:
    data = (SS / name).read_bytes()
    return base64.b64encode(data).decode()


def build_html() -> str:
    imgs = {
        "architecture": b64("systemarch.png"),
        "er_diagram": b64("er_diagram.png"),
        "langsmith": b64("langsmith.png"),
        "cloudwatch": b64("cloudwatch.png"),
        "login": b64("01_login.png"),
        "driver_dash": b64("02_driver_dashboard.png"),
        "driver_chat": b64("03_driver_chat.png"),
        "ops_dash": b64("04_ops_dashboard.png"),
        "ops_sched": b64("05_ops_scheduler.png"),
        "warehouse": b64("06_warehouse.png"),
        "admin": b64("07_admin.png"),
        "analytics": b64("08_analytics.png"),
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>SetuHaul — FDE Demo</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg: #0b0e14;
    --surface: #141922;
    --surface2: #1c2333;
    --border: #262d3d;
    --text: #e4e8f1;
    --muted: #8892a4;
    --accent: #3b82f6;
    --accent2: #60a5fa;
    --green: #22c55e;
    --amber: #f59e0b;
    --red: #ef4444;
    --cyan: #06b6d4;
    --purple: #a855f7;
    --slide-w: 1280px;
    --slide-h: 720px;
  }}

  html, body {{ background: #000; font-family: 'Inter', sans-serif; color: var(--text); }}

  .slide {{
    width: var(--slide-w);
    height: var(--slide-h);
    margin: 20px auto;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    position: relative;
    page-break-after: always;
    display: flex;
    flex-direction: column;
  }}

  .slide-body {{ flex: 1; padding: 36px 48px 30px; display: flex; flex-direction: column; }}

  /* Title slide */
  .title-slide {{ justify-content: center; align-items: center; text-align: center; }}
  .title-slide .slide-body {{ justify-content: center; align-items: center; }}
  .title-slide h1 {{ font-size: 60px; font-weight: 900; letter-spacing: -1.5px; margin-bottom: 12px; }}
  .title-slide h1 span {{ color: var(--accent); }}
  .title-slide .tagline {{ font-size: 24px; color: var(--muted); font-weight: 400; margin-bottom: 20px; }}
  .title-slide .meta {{ font-size: 14px; color: var(--muted); letter-spacing: 0.5px; }}

  /* Section headers */
  .section-num {{
    display: inline-block;
    font-size: 11px;
    font-weight: 600;
    color: var(--accent);
    background: rgba(59,130,246,0.12);
    border: 1px solid rgba(59,130,246,0.25);
    border-radius: 4px;
    padding: 2px 8px;
    margin-bottom: 8px;
    letter-spacing: 1px;
    text-transform: uppercase;
  }}
  .slide h2 {{ font-size: 34px; font-weight: 800; margin-bottom: 4px; }}
  .slide h3 {{ font-size: 24px; font-weight: 600; margin-bottom: 4px; }}
  .slide .subtitle {{ font-size: 16px; color: var(--muted); margin-bottom: 20px; }}
  code {{ font-size: 12px; background: var(--surface2); padding: 2px 6px; border-radius: 4px; }}

  /* Grids */
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; flex: 1; }}
  .three-col {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }}
  .four-col {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 14px; }}

  /* Cards */
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px;
  }}
  .card h4 {{ font-size: 16px; font-weight: 700; margin-bottom: 8px; }}
  .card p, .card li {{ font-size: 14px; color: var(--muted); line-height: 1.65; }}
  .card ul {{ list-style: none; }}
  .card ul li::before {{ content: ''; display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--accent); margin-right: 8px; vertical-align: middle; }}
  .card.green-accent {{ border-left: 3px solid var(--green); }}
  .card.blue-accent {{ border-left: 3px solid var(--accent); }}
  .card.amber-accent {{ border-left: 3px solid var(--amber); }}
  .card.red-accent {{ border-left: 3px solid var(--red); }}
  .card.purple-accent {{ border-left: 3px solid var(--purple); }}
  .card.cyan-accent {{ border-left: 3px solid var(--cyan); }}

  /* Metric pill */
  .metric-pill {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
    font-family: 'JetBrains Mono', monospace;
  }}
  .metric-pill .val {{ font-weight: 600; color: var(--green); }}

  /* Screenshot frame */
  .screenshot-frame {{
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    background: #000;
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .screenshot-frame img {{ width: 100%; height: auto; display: block; }}
  .screenshot-label {{ font-size: 11px; color: var(--muted); text-align: center; margin-top: 4px; font-style: italic; }}

  /* Architecture */
  .arch-row {{ display: flex; gap: 12px; align-items: center; justify-content: center; margin: 6px 0; }}
  .arch-box {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 600;
    text-align: center;
    min-width: 120px;
  }}
  .arch-box small {{ font-size: 10px; color: var(--muted); font-weight: 400; }}
  .arch-box.highlight {{ border-color: var(--accent); background: rgba(59,130,246,0.08); }}
  .arch-box.green {{ border-color: var(--green); background: rgba(34,197,94,0.08); }}
  .arch-box.amber {{ border-color: var(--amber); background: rgba(245,158,11,0.08); }}
  .arch-arrow {{ color: var(--muted); font-size: 20px; }}

  /* Flow */
  .flow-step {{
    display: flex; align-items: center; gap: 10px;
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 8px 12px; font-size: 13px; font-weight: 500;
  }}
  .flow-step .step-num {{
    width: 24px; height: 24px; border-radius: 50%;
    background: var(--accent); color: #fff; font-size: 11px; font-weight: 700;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  }}

  /* Ring */
  .ring {{
    width: 80px; height: 80px; border-radius: 50%; position: relative;
    display: flex; align-items: center; justify-content: center;
  }}
  .ring-label {{ font-size: 20px; font-weight: 800; }}

  /* Thank you */
  .thank-slide {{ justify-content: center; align-items: center; text-align: center; }}
  .thank-slide .slide-body {{ justify-content: center; align-items: center; }}
  .thank-slide h1 {{ font-size: 52px; font-weight: 900; margin-bottom: 12px; }}

  @media print {{
    body {{ background: var(--bg); }}
    .slide {{ margin: 0; border: none; border-radius: 0; }}
  }}
</style>
</head>
<body>

<!-- ===== 1. TITLE ===== -->
<div class="slide title-slide">
  <div class="slide-body">
    <div style="font-size:56px;margin-bottom:16px;">&#x1F69B;</div>
    <h1><span>Setu</span>Haul</h1>
    <p class="tagline">AI-Powered Dock Appointment Scheduling for Freight Logistics</p>
    <p class="meta">Full-Stack Demo &bull; LangGraph Agent &bull; CloudWatch Metrics &bull; Real-Time Operations</p>
  </div>
</div>

<!-- ===== 2. PROBLEM ===== -->
<div class="slide">
  <div class="slide-body">
    <span class="section-num">Problem</span>
    <h2>Freight Scheduling is Broken</h2>
    <p class="subtitle">Manual dispatch creates chaos at the dock gate</p>
    <div class="two-col" style="flex:1;">
      <div class="card red-accent">
        <h4>The Pain</h4>
        <ul>
          <li>Drivers arrive unannounced &mdash; gate congestion</li>
          <li>Ops staff manually juggle 40+ loads per shift</li>
          <li>Warehouse gets 5-min warning before a truck rolls in</li>
          <li>No visibility into delays until the phone rings</li>
          <li>Rescheduling means calling 3 parties and hoping</li>
        </ul>
      </div>
      <div class="card green-accent">
        <h4>The Cost</h4>
        <ul>
          <li>2.5 hr average wait per driver at congested docks</li>
          <li>12+ manual calls per reschedule event</li>
          <li>18% of appointments missed or late</li>
          <li>No audit trail &mdash; disputes are he-said-she-said</li>
          <li>Zero telemetry into agent decision quality</li>
        </ul>
      </div>
    </div>
  </div>
</div>

<!-- ===== 3. ARCHITECTURE ===== -->
<div class="slide">
  <div class="slide-body">
    <span class="section-num">Architecture</span>
    <h2>System Architecture</h2>
    <p class="subtitle">Full-stack with LangGraph agent, CloudWatch observability, and LangSmith tracing</p>
    <div style="flex:1;display:flex;align-items:center;justify-content:center;">
      <div class="screenshot-frame" style="max-width:1000px;flex:none;">
        <img src="data:image/png;base64,{imgs['architecture']}" alt="System Architecture" style="max-height:480px;width:auto;" />
      </div>
    </div>
  </div>
</div>

<!-- ===== 4. TECH STACK ===== -->
<div class="slide">
  <div class="slide-body">
    <span class="section-num">Tech Stack</span>
    <h2>Technology Stack</h2>
    <p class="subtitle">Battle-tested open-source stack with free-tier cloud deployment</p>
    <div style="flex:1;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="border-bottom:2px solid var(--border);">
            <th style="text-align:left;padding:10px 14px;color:var(--muted);font-size:12px;letter-spacing:0.5px;">LAYER</th>
            <th style="text-align:left;padding:10px 14px;color:var(--muted);font-size:12px;letter-spacing:0.5px;">TECHNOLOGY</th>
            <th style="text-align:left;padding:10px 14px;color:var(--muted);font-size:12px;letter-spacing:0.5px;">PURPOSE</th>
          </tr>
        </thead>
        <tbody>
          <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:10px 14px;font-weight:700;">Frontend</td>
            <td style="padding:10px 14px;"><code>React + TypeScript + Vite</code></td>
            <td style="padding:10px 14px;color:var(--muted);">Role-based SPA, dark/light theme, responsive KPI dashboards</td>
          </tr>
          <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:10px 14px;font-weight:700;">Backend API</td>
            <td style="padding:10px 14px;"><code>FastAPI (Python 3.12)</code></td>
            <td style="padding:10px 14px;color:var(--muted);">Async REST BFF, Pydantic validation, JWT auth</td>
          </tr>
          <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:10px 14px;font-weight:700;">AI Agent</td>
            <td style="padding:10px 14px;"><code>LangGraph + OpenRouter</code></td>
            <td style="padding:10px 14px;color:var(--muted);">State graph execution, deterministic tool grounding, guardrails</td>
          </tr>
          <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:10px 14px;font-weight:700;">Database</td>
            <td style="padding:10px 14px;"><code>SQLite (WAL Mode)</code></td>
            <td style="padding:10px 14px;color:var(--muted);">ACID transactions, zero external dependencies, durable local volume</td>
          </tr>
          <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:10px 14px;font-weight:700;">GPS Routing</td>
            <td style="padding:10px 14px;"><code>Geoapify API</code></td>
            <td style="padding:10px 14px;color:var(--muted);">Real-time dual-ETA route calculations and traffic buffering</td>
          </tr>
          <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:10px 14px;font-weight:700;">Observability</td>
            <td style="padding:10px 14px;"><code>AWS CloudWatch + LangSmith</code></td>
            <td style="padding:10px 14px;color:var(--muted);">Custom dashboards, metric alarms, LLM call tracing</td>
          </tr>
          <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:10px 14px;font-weight:700;">Cloud Hosting</td>
            <td style="padding:10px 14px;"><code>AWS EC2 (t2.micro Free Tier)</code></td>
            <td style="padding:10px 14px;color:var(--muted);">100% Free Tier with GP3 EBS persistent storage</td>
          </tr>
          <tr>
            <td style="padding:10px 14px;font-weight:700;">CI / Tests</td>
            <td style="padding:10px 14px;"><code>pytest + 15 unit/integration tests</code></td>
            <td style="padding:10px 14px;color:var(--muted);">Agent behavior, booking, scheduling, concurrency, metrics</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</div>

<!-- ===== 5. ER DIAGRAM ===== -->
<div class="slide">
  <div class="slide-body">
    <span class="section-num">Data Model</span>
    <h2>Entity-Relationship Diagram</h2>
    <p class="subtitle">Core schema covering shipments, appointments, drivers, facilities, and agent metrics</p>
    <div style="flex:1;display:flex;align-items:center;justify-content:center;">
      <div class="screenshot-frame" style="max-width:1080px;flex:none;background:#fff;">
        <img src="data:image/png;base64,{imgs['er_diagram']}" alt="ER Diagram" style="max-height:520px;width:auto;" />
      </div>
    </div>
  </div>
</div>

<!-- ===== 6. ROLE-BASED VIEWS ===== -->
<div class="slide">
  <div class="slide-body">
    <span class="section-num">User Experience</span>
    <h2>Role-Based Dashboards</h2>
    <p class="subtitle">Every stakeholder sees exactly what they need &mdash; 6 roles, 7 tabs, zero clutter</p>
    <div style="flex:1;display:flex;flex-direction:column;gap:16px;">
      <div class="four-col" style="flex:1;">
        <div class="card blue-accent">
          <h4 style="color:var(--accent2);">Driver</h4>
          <p style="font-size:12px;color:var(--muted);margin-bottom:8px;">Self-service delay reporting and slot booking via chat</p>
          <ul>
            <li>My Loads &mdash; inbound shipments with ETA &amp; status</li>
            <li>Chat with exception agent</li>
            <li>Report delay / request reschedule</li>
            <li>Receive AI-proposed slot options</li>
            <li>GPS dual-ETA for accurate arrival预测</li>
          </ul>
          <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:4px;">
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Dashboard</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Chat</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Inbound</span></span>
          </div>
        </div>
        <div class="card green-accent">
          <h4 style="color:var(--green);">Operations</h4>
          <p style="font-size:12px;color:var(--muted);margin-bottom:8px;">Exception queue management and scheduler control</p>
          <ul>
            <li>Exceptions queue with type filter</li>
            <li>Scheduler policy editor (priority weights)</li>
            <li>Penalty request management</li>
            <li>Run Scheduler &mdash; re-sequence all dock slots</li>
            <li>Allocation policy trade-off visibility</li>
          </ul>
          <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:4px;">
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Dashboard</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Ops</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Inbound</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Analytics</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Chat</span></span>
          </div>
        </div>
        <div class="card amber-accent">
          <h4 style="color:var(--amber);">Warehouse</h4>
          <p style="font-size:12px;color:var(--muted);margin-bottom:8px;">Dock slot confirmation and facility operations</p>
          <ul>
            <li>Pending confirmations board</li>
            <li>Confirm / Reject dock slots</li>
            <li>Dock &amp; facility stats (unique docks, facilities)</li>
            <li>Action-needed alerts</li>
            <li>Customer name and time window per slot</li>
          </ul>
          <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:4px;">
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Dashboard</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Warehouse</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Inbound</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Analytics</span></span>
          </div>
        </div>
        <div class="card purple-accent">
          <h4 style="color:var(--purple);">Admin</h4>
          <p style="font-size:12px;color:var(--muted);margin-bottom:8px;">Full system control, baselines, and audit trail</p>
          <ul>
            <li>User management (create/disable accounts)</li>
            <li>Baseline tuning (6 KPI baselines)</li>
            <li>Master data CRUD (9 tables)</li>
            <li>Audit log &mdash; every mutation tracked</li>
            <li>Settings and runtime configuration</li>
          </ul>
          <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:4px;">
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Dashboard</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Admin</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Ops</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Warehouse</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Analytics</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Inbound</span></span>
            <span class="metric-pill" style="font-size:10px;padding:3px 8px;"><span class="val">Chat</span></span>
          </div>
        </div>
      </div>
      <div style="display:flex;gap:16px;">
        <div class="card" style="flex:1;padding:12px 16px;">
          <div style="display:flex;align-items:center;gap:10px;">
            <span style="font-size:24px;font-weight:800;color:var(--accent);">6</span>
            <div><strong>User Roles</strong><br/><span style="font-size:11px;color:var(--muted);">Driver, Ops, Warehouse, Admin, Carrier, Customer</span></div>
          </div>
        </div>
        <div class="card" style="flex:1;padding:12px 16px;">
          <div style="display:flex;align-items:center;gap:10px;">
            <span style="font-size:24px;font-weight:800;color:var(--green);">7</span>
            <div><strong>Tab Views</strong><br/><span style="font-size:11px;color:var(--muted);">Dashboard, Chat, Ops, Warehouse, Admin, Analytics, Inbound</span></div>
          </div>
        </div>
        <div class="card" style="flex:1;padding:12px 16px;">
          <div style="display:flex;align-items:center;gap:10px;">
            <span style="font-size:24px;font-weight:800;color:var(--amber);">2</span>
            <div><strong>Auth Methods</strong><br/><span style="font-size:11px;color:var(--muted);">Username/password login, role-based access control</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ===== 5. AGENT HEALTH ===== -->
<div class="slide">
  <div class="slide-body">
    <span class="section-num">Agent Metrics</span>
    <h2>Agent Health &amp; Guardrails</h2>
    <p class="subtitle">Real-time telemetry on LLM agent decision quality</p>
    <div class="two-col" style="flex:1;">
      <div style="display:flex;flex-direction:column;gap:14px;">
        <div class="card">
          <h4>Three Core Rings</h4>
          <div style="display:flex;gap:28px;margin-top:10px;">
            <div style="text-align:center;">
              <div class="ring" style="background:conic-gradient(var(--green) 0% 87%,var(--surface2) 87% 100%);">
                <span class="ring-label">87%</span>
              </div>
              <div style="font-size:12px;color:var(--muted);margin-top:4px;">Trust</div>
            </div>
            <div style="text-align:center;">
              <div class="ring" style="background:conic-gradient(var(--accent) 0% 72%,var(--surface2) 72% 100%);">
                <span class="ring-label">72%</span>
              </div>
              <div style="font-size:12px;color:var(--muted);margin-top:4px;">Autonomy</div>
            </div>
            <div style="text-align:center;">
              <div class="ring" style="background:conic-gradient(var(--amber) 0% 65%,var(--surface2) 65% 100%);">
                <span class="ring-label">65%</span>
              </div>
              <div style="font-size:12px;color:var(--muted);margin-top:4px;">Fit</div>
            </div>
          </div>
          <p style="margin-top:10px;font-size:12px;">Trust = 1 &minus; (agent_faults / cases)<br/>Autonomy = self-resolved / total<br/>Fit = first_option_accepted / with_option_data</p>
        </div>
        <div class="card">
          <h4>Per-Turn Eval Table</h4>
          <p style="font-size:13px;">Every LangGraph turn is logged to <code>agent_turn_evals</code>:</p>
          <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;">
            <span class="metric-pill"><span class="val">invented_slot</span></span>
            <span class="metric-pill"><span class="val">skipped_tool</span></span>
            <span class="metric-pill"><span class="val">invalid_book_attempt</span></span>
            <span class="metric-pill"><span class="val">tool_grounding_score</span></span>
          </div>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:14px;">
        <div class="card">
          <h4>Performance Measures (6 Cards)</h4>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
            <div class="metric-pill"><span class="val">Time to Resolve</span> &nbsp;45m base</div>
            <div class="metric-pill"><span class="val">Human Help Needed</span></div>
            <div class="metric-pill"><span class="val">Self-Service Rescheduling</span></div>
            <div class="metric-pill"><span class="val">ETA Error</span> &nbsp;40m base</div>
            <div class="metric-pill"><span class="val">First Option Accepted</span> &nbsp;35%</div>
            <div class="metric-pill"><span class="val">Wait Reduced</span></div>
          </div>
        </div>
        <div class="card">
          <h4>CloudWatch: <code>SetuHaul/Agent</code></h4>
          <p style="font-size:13px;">9 metrics pushed via <code>POST /api/analytics/cloudwatch-metrics/push</code></p>
          <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;">
            <span class="metric-pill"><span class="val">Trust</span></span>
            <span class="metric-pill"><span class="val">Autonomy</span></span>
            <span class="metric-pill"><span class="val">Fit</span></span>
            <span class="metric-pill"><span class="val">HumanHelpRate</span></span>
            <span class="metric-pill"><span class="val">SelfServiceRate</span></span>
            <span class="metric-pill"><span class="val">AvgResolveMin</span></span>
            <span class="metric-pill"><span class="val">AvgEtaErrorMin</span></span>
            <span class="metric-pill"><span class="val">AvgWaitReducedMin</span></span>
            <span class="metric-pill"><span class="val">Cases</span></span>
          </div>
        </div>
        <div class="card">
          <h4>Guardrails Engine</h4>
          <p style="font-size:13px;">Every agent response passes guardrails logged to <code>guardrail_events</code>:</p>
          <div style="display:flex;gap:8px;margin-top:8px;">
            <span class="metric-pill"><span class="val" style="color:var(--red);">BLOCK</span> Invalid bookings</span>
            <span class="metric-pill"><span class="val" style="color:var(--amber);">ESCALATE</span> High-risk</span>
            <span class="metric-pill"><span class="val" style="color:var(--green);">WARN</span> Soft violations</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ===== 6. WEEK-OVER-WEEK ===== -->
<div class="slide">
  <div class="slide-body">
    <span class="section-num">Trending</span>
    <h2>Week-Over-Week Snapshots</h2>
    <p class="subtitle">Per-scope KPI tracking with delta indicators</p>
    <div style="flex:1;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="border-bottom:2px solid var(--border);">
            <th style="text-align:left;padding:8px 12px;color:var(--muted);font-size:12px;">SCOPE</th>
            <th style="text-align:right;padding:8px 12px;color:var(--muted);font-size:12px;">CASES</th>
            <th style="text-align:right;padding:8px 12px;color:var(--muted);font-size:12px;">SELF-SERVICE</th>
            <th style="text-align:right;padding:8px 12px;color:var(--muted);font-size:12px;">HUMAN HELP</th>
            <th style="text-align:right;padding:8px 12px;color:var(--muted);font-size:12px;">AVG RESOLVE</th>
            <th style="text-align:right;padding:8px 12px;color:var(--muted);font-size:12px;">ETA ERROR</th>
            <th style="text-align:right;padding:8px 12px;color:var(--muted);font-size:12px;">WAIT REDUCED</th>
          </tr>
        </thead>
        <tbody>
          <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:10px 12px;font-weight:700;">NETWORK</td>
            <td style="text-align:right;padding:10px 12px;">142</td>
            <td style="text-align:right;padding:10px 12px;">68% <span style="color:var(--green);font-size:12px;">&#9650; +4%</span></td>
            <td style="text-align:right;padding:10px 12px;">12% <span style="color:var(--green);font-size:12px;">&#9660; &minus;2%</span></td>
            <td style="text-align:right;padding:10px 12px;">32m <span style="color:var(--green);font-size:12px;">&#9660; &minus;8m</span></td>
            <td style="text-align:right;padding:10px 12px;">18m <span style="color:var(--green);font-size:12px;">&#9660; &minus;5m</span></td>
            <td style="text-align:right;padding:10px 12px;">22m <span style="color:var(--green);font-size:12px;">&#9650; +6m</span></td>
          </tr>
          <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:10px 12px;font-weight:700;">FACILITY</td>
            <td style="text-align:right;padding:10px 12px;">48</td>
            <td style="text-align:right;padding:10px 12px;">71% <span style="color:var(--green);font-size:12px;">&#9650; +6%</span></td>
            <td style="text-align:right;padding:10px 12px;">10% <span style="color:var(--green);font-size:12px;">&#9660; &minus;3%</span></td>
            <td style="text-align:right;padding:10px 12px;">28m <span style="color:var(--green);font-size:12px;">&#9660; &minus;12m</span></td>
            <td style="text-align:right;padding:10px 12px;">15m <span style="color:var(--green);font-size:12px;">&#9660; &minus;7m</span></td>
            <td style="text-align:right;padding:10px 12px;">26m <span style="color:var(--green);font-size:12px;">&#9650; +8m</span></td>
          </tr>
          <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:10px 12px;font-weight:700;">DRIVER</td>
            <td style="text-align:right;padding:10px 12px;">36</td>
            <td style="text-align:right;padding:10px 12px;">58% <span style="color:var(--amber);font-size:12px;">&#9660; &minus;2%</span></td>
            <td style="text-align:right;padding:10px 12px;">22% <span style="color:var(--amber);font-size:12px;">&#9650; +3%</span></td>
            <td style="text-align:right;padding:10px 12px;">38m <span style="color:var(--amber);font-size:12px;">&#9650; +4m</span></td>
            <td style="text-align:right;padding:10px 12px;">20m <span style="color:var(--amber);font-size:12px;">&#9650; +2m</span></td>
            <td style="text-align:right;padding:10px 12px;">18m <span style="color:var(--amber);font-size:12px;">&#9660; &minus;2m</span></td>
          </tr>
          <tr>
            <td style="padding:10px 12px;font-weight:700;">CARRIER</td>
            <td style="text-align:right;padding:10px 12px;">58</td>
            <td style="text-align:right;padding:10px 12px;">74% <span style="color:var(--green);font-size:12px;">&#9650; +8%</span></td>
            <td style="text-align:right;padding:10px 12px;">8% <span style="color:var(--green);font-size:12px;">&#9660; &minus;4%</span></td>
            <td style="text-align:right;padding:10px 12px;">25m <span style="color:var(--green);font-size:12px;">&#9660; &minus;6m</span></td>
            <td style="text-align:right;padding:10px 12px;">12m <span style="color:var(--green);font-size:12px;">&#9660; &minus;4m</span></td>
            <td style="text-align:right;padding:10px 12px;">30m <span style="color:var(--green);font-size:12px;">&#9650; +10m</span></td>
          </tr>
        </tbody>
      </table>
      <div class="three-col" style="margin-top:16px;">
        <div class="card">
          <h4>vs Manual Baseline</h4>
          <p>Each scope KPI compared against admin-configurable <code>manual_baseline</code> &mdash; showing exactly how the agent performs vs human dispatch.</p>
        </div>
        <div class="card">
          <h4>Rule-Based Insights</h4>
          <p>Auto-generated insight cards when delta thresholds are breached:<br/>
          <span style="color:var(--amber);">"Human help rising"</span> when rate &Delta; &gt; +5%<br/>
          <span style="color:var(--red);">"Resolve time stretched"</span> when &Delta; &gt; +2min</p>
        </div>
        <div class="card">
          <h4>AI Insights Layer</h4>
          <p>Optional LLM pass (OpenRouter) synthesizes weekly data into natural-language insight cards with severity: <span style="color:var(--green);">ok</span>, <span style="color:var(--amber);">warn</span>, <span style="color:var(--red);">danger</span>, <span style="color:var(--cyan);">info</span>.</p>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ===== 7. SCREENSHOT — LOGIN ===== -->
<div class="slide">
  <div class="slide-body">
    <span class="section-num">Live Demo</span>
    <h2>Login &amp; Role Selection</h2>
    <p class="subtitle">Quick-select accounts &mdash; each role unlocks a different dashboard and agent capability set</p>
    <div style="flex:1;display:flex;flex-direction:column;align-items:center;">
      <div class="screenshot-frame" style="max-width:900px;">
        <img src="data:image/png;base64,{imgs['login']}" alt="Login screen" />
      </div>
      <div class="screenshot-label">SetuHaul login &mdash; themed, animated atmosphere with quick-select account picker</div>
    </div>
  </div>
</div>

<!-- ===== 8. SCREENSHOT — DRIVER ===== -->
<div class="slide">
  <div class="slide-body">
    <span class="section-num">Live Demo</span>
    <h2>Driver Dashboard &amp; Chat</h2>
    <p class="subtitle">Driver sees my loads + exception chat agent with slot options</p>
    <div class="two-col" style="flex:1;">
      <div style="display:flex;flex-direction:column;">
        <div class="screenshot-frame" style="flex:1;">
          <img src="data:image/png;base64,{imgs['driver_dash']}" alt="Driver dashboard" />
        </div>
        <div class="screenshot-label">Driver dashboard &mdash; inbound shipments, exception status, agent health rings</div>
      </div>
      <div style="display:flex;flex-direction:column;">
        <div class="screenshot-frame" style="flex:1;">
          <img src="data:image/png;base64,{imgs['driver_chat']}" alt="Driver chat" />
        </div>
        <div class="screenshot-label">Driver chat &mdash; report delay, AI proposes reschedule options, driver picks one</div>
      </div>
    </div>
  </div>
</div>

<!-- ===== 9. SCREENSHOT — OPS ===== -->
<div class="slide">
  <div class="slide-body">
    <span class="section-num">Live Demo</span>
    <h2>Operations Dashboard &amp; Scheduler</h2>
    <p class="subtitle">Ops sees exception queue, runs scheduler, edits allocation policy</p>
    <div class="two-col" style="flex:1;">
      <div style="display:flex;flex-direction:column;">
        <div class="screenshot-frame" style="flex:1;">
          <img src="data:image/png;base64,{imgs['ops_dash']}" alt="Ops dashboard" />
        </div>
        <div class="screenshot-label">Ops dashboard &mdash; exceptions queue with type filter + Run Scheduler action</div>
      </div>
      <div style="display:flex;flex-direction:column;">
        <div class="screenshot-frame" style="flex:1;">
          <img src="data:image/png;base64,{imgs['ops_sched']}" alt="Scheduler policy" />
        </div>
        <div class="screenshot-label">Scheduler policy &mdash; editable priority weights, in-progress protection, objective tuning</div>
      </div>
    </div>
  </div>
</div>

<!-- ===== 10. SCREENSHOT — WAREHOUSE & ADMIN ===== -->
<div class="slide">
  <div class="slide-body">
    <span class="section-num">Live Demo</span>
    <h2>Warehouse &amp; Admin Panels</h2>
    <p class="subtitle">Warehouse confirms dock slots; Admin tunes baselines and manages users</p>
    <div class="two-col" style="flex:1;">
      <div style="display:flex;flex-direction:column;">
        <div class="screenshot-frame" style="flex:1;">
          <img src="data:image/png;base64,{imgs['warehouse']}" alt="Warehouse panel" />
        </div>
        <div class="screenshot-label">Warehouse &mdash; pending confirmations, dock stats, confirm/reject actions</div>
      </div>
      <div style="display:flex;flex-direction:column;">
        <div class="screenshot-frame" style="flex:1;">
          <img src="data:image/png;base64,{imgs['admin']}" alt="Admin panel" />
        </div>
        <div class="screenshot-label">Admin &mdash; user management, baseline tuning, master data CRUD, audit log</div>
      </div>
    </div>
  </div>
</div>

<!-- ===== 11. SCREENSHOT — ANALYTICS ===== -->
<div class="slide">
  <div class="slide-body">
    <span class="section-num">Live Demo</span>
    <h2>Analytics &amp; Insights</h2>
    <p class="subtitle">6 performance measure cards + 3 agent health rings + AI insight cards + WoW snapshots</p>
    <div style="flex:1;display:flex;flex-direction:column;">
      <div class="screenshot-frame" style="flex:1;">
        <img src="data:image/png;base64,{imgs['analytics']}" alt="Analytics panel" />
      </div>
      <div class="screenshot-label">Analytics panel &mdash; measure cards, agent health rings, insight cards, week-over-week snapshots</div>
    </div>
  </div>
</div>

<!-- ===== 12. MONITORING ===== -->
<div class="slide">
  <div class="slide-body">
    <span class="section-num">Monitoring</span>
    <h2>Observability &amp; Monitoring</h2>
    <p class="subtitle">Every agent turn traced, every metric pushed &mdash; full production telemetry</p>
    <div class="two-col" style="flex:1;">
      <div style="display:flex;flex-direction:column;gap:10px;">
        <div class="screenshot-frame" style="flex:1;">
          <img src="data:image/png;base64,{imgs['langsmith']}" alt="LangSmith traces" />
        </div>
        <div class="screenshot-label">LangSmith &mdash; per-turn trace timeline showing latency, tool calls, token usage, and guardrail actions</div>
      </div>
      <div style="display:flex;flex-direction:column;gap:10px;">
        <div class="screenshot-frame" style="flex:1;">
          <img src="data:image/png;base64,{imgs['cloudwatch']}" alt="CloudWatch dashboard" />
        </div>
        <div class="screenshot-label">AWS CloudWatch &mdash; real-time Agent Health, Resolution Speed, Case Throughput, and Application Logs</div>
      </div>
    </div>
  </div>
</div>

<!-- ===== 13. AI AGENT FLOW ===== -->
<div class="slide">
  <div class="slide-body">
    <span class="section-num">AI Agent</span>
    <h2>Exception Agent &mdash; Turn Lifecycle</h2>
    <p class="subtitle">LangGraph state machine with guardrails at every decision point</p>
    <div style="flex:1;display:flex;flex-direction:column;gap:16px;">
      <div class="arch-row" style="flex-wrap:wrap;">
        <div class="flow-step"><span class="step-num">1</span><div><strong>Driver Message</strong><br/><span style="font-size:11px;color:var(--muted);">"Running late 45min"</span></div></div>
        <span class="arch-arrow">&rarr;</span>
        <div class="flow-step"><span class="step-num">2</span><div><strong>Intent Detection</strong><br/><span style="font-size:11px;color:var(--muted);">REPORT_DELAY</span></div></div>
        <span class="arch-arrow">&rarr;</span>
        <div class="flow-step"><span class="step-num">3</span><div><strong>Context Gather</strong><br/><span style="font-size:11px;color:var(--muted);">DB lookups, facility rules</span></div></div>
        <span class="arch-arrow">&rarr;</span>
        <div class="flow-step"><span class="step-num">4</span><div><strong>LLM Slot Proposal</strong><br/><span style="font-size:11px;color:var(--muted);">OpenRouter generates options</span></div></div>
        <span class="arch-arrow">&rarr;</span>
        <div class="flow-step"><span class="step-num">5</span><div><strong>Guardrails Check</strong><br/><span style="font-size:11px;color:var(--muted);">No invented slots</span></div></div>
        <span class="arch-arrow">&rarr;</span>
        <div class="flow-step"><span class="step-num">6</span><div><strong>Respond + Log</strong><br/><span style="font-size:11px;color:var(--muted);">trace, eval, CloudWatch</span></div></div>
      </div>
      <div class="two-col" style="flex:1;">
        <div class="card">
          <h4>Insights Agent Pipeline</h4>
          <p style="font-size:13px;">Separate LangGraph graph for weekly insights:</p>
          <div style="display:flex;flex-direction:column;gap:6px;margin-top:8px;">
            <div class="flow-step"><span class="step-num">A</span><div><strong>gather_context</strong> &mdash; pulls weekly reports + agent health</div></div>
            <div class="flow-step"><span class="step-num">B</span><div><strong>generate_insights</strong> &mdash; LLM or heuristic fallback</div></div>
            <div class="flow-step"><span class="step-num">C</span><div><strong>persist</strong> &mdash; saves to <code>ai_insight_runs</code></div></div>
          </div>
        </div>
        <div class="card">
          <h4>Heuristic Insight Types</h4>
          <ul style="font-size:13px;">
            <li><span style="color:var(--green);">Agent health pulse</span> &mdash; always generated</li>
            <li><span style="color:var(--amber);">Human help rising</span> &mdash; rate &Delta; &gt; +5%</li>
            <li><span style="color:var(--amber);">Self-service slipping</span> &mdash; rate &Delta; &lt; &minus;5%</li>
            <li><span style="color:var(--red);">Resolve time stretched</span> &mdash; &Delta; &gt; +2min</li>
            <li><span style="color:var(--green);">Human help improving</span> &mdash; rate &Delta; &lt; &minus;5%</li>
            <li><span style="color:var(--cyan);">No strong movement yet</span> &mdash; fallback</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ===== 14. THANK YOU ===== -->
<div class="slide thank-slide">
  <div class="slide-body">
    <div style="font-size:56px;margin-bottom:16px;">&#x1F69B;</div>
    <h1>Thank You</h1>
    <p style="font-size:20px;color:var(--muted);max-width:640px;margin:0 auto 16px;">
      SetuHaul &mdash; from driver message to CloudWatch metric in one turn.<br/>
      Trust. Autonomy. Fit. Measured, not assumed.
    </p>
    <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
      <span class="metric-pill"><span class="val">15 tests passing</span></span>
      <span class="metric-pill"><span class="val">8 screenshots</span></span>
      <span class="metric-pill"><span class="val">4 user roles</span></span>
      <span class="metric-pill"><span class="val">9 CloudWatch metrics</span></span>
      <span class="metric-pill"><span class="val">6 performance KPIs</span></span>
      <span class="metric-pill"><span class="val">LangGraph + Guardrails</span></span>
    </div>
  </div>
</div>

</body>
</html>"""


def main():
    from playwright.sync_api import sync_playwright
    import time

    html = build_html()
    html_path = ASSETS / "setuhaul_demo_presentation.html"
    html_path.write_text(html)
    print(f"HTML written: {html_path} ({len(html)//1024} KB)")

    pdf_path = ASSETS / "setuhaul_demo_presentation.pdf"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file://{html_path.resolve()}")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        page.pdf(
            path=str(pdf_path),
            width="1280px",
            height="720px",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()

    print(f"PDF written: {pdf_path} ({pdf_path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
