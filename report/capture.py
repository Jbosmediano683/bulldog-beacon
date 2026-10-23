"""Capture the report and slide screenshots from a real run of the app.

Starts a clean copy of Bulldog Beacon on port 8030 (scratch database), plays the
"night shift at YCCI" scenario in headless Microsoft Edge with Playwright, and
saves screenshots to report/screenshots/. Every AI step is a real gpt-6-luna
call; the run log (tokens and tool traces) is saved to output/walkthrough_runs.json.

    pip install playwright      (uses the system Edge, no browser download)
    python report/capture.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "report" / "screenshots"
PORT = 8030
BASE = f"http://127.0.0.1:{PORT}"
DB = Path(tempfile.mkdtemp(prefix="beacon-shots-")) / "shots.db"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def shot(page: Page, name: str, selector: str | None = None) -> None:
    path = SHOTS / f"{name}.jpg"
    time.sleep(0.6)
    if selector:
        page.locator(selector).first.screenshot(path=str(path), type="jpeg", quality=86)
    else:
        page.screenshot(path=str(path), type="jpeg", quality=86)
    log(f"saved {path.name}")


def tab(page: Page, label: str) -> None:
    page.locator(".tabbar button", has_text=label).first.click()
    time.sleep(1.2)


def wait_text(page: Page, selector: str, text: str, timeout: float = 90) -> None:
    page.locator(selector, has_text=text).first.wait_for(timeout=timeout * 1000)


def sign_in(page: Page, label: str) -> None:
    page.goto(BASE)
    page.locator(".demo-btn", has_text=label).click()
    page.locator(".tabbar").wait_for(timeout=20000)
    time.sleep(2.5)


def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "BEACON_DB": str(DB), "PYTHONUTF8": "1"}
    server = subprocess.Popen([sys.executable, str(ROOT / "run.py"), "--port", str(PORT), "--no-browser", "--reset"],
                              env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                if httpx.get(f"{BASE}/api/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        log("server up")

        # A first real report at the Temple Street Garage, from another member, so the
        # scenario's own report has a real neighbour for the Corroborator to merge with.
        with httpx.Client(base_url=BASE, timeout=90) as api:
            api.post("/api/auth/login", json={"netid": "hd2026", "password": "Bulldog#2026"})
            r = api.post("/api/posts", json={"text": "Someone in a black jacket was trying car door handles on level 2 of the "
                                             "Temple Street garage around 10:30. I yelled and he walked off toward Crown St.",
                                             "category": "suspicious_activity", "place_id": 12})
            log(f"seed report: {r.json()['post']['status']}")

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            ctx = browser.new_context(viewport={"width": 1440, "height": 1010}, device_scale_factor=2, color_scheme="light")
            page = ctx.new_page()

            page.goto(BASE)
            page.locator(".cas-body").wait_for()
            time.sleep(1.5)
            shot(page, "01_login")

            sign_in(page, "Night-shift staff")
            shot(page, "02_desktop_home")
            shot(page, "03_home", ".phone")

            # 1) Ask Beacon before leaving YCCI.
            tab(page, "Ask Beacon")
            q = "I'm finishing my night shift at YCCI around 11. Is it OK to walk to the Temple Street Garage?"
            page.locator(".composer textarea").fill(q)
            page.locator(".composer .send").click()
            page.locator(".bubble.bot .runline").first.wait_for(timeout=90000)
            time.sleep(1)
            page.locator(".app-scroll").evaluate("el => el.scrollTo(0, 0)")
            shot(page, "04_chat", ".phone")
            page.locator(".insights .act", has_text="concierge").first.click()
            page.locator(".insights .trace .step").first.wait_for(timeout=15000)
            shot(page, "05_chat_trace", ".insights")

            # 2) Post what she saw on the way: race and a plate the Moderator should remove.
            tab(page, "Map")
            page.locator(".fab").click()
            page.locator(".sheet textarea").fill(
                "Hispanic guy in a black jacket was pulling on car door handles on level 2 of the Temple Street garage "
                "around 10:45, then walked toward Crown St. His plate was CT 7KX-219.")
            page.locator(".sheet select").select_option(label="Temple Street Garage")
            page.locator(".sheet .btn.primary.block").click()
            page.locator(".sheet .verdict .h2").first.wait_for(timeout=90000)
            time.sleep(4.5)
            shot(page, "06_post_verdict", ".phone")
            page.locator(".sheet .btn", has_text="Done").click()
            time.sleep(12)  # the Corroborator runs in the background
            page.reload()
            page.locator(".tabbar").wait_for()
            time.sleep(4)
            shot(page, "07_post_runs", ".insights")

            tab(page, "Map")
            page.locator(".layer-toggle button", has_text="Safety").click()
            time.sleep(3)
            shot(page, "08_map", ".phone")
            page.add_style_tag(content=".fab{display:none !important}")
            card = page.locator(".incident-card", has_text="Temple").filter(has_not_text="Demo report").first
            card.scroll_into_view_if_needed()
            card.click()
            time.sleep(1.2)
            card.screenshot(path=str(SHOTS / "09_incident_merged.jpg"), type="jpeg", quality=86)
            log("saved 09_incident_merged.jpg")

            # 3) Community: a helpful comment, then one the Moderator stops.
            tab(page, "Community")
            time.sleep(2)
            shot(page, "10_community", ".phone")
            page.add_style_tag(content=".fab{display:none !important}")
            post = page.locator(".post-card", has_text="Temple").filter(has_text="Yale student").filter(has_not_text="Demo post").first
            post.locator(".act-btn", has_text="comment").click()
            box = post.locator(".comment-box input")
            box.wait_for()
            box.fill("Saw someone trying doors on level 3 too, around 10:50. I told the Yale Security officer at the entrance.")
            post.locator(".comment-box .btn").click()
            post.locator(".comment").first.wait_for(timeout=90000)
            time.sleep(1.5)
            box.fill("It's probably one of those homeless guys from the Green, they should all be locked up.")
            post.locator(".comment-box .btn").click()
            post.locator(".comment.held").first.wait_for(timeout=90000)
            time.sleep(1)
            post.scroll_into_view_if_needed()
            post.screenshot(path=str(SHOTS / "11_comment_blocked.jpg"), type="jpeg", quality=86)
            log("saved 11_comment_blocked.jpg")

            # 4) Something nice on campus: an event, inside the app.
            tab(page, "Home")
            page.locator(".app-scroll").evaluate("el => el.scrollTo(0, 620)")
            time.sleep(1.5)
            page.locator(".event-card").first.click()
            page.locator(".sheet .about-label").wait_for()
            time.sleep(2.5)
            shot(page, "12_event_sheet", ".phone")
            page.locator(".sheet .btn", has_text="Close").click()

            # 5) Walk With Me with a 1-minute check-in that she misses.
            tab(page, "Walk")
            page.locator(".app-scroll select").nth(1).select_option(label="Temple Street Garage")
            page.locator("input[type=range]").evaluate(
                "el => { const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;"
                " s.call(el, '1'); el.dispatchEvent(new Event('input', { bubbles: true })); }")
            time.sleep(0.5)
            page.locator(".btn.primary", has_text="Start walk").click()
            time.sleep(2)
            shot(page, "13_walk_active", ".phone")
            log("waiting for the missed check-in...")
            wait_text(page, ".h1", "Are you OK?", timeout=120)
            time.sleep(1.5)
            shot(page, "14_walk_overdue", ".phone")

            # 6) SOS from the overdue walk, with a short note for responders.
            page.locator(".btn.danger", has_text="I need help").click()
            page.locator(".sos-overlay textarea").wait_for()
            page.locator(".sos-overlay textarea").fill("Someone followed me from the garage stairwell, I'm back inside the YCCI lobby")
            page.locator(".sos-overlay .btn.primary", has_text="Send to dispatch").click()
            wait_text(page, ".sos-overlay", "summarized it for the dispatcher", timeout=90)
            time.sleep(1)
            shot(page, "15_sos", ".phone")

            # 7) The simulated Yale PD side.
            ctx2 = browser.new_context(viewport={"width": 1440, "height": 1010}, device_scale_factor=2, color_scheme="light")
            page2 = ctx2.new_page()
            sign_in(page2, "Dispatcher console")
            page2.locator(".brief").first.wait_for(timeout=30000)
            time.sleep(2)
            shot(page2, "16_dispatch", ".phone")
            page2.locator(".brief").first.scroll_into_view_if_needed()
            time.sleep(1)
            shot(page2, "17_dispatch_brief", ".phone")
            tab(page2, "AI usage")
            time.sleep(1.5)
            shot(page2, "18_usage", ".phone")
            tab(page2, "Resources")
            shot(page2, "19_resources", ".phone")

            # 8) Phone-sized view.
            ctx3 = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, color_scheme="light",
                                       has_touch=True)
            page3 = ctx3.new_page()
            sign_in(page3, "Student")
            shot(page3, "20_mobile_home")
            browser.close()

        # Save the run log for the report's step-by-step walkthrough.
        sys.path.insert(0, str(ROOT / "backend"))
        os.environ["BEACON_DB"] = str(DB)
        import importlib
        import db as dbmod
        importlib.reload(dbmod)
        conn = dbmod.connect()
        runs = dbmod.rows(conn.execute("SELECT * FROM ai_runs ORDER BY id"))
        for r in runs:
            r["trace"] = json.loads(r.pop("trace_json") or "[]")
        posts = dbmod.rows(conn.execute("SELECT id, raw_text, text, status, moderation_json, incident_id FROM posts WHERE demo = 0"))
        incidents = dbmod.rows(conn.execute("SELECT * FROM incidents WHERE demo = 0"))
        comments = dbmod.rows(conn.execute("SELECT id, raw_text, text, status, moderation_json FROM comments WHERE demo = 0"))
        sos = dbmod.rows(conn.execute("SELECT * FROM sos_events"))
        chat = dbmod.rows(conn.execute("SELECT role, content, meta_json FROM chat_messages"))
        (ROOT / "output" / "walkthrough_runs.json").write_text(json.dumps(
            {"runs": runs, "posts": posts, "incidents": incidents, "comments": comments, "sos": sos, "chat": chat},
            indent=1, ensure_ascii=False), encoding="utf-8")
        log(f"saved output/walkthrough_runs.json ({len(runs)} AI runs)")
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
