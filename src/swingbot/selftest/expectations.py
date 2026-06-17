from __future__ import annotations

from dataclasses import dataclass

_ROADMAP_SPEC = "docs/superpowers/specs/2026-06-02-platform-improvement-roadmap-design.md"
_C_SPEC = "docs/superpowers/specs/2026-06-04-subproject-c-decision-brain-design.md"
_D_SPEC = "docs/superpowers/specs/2026-06-03-subproject-d-self-test-gate-design.md"
_GUIDE = "frontend/src/guide.md"


@dataclass(frozen=True)
class Expectation:
    key: str
    session: str
    expected: str        # the documented claim, human-readable
    doc: str             # repo-relative path of the source document
    section: str         # '§"Section name"'
    fix_bias: str = "ui"  # when violated: "doc" -> doc_fix proposal, "ui" -> ui_fix


def _e(key, session, expected, doc, section, fix_bias="ui"):
    return Expectation(key, session, expected, doc, section, fix_bias)


EXPECTATIONS: dict[str, Expectation] = {e.key: e for e in [
    # S1 — tab navigation
    _e("s1.tab-renders", "s1-tabs",
       "every nav tab renders its key element with no console errors",
       _ROADMAP_SPEC, '§"Sub-project A"'),
    # S2 — guided strategy flow
    _e("s2.backtest-needs-creds", "s2-strategy-flow",
       "backtest without Alpaca credentials returns the documented "
       "'set Alpaca credentials in Settings first' error",
       _GUIDE, '§"Step 2 — Connect your Alpaca account (paper)"', "doc"),
    _e("s2.save-profile", "s2-strategy-flow",
       "a valid preset-based profile saves via POST /api/profiles",
       _GUIDE, '§"Step 3 — Build a strategy profile"'),
    _e("s2.arm-strategy", "s2-strategy-flow",
       "arming a saved profile succeeds and it lists as armed",
       _GUIDE, '§"The 5 steps to start trading"', "doc"),
    _e("s2.dashboard-shows-armed", "s2-strategy-flow",
       "an armed strategy appears on the Dashboard grid (no 'No strategies "
       "armed' empty state)",
       _ROADMAP_SPEC, '§"Sub-project A"'),
    # S3 — watchlist round-trip
    _e("s3.watchlist-roundtrip", "s3-watchlist",
       "a symbol added to the watchlist appears in the Dashboard watchlist "
       "row and removal restores the original list",
       _ROADMAP_SPEC, '§"Sub-project A"'),
    # S4 — settings persistence
    _e("s4.settings-persist", "s4-settings",
       "PUT /api/portfolio/settings persists max_concurrent and serves it back",
       _C_SPEC, '§"Configuration"'),
    # S5 — brain inbox
    _e("s5.apply-approved-arm", "s5-brain-inbox",
       "applying an approved arm proposal arms the strategy",
       _C_SPEC, '§"Frontend"'),
    _e("s5.dismiss-leaves-others", "s5-brain-inbox",
       "dismissing a proposal marks it dismissed and leaves others pending",
       _C_SPEC, '§"Frontend"'),
    _e("s5.blocked-shows-reason", "s5-brain-inbox",
       "a blocked proposal card shows its guardrail reason",
       _C_SPEC, '§"Frontend"'),
    _e("s5.ui-fix-no-apply", "s5-brain-inbox",
       "non-executable proposals (ui_fix/doc_fix) show no Apply button",
       _D_SPEC, '§"New action type"'),
    # S6 — guide reconciliation (one key; per-affordance detail in the step)
    _e("s6.affordance-exists", "s6-guide",
       "every UI control the Guide names exists in the rendered DOM",
       _GUIDE, '§"The 5 steps to start trading"', "doc"),
]}


# (visible text, hash route, guide section) — S6 checks each renders in the DOM.
# Keep this list in sync with frontend/src/guide.md.
GUIDE_AFFORDANCES: list[tuple[str, str, str]] = [
    ("Save profile",     "/#/strategy",  '§"Step 3 — Build a strategy profile"'),
    ("Arm",              "/#/strategy",  '§"Step 4 — Arm the profile"'),
    ("Save credentials", "/#/settings",  '§"Step 2 — Connect your Alpaca account (paper)"'),
    # Start/Stop is one toggle button; its label depends on running state.
    ("Start bot | Stop bot", "/#/dashboard", '§"Step 5 — Start the bot"'),
    ("HALT",             "/#/dashboard", '§"Controls reference"'),
    ("Flatten",          "/#/dashboard", '§"Controls reference"'),
]
