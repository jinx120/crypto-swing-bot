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
    # "Save profile" lives inside a collapsed <details>; use the always-visible
    # manual-form toggle as the strategy tab's key element.
    ("/#/strategy",  "text=Advanced — hand-tune a profile"),
    ("/#/discover",  ".discover-controls"),
    ("/#/brain",     ".brain-title"),
    ("/#/settings",  "text=Alpaca credentials"),
    ("/#/health",    "text=Last usage-agent run"),
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


def _api_step(rec: SessionRecorder, ctx: SessionContext, desc: str, method: str,
              path: str, body=None, ok_when=lambda st, js: st == 200,
              expectation_key: str = "") -> tuple[bool, dict]:
    try:
        st, js = ctx.api(method, path, body)
    except Exception as e:
        return rec.step(desc, "api", False, detail=f"{method} {path}: {e}",
                        expectation_key=expectation_key), {}
    ok = bool(ok_when(st, js))
    return rec.step(desc, "api", ok,
                    detail="" if ok else f"{method} {path} -> {st} {str(js)[:200]}",
                    expectation_key="" if ok else expectation_key), js


# ---- S2: Guide's "5 steps" — build, (gated) backtest, arm, see it trading ----

class GuidedStrategyFlowSession:
    name = "s2-strategy-flow"
    tier = "ephemeral"
    PROFILE_NAME = "agent-s2-btc"

    def run(self, page, ctx: SessionContext) -> SessionTrace:
        rec = SessionRecorder(self.name)
        ok, presets = _api_step(rec, ctx, "list presets", "GET", "/api/presets")
        if not ok or not presets:
            return rec.finish()
        profile = dict(presets[0]["profile"])
        profile["symbol"] = "BTC/USD"

        # Ephemeral app has no Alpaca creds: the Guide documents the exact
        # error this must produce (Guide §Step 2).
        _api_step(rec, ctx, "backtest without creds gives documented error",
                  "POST", "/api/strategy/backtest", {"profile": profile},
                  ok_when=lambda st, js: st == 400 and
                  "credentials" in str(js.get("detail", "")).lower(),
                  expectation_key="s2.backtest-needs-creds")

        _api_step(rec, ctx, "save preset-based profile", "POST", "/api/profiles",
                  {"name": self.PROFILE_NAME, "profile": profile},
                  expectation_key="s2.save-profile")
        _api_step(rec, ctx, "arm the profile", "POST", "/api/strategies/arm",
                  {"name": self.PROFILE_NAME},
                  expectation_key="s2.arm-strategy")
        _api_step(rec, ctx, "strategy lists as armed", "GET", "/api/strategies",
                  ok_when=lambda st, js: st == 200 and any(
                      r.get("name") == self.PROFILE_NAME and r.get("armed")
                      for r in js),
                  expectation_key="s2.arm-strategy")

        if _goto(page, rec, ctx, "/#/dashboard", "s2.dashboard-shows-armed"):
            _wait(page, rec, ctx, "/#/dashboard", "text=BTC/USD",
                  "s2.dashboard-shows-armed", "s2-dashboard")
        return rec.finish()


# ---- S3: watchlist round-trip ----

class WatchlistRoundTripSession:
    name = "s3-watchlist"
    tier = "ephemeral"

    def run(self, page, ctx: SessionContext) -> SessionTrace:
        rec = SessionRecorder(self.name)
        ok, before = _api_step(rec, ctx, "read watchlist", "GET", "/api/watchlist",
                               expectation_key="s3.watchlist-roundtrip")
        if not ok:
            return rec.finish()
        base = list(before.get("symbols") or [])
        _api_step(rec, ctx, "add ETH/USD", "PUT", "/api/watchlist",
                  {"symbols": base + ["ETH/USD"]},
                  ok_when=lambda st, js: st == 200 and "ETH/USD" in js.get("symbols", []),
                  expectation_key="s3.watchlist-roundtrip")
        if _goto(page, rec, ctx, "/#/dashboard", "s3.watchlist-roundtrip"):
            _wait(page, rec, ctx, "/#/dashboard", "text=ETH/USD",
                  "s3.watchlist-roundtrip", "s3-watchlist")
        _api_step(rec, ctx, "restore watchlist", "PUT", "/api/watchlist",
                  {"symbols": base},
                  ok_when=lambda st, js: st == 200 and js.get("symbols") == base,
                  expectation_key="s3.watchlist-roundtrip")
        return rec.finish()


# ---- S4: portfolio settings persistence ----

