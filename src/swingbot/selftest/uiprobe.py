from __future__ import annotations

import os

from swingbot.selftest import UIFinding

ROUTES = ["/", "/discover", "/brain"]


class UIProbe:
    def __init__(self, base_url: str, screenshot_dir: str):
        self.base_url = base_url.rstrip("/")
        self.screenshot_dir = screenshot_dir

    def probe_route(self, route: str, page) -> list[UIFinding]:
        findings: list[UIFinding] = []
        shot_name = route.strip("/") or "index"
        shot_path = os.path.join(self.screenshot_dir, f"{shot_name}.png")

        def on_console(msg):
            if msg.type == "error":
                findings.append(UIFinding(route=route, severity="warn", kind="console",
                                          detail=msg.text, screenshot_path=""))
            elif msg.type == "warning":
                findings.append(UIFinding(route=route, severity="info", kind="console",
                                          detail=msg.text, screenshot_path=""))

        def on_pageerror(exc):
            findings.append(UIFinding(route=route, severity="fatal", kind="exception",
                                      detail=str(exc), screenshot_path=""))

        def on_response(resp):
            if resp.status >= 500:
                findings.append(UIFinding(route=route, severity="fatal", kind="network",
                                          detail=f"HTTP {resp.status} {resp.url}",
                                          screenshot_path=""))
            elif resp.status >= 400:
                findings.append(UIFinding(route=route, severity="warn", kind="network",
                                          detail=f"HTTP {resp.status} {resp.url}",
                                          screenshot_path=""))

        page.on("console", on_console)
        page.on("pageerror", on_pageerror)
        page.on("response", on_response)

        try:
            page.goto(f"{self.base_url}{route}", wait_until="networkidle")
        except Exception as e:
            findings.append(UIFinding(route=route, severity="fatal", kind="exception",
                                      detail=f"navigation failed: {e}", screenshot_path=""))

        try:
            page.screenshot(path=shot_path, full_page=True)
        except Exception:
            pass

        for f in findings:
            if not f.screenshot_path:
                f.screenshot_path = shot_path

        return findings

    def run(self, page_factory) -> list[UIFinding]:
        all_findings: list[UIFinding] = []
        for route in ROUTES:
            page = page_factory()
            all_findings.extend(self.probe_route(route, page))
        return all_findings
