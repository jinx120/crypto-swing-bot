from swingbot.sizing import position_size


def test_risk_based_size():
    # equity 1000, risk 1% => $10 risk; stop distance $0.005 => 2000 units
    qty = position_size(equity=1000, risk_per_trade=0.01, stop_distance=0.005,
                        price=0.10, max_position_frac=1.0)
    assert abs(qty - 2000) < 1e-6

def test_position_cap_clamps_size():
    # uncapped would be huge; cap at 25% of 1000 = $250 / $0.10 = 2500 units
    qty = position_size(equity=1000, risk_per_trade=0.5, stop_distance=0.0001,
                        price=0.10, max_position_frac=0.25)
    assert abs(qty - 2500) < 1e-6

def test_zero_stop_distance_returns_zero():
    assert position_size(1000, 0.01, 0.0, 0.10, 0.25) == 0.0