class SettingsPersistenceSession:
    name = "s4-settings"
    tier = "ephemeral"

    def run(self, page, ctx: SessionContext) -> SessionTrace:
        rec = SessionRecorder(self.name)
        ok, before = _api_step(rec, ctx, "read settings", "GET",
                               "/api/portfolio/settings",
                               expectation_key="s4.settings-persist")
        if not ok:
            return rec.finish()
        old = before.get("max_concurrent", 5)
        new = old + 2
        _api_step(rec, ctx, f"set max_concurrent={new}", "PUT",
                  "/api/portfolio/settings", {"max_concurrent": new},
                  ok_when=lambda st, js: st == 200 and js.get("max_concurrent") == new,
                  expectation_key="s4.settings-persist")
        _api_step(rec, ctx, "re-read shows persisted value", "GET",
                  "/api/portfolio/settings",
                  ok_when=lambda st, js: st == 200 and js.get("max_concurrent") == new,
                  expectation_key="s4.settings-persist")
        _api_step(rec, ctx, "restore", "PUT", "/api/portfolio/settings",
                  {"max_concurrent": old},
                  ok_when=lambda st, js: st == 200 and js.get("max_concurrent") == old,
                  expectation_key="s4.settings-persist")
        return rec.finish()


# ---- S5: brain inbox flow ----

def _seed_rows(archetype_key: str) -> list[dict]:
    base = {"created_at": 1, "rationale": "agent seed", "confidence": 0.9,
            "status": "pending", "applied_at": None, "source": "usage-agent"}
    return [
        {**base, "id": "agent-s5-arm", "action": "arm",
         "target": {"symbol": "BTC/USD", "archetype": archetype_key},
         "guardrail_status": "approved", "guardrail_reason": ""},
        {**base, "id": "agent-s5-tune", "action": "tune",
         "target": {"symbol": "BTC/USD", "archetype": archetype_key,
                    "params": {"entry_threshold": 0.5}},
         "guardrail_status": "blocked",
         "guardrail_reason": "guardrail-test-reason"},
        {**base, "id": "agent-s5-uifix", "action": "ui_fix",
         "target": {"route": "/#/dashboard", "issue": "agent seed"},
         "guardrail_status": "approved", "guardrail_reason": ""},
    ]


class BrainInboxSession:
    name = "s5-brain-inbox"
    tier = "ephemeral"

    def run(self, page, ctx: SessionContext) -> SessionTrace:
        rec = SessionRecorder(self.name)
        ok, presets = _api_step(rec, ctx, "list presets", "GET", "/api/presets")
        if not ok or not presets:
            return rec.finish()
        arch = presets[0]["key"]

        if ctx.seed_proposals is None:
            rec.step("seed proposals", "api", False,
                     detail="no seed_proposals hook on context")
            return rec.finish()
        ctx.seed_proposals(_seed_rows(arch))
        rec.step("seed 3 proposals into inbox", "api", True)

        _api_step(rec, ctx, "inbox shows seeded proposals", "GET",
                  "/api/brain/proposals",
                  ok_when=lambda st, js: st == 200 and
                  {"agent-s5-arm", "agent-s5-tune", "agent-s5-uifix"} <=
                  {p.get("id") for p in js},
                  expectation_key="s5.apply-approved-arm")
        _api_step(rec, ctx, "apply approved arm", "POST",
                  "/api/brain/proposals/agent-s5-arm/apply",
                  ok_when=lambda st, js: st == 200 and js.get("ok"),
                  expectation_key="s5.apply-approved-arm")
        _api_step(rec, ctx, "applied arm armed the strategy", "GET",
                  "/api/strategies",
                  ok_when=lambda st, js: st == 200 and any(
                      r.get("name", "").startswith("disc-btcusd") and r.get("armed")
                      for r in js),
                  expectation_key="s5.apply-approved-arm")
        _api_step(rec, ctx, "dismiss blocked tune", "POST",
                  "/api/brain/proposals/agent-s5-tune/dismiss",
                  ok_when=lambda st, js: st == 200 and js.get("ok"),
                  expectation_key="s5.dismiss-leaves-others")
        _api_step(rec, ctx, "ui_fix still pending after dismiss", "GET",
                  "/api/brain/proposals",
                  ok_when=lambda st, js: st == 200 and any(
                      p.get("id") == "agent-s5-uifix" and p.get("status") == "pending"
                      for p in js),
                  expectation_key="s5.dismiss-leaves-others")

        if _goto(page, rec, ctx, "/#/brain", "s5.blocked-shows-reason"):
            _wait(page, rec, ctx, "/#/brain", "text=guardrail-test-reason",
                  "s5.blocked-shows-reason", "s5-brain")
            apply_buttons = 0
            try:
                apply_buttons = page.locator('button:has-text("Apply")').count()
            except Exception:
                pass
            rec.step("no Apply button for non-executable proposals", "assert",
                     apply_buttons == 0,
                     detail="" if apply_buttons == 0 else
                     f"{apply_buttons} Apply button(s) rendered for "
                     f"ui_fix/blocked proposals",
                     expectation_key="" if apply_buttons == 0 else "s5.ui-fix-no-apply",
                     screenshot_path="" if apply_buttons == 0 else _shoot(page, ctx, "s5-apply-dead-end"))
        return rec.finish()


LIVE_SESSIONS = [TabNavigationSession(), GuideReconciliationSession()]
EPHEMERAL_SESSIONS = [GuidedStrategyFlowSession(), WatchlistRoundTripSession(),
                      SettingsPersistenceSession(), BrainInboxSession()]
