from datetime import datetime, timezone

from swingbot.profiles import ProfileStore
from swingbot.supervisor import PortfolioSupervisor


def _sup(tmp_path):
    profiles = ProfileStore(str(tmp_path / "swingbot.db"))
    profiles.save(
        "kronos-btc-usd",
        {
            "symbol": "BTC/USD",
            "signals": {"kronos_forecast": {"weight": 1.0}},
            "entry_threshold": 0.50,
            "max_position_frac": 0.10,
            "max_concurrent": 2,
        },
    )
    profiles.arm("kronos-btc-usd")
    profiles.set_risk_level("Moderate")
    sup = PortfolioSupervisor(
        profiles=profiles,
        creds=None,
        state_db=str(tmp_path / "swingbot.db"),
    )
    return sup, profiles


def test_autotune_tightens_armed_profiles_on_drawdown(tmp_path):
    sup, profiles = _sup(tmp_path)
    now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    # Seed an equity dip: 24h peak 10000 -> current 9600 (4% down).
    from datetime import timedelta

    sup._equity_snapshots.record(10000.0, now - timedelta(hours=10))
    sup._equity_snapshots.record(9600.0, now - timedelta(minutes=1))
    sup._maybe_autotune(now)
    p = profiles.get("kronos-btc-usd")
    assert round(p["max_position_frac"], 4) == 0.07
    assert round(p["entry_threshold"], 4) == 0.60
    assert profiles.get_meta("autotuner_tier") == "1"
    assert sup._defensive_mode is True


def test_summary_exposes_defensive_flag(tmp_path):
    sup, _ = _sup(tmp_path)
    sup._defensive_mode = True
    sup._autotuner_status = "Defensive mode -- recovering from recent losses."
    summary = sup._build_summary({"equity": 10000.0})
    assert summary["defensive"] is True
    assert "Defensive" in summary["autotuner_status"]
