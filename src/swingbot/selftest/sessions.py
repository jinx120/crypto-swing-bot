from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from swingbot.selftest import SessionStep, SessionTrace
from swingbot.selftest.expectations import GUIDE_AFFORDANCES

_WAIT_MS = 8000


def _default_api(base_url: str, token: str, method: str, path: str,
                 body: dict | None = None) -> tuple[int, dict]:
    """Tiny JSON client for session API steps. Returns (status, payload)."""
    req = urllib.request.Request(
        base_url.rstrip("/") + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


@dataclass
class SessionContext:
    base_url: str
    token: str = ""
    screenshot_dir: str = ""
    api_fn: object = None          # (base_url, token, method, path, body) -> (status, json)
    seed_proposals: object = None  # callable(list[dict]) — wired to EphemeralApp

    def api(self, method: str, path: str, body: dict | None = None):
        fn = self.api_fn or _default_api
        return fn(self.base_url, self.token, method, path, body)


class SessionRecorder:
    def __init__(self, name: str):
        self.trace = SessionTrace(session=name, ok=True, started_at=time.time())

    def step(self, desc: str, action: str, ok: bool, detail: str = "",
             expectation_key: str = "", screenshot_path: str = "") -> bool:
        self.trace.steps.append(SessionStep(
            desc=desc, action=action, ok=ok, detail=detail,
            screenshot_path=screenshot_path, expectation_key=expectation_key))
        if not ok:
            self.trace.ok = False
        return ok

    def finish(self) -> SessionTrace:
        self.trace.duration_s = round(time.time() - self.trace.started_at, 2)
        return self.trace


def _goto(page, rec: SessionRecorder, ctx: SessionContext, route: str,
          expectation_key: str = "") -> bool:
    try:
        page.goto(f"{ctx.base_url.rstrip('/')}{route}", wait_until="networkidle")
        return rec.step(f"open {route}", "goto", True)
    except Exception as e:
        return rec.step(f"open {route}", "goto", False,
                        detail=f"{route}: navigation failed: {e}",
                        expectation_key=expectation_key)


def _shoot(page, ctx: SessionContext, name: str) -> str:
    if not ctx.screenshot_dir:
        return ""
    path = os.path.join(ctx.screenshot_dir, f"{name}.png")
    try:
        os.makedirs(ctx.screenshot_dir, exist_ok=True)
        page.screenshot(path=path, full_page=True)
        return path
    except Exception:
        return ""


def _wait(page, rec: SessionRecorder, ctx: SessionContext, route: str,
          selector: str, expectation_key: str, shot_name: str) -> bool:
    try:
        page.wait_for_selector(selector, timeout=_WAIT_MS)
        return rec.step(f"{route} shows {selector}", "assert", True)
    except Exception:
        return rec.step(f"{route} shows {selector}", "assert", False,
                        detail=f"{route}: expected element {selector!r} not found",
                        expectation_key=expectation_key,
                        screenshot_path=_shoot(page, ctx, shot_name))


# ---- S1: every tab renders its key element ----

_TAB_CHECKS = [
    ("/#/dashboard", "text=Watchlist"),          # PositionGrid header
    ("/#/strategy",  "text=Save profile"),
    ("/#/discover",  ".discover-controls"),
    ("/#/brain",     ".brain-title"),
    ("/#/settings",  "text=Alpaca credentials"),
    ("/#/guide",     ".guide"),
]


class TabNavigationSession:
    name = "s1-tabs"
    tier = "live"

    def run(self, page, ctx: SessionContext) -> SessionTrace:
        rec = SessionRecorder(self.name)
        for route, selector in _TAB_CHECKS:
            try:
                page.goto(f"{ctx.base_url.rstrip('/')}{route}",
                          wait_until="networkidle")
                page.wait_for_selector(selector, timeout=_WAIT_MS)
                rec.step(f"{route} renders {selector}", "goto", True)
            except Exception as e:
                rec.step(f"{route} renders {selector}", "goto", False,
                         detail=f"{route}: {selector!r} not rendered ({e})",
                         expectation_key="s1.tab-renders",
                         screenshot_path=_shoot(page, ctx, f"s1-{route.split('/')[-1]}"))
        return rec.finish()


# ---- S6: every affordance the Guide names exists in the DOM ----

class GuideReconciliationSession:
    name = "s6-guide"
    tier = "live"

    def run(self, page, ctx: SessionContext) -> SessionTrace:
        rec = SessionRecorder(self.name)
        for text, route, section in GUIDE_AFFORDANCES:
            try:
                page.goto(f"{ctx.base_url.rstrip('/')}{route}",
                          wait_until="networkidle")
                found = page.locator(f"text={text}").count() > 0
            except Exception:
                found = False
            rec.step(f"Guide names {text!r} on {route}", "assert", found,
                     detail=("" if found else
                             f"Guide {section} names {text!r} but {route} has no "
                             f"such element"),
                     expectation_key="" if found else "s6.affordance-exists",
                     screenshot_path="" if found else _shoot(page, ctx, "s6-" + text.lower().replace(" ", "-")))
        return rec.finish()


LIVE_SESSIONS = [TabNavigationSession(), GuideReconciliationSession()]
EPHEMERAL_SESSIONS: list = []   # filled in Task 6
