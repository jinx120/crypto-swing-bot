from __future__ import annotations

import os
import secrets

import uvicorn

from swingbot.credentials import CredentialStore
from swingbot.data.backfill import ArchiveConfig, Backfiller
from swingbot.data.ccxt_provider import CcxtProvider
from swingbot.data.market import MarketData
from swingbot.data.poller import CandlePoller
from swingbot.data.store import CandleStore
from swingbot.discovery import DiscoveryEngine
from swingbot.profiles import ProfileStore
from swingbot.runtime_state import RuntimeStateStore
from swingbot.supervisor import PortfolioSupervisor
from swingbot.web import create_app

HOST = os.environ.get("SWINGBOT_HOST", "127.0.0.1")
DATA_DIR = os.environ.get("SWINGBOT_DATA_DIR", os.path.expanduser("~/.swingbot"))
PORT = int(os.environ.get("SWINGBOT_PORT", "8000"))


def _ensure_token(path: str) -> str:
    env_tok = os.environ.get("SWINGBOT_TOKEN")
    if env_tok:
        return env_tok.strip()
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    tok = secrets.token_urlsafe(24)
    with open(path, "w") as f:
        f.write(tok)
    os.chmod(path, 0o600)
    return tok


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    token = _ensure_token(os.path.join(DATA_DIR, "token"))
    profiles = ProfileStore(os.path.join(DATA_DIR, "swingbot.db"))
    creds = CredentialStore(os.path.join(DATA_DIR, "credentials.json"))
    store = CandleStore(os.path.join(DATA_DIR, "candles.db"))
    archive_cfg = ArchiveConfig()
    archive_provider = CcxtProvider(exchange_id=archive_cfg.exchange,
                                    quote_map=archive_cfg.quote_map,
                                    symbol_overrides=archive_cfg.symbol_overrides)
    backfiller = Backfiller(store, provider=archive_provider)
    market = MarketData(store, creds, data_source=profiles.get_data_source())
    runtime_state = RuntimeStateStore(os.path.join(DATA_DIR, "swingbot.db"))

    from swingbot.managed_profiles import reconcile_managed_profiles
    from swingbot.probe_marker import ProbeMarkerStore

    probe_marker = ProbeMarkerStore(os.path.join(DATA_DIR, "probe_markers.db"))
    enable_probe = os.environ.get("SWINGBOT_ENABLE_PAPER_PROBE") == "1"
    backup_dir = os.path.join(DATA_DIR, "backups")

    def _reconcile_managed():
        reconcile_managed_profiles(
            profiles, enable_probe=enable_probe, mode="paper", backup_dir=backup_dir
        )

    supervisor = PortfolioSupervisor(
        profiles=profiles, creds=creds,
        state_db=os.path.join(DATA_DIR, "swingbot.db"), market=market,
        runtime_state=runtime_state,
        reconcile=_reconcile_managed, probe_marker=probe_marker)
    poller = CandlePoller(market, profiles)        # lifespan owns start/stop
    discovery = DiscoveryEngine(market)

    from swingbot.decision.brain import DecisionBrain
    from swingbot.decision.ollama import OllamaClient
    from swingbot.decision.proposals import IssueLog, ProposalStore
    from swingbot.notify import DiscordNotifier
    from swingbot.discovery import good_history
    from swingbot.strategy_search import _df_from_market, metrics_dict
    from swingbot.backtest import run_backtest
    from swingbot.presets import STYLE, ARCHETYPES, archetype_profile
    from swingbot.profile import StrategyProfile

    def _ollama_factory(settings):
        return OllamaClient(settings.get("brain_ollama_url", "http://localhost:11434"),
                            settings.get("brain_model", "qwen2.5"),
                            float(settings.get("brain_timeout_s", 30)))

    def _backtest_ok(symbol, archetype_key, params):
        try:
            arch = next(a for a in ARCHETYPES if a.key == archetype_key)
            timeframe = STYLE["swing"]["timeframe"]
            profile_dict = archetype_profile(arch, symbol, "swing")
            profile_dict.update(params or {})
            df = _df_from_market(market, symbol, timeframe, 100_000)
            _trades, m = run_backtest(df, StrategyProfile.from_dict(profile_dict))
            return good_history(metrics_dict(m))
        except Exception:
            return False

    notifier = DiscordNotifier(profiles.get_discord_webhook)
    brain = DecisionBrain(
        profiles=profiles, controller=supervisor, ollama_factory=_ollama_factory,
        proposals=ProposalStore(os.path.join(DATA_DIR, "brain_proposals.json")),
        issues=IssueLog(os.path.join(DATA_DIR, "brain_issues.json")),
        notifier=notifier,
        get_discovery=lambda: {},                    # rebound to app.state below
        backtest_ok=_backtest_ok)

    # The dashboard reuses core_engine.backtest; if that package is ever unavailable,
    # degrade gracefully (autodash routes 404) rather than taking the whole app down.
    try:
        from swingbot.autodash import AutoDashConfig, AutoDashboardService
        auto_dashboard = AutoDashboardService(AutoDashConfig.default(), prewarm=True)
    except Exception as exc:
        print(f"[swingbot-web] autodash disabled ({type(exc).__name__}: {exc})")
        auto_dashboard = None

    app = create_app(controller=supervisor, profiles=profiles, creds=creds,
                     token=token, store=store, market=market, backfiller=backfiller,
                     discovery=discovery,
                     discovery_cache_path=os.path.join(DATA_DIR, "discovery.json"),
                     brain=brain,
                     poller=poller, auto_dashboard=auto_dashboard,
                     local_trust=os.environ.get("SWINGBOT_LOCAL_TRUST") == "1")
    brain.get_discovery = lambda: app.state.discovery
    app.state.archive_config = archive_cfg
    print(f"[swingbot-web] token: {token}")
    print(f"[swingbot-web] http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
