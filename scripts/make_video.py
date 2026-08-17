#!/usr/bin/env python3
"""Build demo video: title frame → app screenshots → langsmith frame."""
from __future__ import annotations

import subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SS = ASSETS / "screenshots"
FRAMES = ASSETS / "video_frames"
FRAMES.mkdir(exist_ok=True)
OUTPUT = ASSETS / "setuhaul_demo.mp4"

# Ordered list of frames: (source_file, label_overlay_or_None, duration_seconds)
FRAMES_SPEC = [
    ("__title__",   None,                5),
    ("01_login.png", None,               6),
    ("02_driver_dashboard.png", None,    5),
    ("03_driver_chat.png", None,         5),
    ("04_ops_dashboard.png", None,       5),
    ("05_ops_scheduler.png", None,       5),
    ("06_warehouse.png", None,           5),
    ("07_admin.png", None,               5),
    ("08_analytics.png", None,           6),
    ("__langsmith__", None,              6),
]

TITLE_HTML = """<!DOCTYPE html>
<html><head><style>
  body {{ margin:0; width:1440px; height:900px; background:#0b0e14; display:flex;
         align-items:center; justify-content:center; font-family:Inter,system-ui,sans-serif; color:#e4e8f1; }}
  .wrap {{ text-align:center; }}
  .emoji {{ font-size:72px; margin-bottom:16px; }}
  h1 {{ font-size:64px; font-weight:900; letter-spacing:-1.5px; margin-bottom:10px; }}
  h1 span {{ color:#3b82f6; }}
  .tag {{ font-size:24px; color:#8892a4; margin-bottom:16px; }}
  .meta {{ font-size:14px; color:#8892a4; }}
</style></head><body>
  <div class="wrap">
    <div class="emoji">&#x1F69B;</div>
    <h1><span>Setu</span>Haul</h1>
    <p class="tag">AI-Powered Dock Appointment Scheduling for Freight Logistics</p>
    <p class="meta">LangGraph Agent &bull; CloudWatch Metrics &bull; Real-Time Operations</p>
  </div>
</body></html>"""

LANGSMITH_HTML = """<!DOCTYPE html>
<html><head><style>
  body {{ margin:0; width:1440px; height:900px; background:#0b0e14; display:flex;
         align-items:center; justify-content:center; font-family:Inter,system-ui,sans-serif; color:#e4e8f1; }}
  .wrap {{ text-align:center; max-width:800px; }}
  h1 {{ font-size:48px; font-weight:800; margin-bottom:12px; }}
  h1 span {{ color:#3b82f6; }}
  .sub {{ font-size:20px; color:#8892a4; margin-bottom:24px; line-height:1.6; }}
  .pills {{ display:flex; gap:10px; justify-content:center; flex-wrap:wrap; }}
  .pill {{ background:#1c2333; border:1px solid #262d3d; border-radius:6px; padding:8px 14px;
           font-size:13px; font-family:'JetBrains Mono',monospace; }}
  .pill b {{ color:#22c55e; }}
</style></head><body>
  <div class="wrap">
    <h1>Trust. Autonomy. <span>Fit.</span></h1>
    <p class="sub">Every agent turn traced to LangSmith.<br>Every metric pushed to CloudWatch.<br>Measured, not assumed.</p>
    <div class="pills">
      <div class="pill"><b>15</b> tests passing</div>
      <div class="pill"><b>9</b> CloudWatch metrics</div>
      <div class="pill"><b>6</b> performance KPIs</div>
      <div class="pill"><b>4</b> user roles</div>
      <div class="pill"><b>LangGraph</b> + Guardrails</div>
    </div>
  </div>
</body></html>"""


def render_title_frame():
    from playwright.sync_api import sync_playwright
    path = FRAMES / "f00_title.png"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page.set_content(TITLE_HTML)
        time.sleep(0.5)
        page.screenshot(path=str(path))
        browser.close()
    print("  f00_title.png")
    return path


def render_langsmith_frame():
    from playwright.sync_api import sync_playwright
    path = FRAMES / "f99_langsmith.png"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page.set_content(LANGSMITH_HTML)
        time.sleep(0.5)
        page.screenshot(path=str(path))
        browser.close()
    print("  f99_langsmith.png")
    return path


def copy_app_screenshots():
    """Copy and rename app screenshots into the frames directory."""
    mapping = [
        ("01_login.png",            "f01_login.png"),
        ("02_driver_dashboard.png", "f02_driver_dashboard.png"),
        ("03_driver_chat.png",      "f03_driver_chat.png"),
        ("04_ops_dashboard.png",    "f04_ops_dashboard.png"),
        ("05_ops_scheduler.png",    "f05_ops_scheduler.png"),
        ("06_warehouse.png",        "f06_warehouse.png"),
        ("07_admin.png",            "f07_admin.png"),
        ("08_analytics.png",        "f08_analytics.png"),
    ]
    for src, dst in mapping:
        import shutil
        shutil.copy2(SS / src, FRAMES / dst)
        print(f"  {dst}")


def build_video():
    """Use ffmpeg to concatenate frames with xfade transitions."""
    # Gather frame files in order
    frame_files = sorted(FRAMES.glob("f*.png"))
    n = len(frame_files)
    print(f"\nConcatenating {n} frames...")

    # Each frame shown for a duration (we use 5s uniform, with 1s crossfade)
    # Build ffmpeg inputs + xfade chain
    input_args = []
    for f in frame_files:
        input_args += ["-loop", "1", "-t", "5", "-i", str(f)]

    if n == 1:
        filter_str = "[0:v]format=yuv420p[outv]"
    else:
        parts = []
        offset = 4.0  # 5s - 1s fade
        parts.append(f"[0:v][1:v]xfade=transition=fade:duration=1:offset={offset:.1f}[v01]")
        prev = "v01"
        for i in range(2, n):
            out = f"v{i-1:02d}{i:02d}"
            offset = 4.0 + (i - 1) * 4.0
            parts.append(f"[{prev}][{i}:v]xfade=transition=fade:duration=1:offset={offset:.1f}[{out}]")
            prev = out
        parts.append(f"[{prev}]format=yuv420p[outv]")
        filter_str = ";".join(parts)

    cmd = [
        "ffmpeg", "-y",
        *input_args,
        "-filter_complex", filter_str,
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", "30",
        str(OUTPUT),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print("STDERR:", result.stderr[-3000:] if result.stderr else "")
        raise RuntimeError(f"ffmpeg failed with code {result.returncode}")

    size_mb = OUTPUT.stat().st_size / (1024 * 1024)
    print(f"\nVideo written: {OUTPUT} ({size_mb:.1f} MB)")


def main():
    print("Rendering title frame...")
    render_title_frame()

    print("Copying app screenshots...")
    copy_app_screenshots()

    print("Rendering langsmith closing frame...")
    render_langsmith_frame()

    build_video()


if __name__ == "__main__":
    main()
