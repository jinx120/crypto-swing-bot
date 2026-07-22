from swingbot.autotuner import AutoTuner


def test_normal_tier_is_baseline():
    d = AutoTuner().decide("Moderate", dd_24h=0.0, dd_7d=0.0)
    assert d.tier == 0
    assert d.defensive is False
    assert d.status == ""
    assert d.params["max_position_frac"] == 0.10
    assert d.params["entry_threshold"] == 0.50


def test_tighten_on_24h_drawdown():
    d = AutoTuner().decide("Moderate", dd_24h=0.04, dd_7d=0.0)
    assert d.tier == 1
    assert d.defensive is True
    assert round(d.params["max_position_frac"], 4) == 0.07  # 0.10 * 0.7
    assert round(d.params["entry_threshold"], 4) == 0.60  # 0.50 * 1.2
    assert d.params["max_concurrent"] == 1  # 2 - 1
    assert "Defensive" in d.status


def test_suspend_on_7d_drawdown():
    d = AutoTuner().decide("Aggressive", dd_24h=0.10, dd_7d=0.09)
    assert d.tier == 2
    assert d.params["entry_threshold"] >= 999.0  # no new entries pass
    assert d.params["max_concurrent"] == 3  # 4 - 1
    assert d.defensive is True


def test_hysteresis_holds_tier_until_recovered():
    tuner = AutoTuner()
    # still 2% down in 24h -> stays tightened even though below the 3% trigger
    d = tuner.decide("Moderate", dd_24h=0.02, dd_7d=0.02, current_tier=1)
    assert d.tier == 1
    # recovered below 1% -> relaxes to baseline
    d2 = tuner.decide("Moderate", dd_24h=0.005, dd_7d=0.01, current_tier=1)
    assert d2.tier == 0


def test_max_concurrent_floor_is_one():
    d = AutoTuner().decide("Conservative", dd_24h=0.05, dd_7d=0.0)
    assert d.params["max_concurrent"] == 1
