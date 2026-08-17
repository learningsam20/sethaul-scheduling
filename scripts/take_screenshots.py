#!/usr/bin/env python3
"""Capture screenshots of the SetuHaul app for the presentation."""
from __future__ import annotations

import time
from pathlib import Path

SCREENSHOTS = Path(__file__).resolve().parents[1] / "assets" / "screenshots"
SCREENSHOTS.mkdir(parents=True, exist_ok=True)

BASE = "http://127.0.0.1:5173"


def screenshot(page, name: str):
    path = SCREENSHOTS / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  {name}")


def fresh_page(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    return ctx, ctx.new_page()


def login(page, username: str):
    page.goto(BASE)
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    page.fill("#login-user", username)
    page.fill("#login-pass", "pin1234")
    page.click(".login-submit")
    page.wait_for_load_state("networkidle")
    time.sleep(2)


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # 1. Login page
        print("1. Login page")
        ctx, page = fresh_page(browser)
        page.goto(BASE)
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)
        screenshot(page, "01_login")
        ctx.close()

        # 2. Driver dashboard
        print("2. Driver dashboard")
        ctx, page = fresh_page(browser)
        login(page, "driver.ravi")
        time.sleep(1)
        screenshot(page, "02_driver_dashboard")
        ctx.close()

        # 3. Driver chat (send delay message)
        print("3. Driver chat")
        ctx, page = fresh_page(browser)
        login(page, "driver.ravi")
        time.sleep(1)
        nav = page.locator('.nav-item[aria-label="Chat"]')
        if nav.count():
            nav.click()
            time.sleep(1)
        textarea = page.locator("textarea").first
        if textarea.count():
            textarea.fill("Running late by 45 minutes, ETA 11:20")
            page.locator("button.send-btn, .chat-input button[type='submit'], .chat-send").first.click()
            time.sleep(5)
            page.wait_for_load_state("networkidle")
        screenshot(page, "03_driver_chat")
        ctx.close()

        # 4. Ops dashboard
        print("4. Ops dashboard")
        ctx, page = fresh_page(browser)
        login(page, "ops")
        time.sleep(1)
        screenshot(page, "04_ops_dashboard")
        ctx.close()

        # 5. Ops scheduler
        print("5. Ops scheduler")
        ctx, page = fresh_page(browser)
        login(page, "ops")
        time.sleep(1)
        nav = page.locator('.nav-item[aria-label="Exceptions"]')
        if nav.count():
            nav.click()
            time.sleep(2)
        screenshot(page, "05_ops_scheduler")
        ctx.close()

        # 6. Warehouse
        print("6. Warehouse")
        ctx, page = fresh_page(browser)
        login(page, "warehouse.jai")
        time.sleep(1)
        nav = page.locator('.nav-item[aria-label="Warehouse"]')
        if nav.count():
            nav.click()
            time.sleep(2)
        screenshot(page, "06_warehouse")
        ctx.close()

        # 7. Admin
        print("7. Admin")
        ctx, page = fresh_page(browser)
        login(page, "admin")
        time.sleep(1)
        nav = page.locator('.nav-item[aria-label="Admin"]')
        if nav.count():
            nav.click()
            time.sleep(2)
        screenshot(page, "07_admin")
        ctx.close()

        # 8. Analytics
        print("8. Analytics")
        ctx, page = fresh_page(browser)
        login(page, "ops")
        time.sleep(0.5)
        nav = page.locator('.nav-item[aria-label="Analytics"]')
        if nav.count():
            nav.click()
            time.sleep(2.5)
        screenshot(page, "08_analytics")
        ctx.close()

        browser.close()

    print(f"\nDone — {len(list(SCREENSHOTS.glob('*.png')))} screenshots in {SCREENSHOTS}")


if __name__ == "__main__":
    main()
