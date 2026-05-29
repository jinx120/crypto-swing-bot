from swingbot.exits import bracket_levels


def test_bracket_levels():
    stop, tp = bracket_levels(entry_price=100.0, atr=2.0, stop_mult=1.5, tp_mult=2.0)
    assert abs(stop - 97.0) < 1e-9     # 100 - 1.5*2
    assert abs(tp - 104.0) < 1e-9      # 100 + 2.0*2
