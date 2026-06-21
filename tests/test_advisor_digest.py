from swingbot.advisor.digest import build_digest


def test_digest_computes_win_rate_and_passes_params():
    raw = {
        "BTC/USD": {
            "trades": 10,
            "wins": 6,
            "losses": 4,
            "avg_win": 1.5,
            "avg_loss": -1.0,
            "drawdown": -0.03,
            "params": {"threshold_pct": 0.0075, "tp_pct": 0.015, "sl_pct": 0.01},
            "weight": 0.5,
            "equity_curve": [100, 101, 99, 103],
        }
    }
    digest = build_digest(raw)
    assert digest["BTC/USD"]["win_rate"] == 0.6
    assert digest["BTC/USD"]["params"]["tp_pct"] == 0.015
    assert digest["BTC/USD"]["drawdown"] == -0.03


def test_digest_zero_trades_is_safe():
    digest = build_digest(
        {
            "ETH/USD": {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "drawdown": 0,
                "params": {},
                "weight": 0,
                "equity_curve": [],
            }
        }
    )
    assert digest["ETH/USD"]["win_rate"] == 0.0
