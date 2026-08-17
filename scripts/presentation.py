#!/usr/bin/env python3
"""Generate presentation.pdf from presentation.html using Playwright."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "docs" / "presentation.html"
PDF = ROOT / "docs" / "presentation.pdf"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(HTML.as_uri())
        page.wait_for_load_state("networkidle")
        page.pdf(
            path=str(PDF),
            format="A4",
            landscape=True,
            print_background=True,
            prefer_css_page_size=True,
        )
        browser.close()

    print(f"PDF written: {PDF} ({PDF.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
