
from swingbot.data.series_store import SeriesStore


def _store(tmp_path):
    return SeriesStore(str(tmp_path / "series.db"))


def test_upsert_then_get_df_returns_utc_timestamps_oldest_first(tmp_path):
    s = _store(tmp_path)
    assert s.upsert("funding_8h", "BTC/USD", [(1700000000, 0.0004),
                                              (1699999000, 0.0001)]) == 2
    df = s.get_df("funding_8h", "BTC/USD")
    assert list(df.columns) == ["ts", "value"]
    assert df["ts"].is_monotonic_increasing
    assert str(df["ts"].dt.tz) == "UTC"
    assert df["value"].tolist() == [0.0001, 0.0004]


def test_upsert_is_idempotent_on_the_same_timestamp(tmp_path):
    s = _store(tmp_path)
    s.upsert("funding_8h", "BTC/USD", [(1700000000, 0.0004)])
    s.upsert("funding_8h", "BTC/USD", [(1700000000, 0.0009)])
    df = s.get_df("funding_8h", "BTC/USD")
    assert len(df) == 1
    assert df["value"].iloc[0] == 0.0009  # last write wins, no duplicate row


def test_series_are_isolated_by_name_and_symbol(tmp_path):
    s = _store(tmp_path)
    s.upsert("funding_8h", "BTC/USD", [(1, 0.1)])
    s.upsert("cb_premium", "BTC/USD", [(1, 0.2)])
    s.upsert("funding_8h", "ETH/USD", [(1, 0.3)])
    assert s.get_df("funding_8h", "BTC/USD")["value"].tolist() == [0.1]
    assert s.get_df("cb_premium", "BTC/USD")["value"].tolist() == [0.2]
    assert s.get_df("funding_8h", "ETH/USD")["value"].tolist() == [0.3]


def test_get_df_honours_the_time_bounds(tmp_path):
    s = _store(tmp_path)
    s.upsert("f", "BTC/USD", [(100, 1.0), (200, 2.0), (300, 3.0)])
    assert s.get_df("f", "BTC/USD", start_ts=200)["value"].tolist() == [2.0, 3.0]
    assert s.get_df("f", "BTC/USD", end_ts=200)["value"].tolist() == [1.0, 2.0]
    assert s.get_df("f", "BTC/USD", start_ts=200, end_ts=200)["value"].tolist() == [2.0]


def test_get_df_on_an_unknown_series_returns_an_empty_typed_frame(tmp_path):
    df = _store(tmp_path).get_df("nope", "BTC/USD")
    assert df.empty
    assert list(df.columns) == ["ts", "value"]


def test_coverage_reports_bounds_and_count(tmp_path):
    s = _store(tmp_path)
    s.upsert("f", "BTC/USD", [(100, 1.0), (300, 3.0)])
    assert s.coverage("f", "BTC/USD") == {"min_ts": 100, "max_ts": 300, "count": 2}
    assert s.coverage("f", "ETH/USD") == {"min_ts": None, "max_ts": None, "count": 0}


def test_upsert_of_nothing_writes_nothing(tmp_path):
    assert _store(tmp_path).upsert("f", "BTC/USD", []) == 0


def test_names_lists_stored_series(tmp_path):
    s = _store(tmp_path)
    s.upsert("funding_8h", "BTC/USD", [(1, 0.1)])
    s.upsert("cb_premium", "BTC/USD", [(1, 0.2)])
    assert sorted(n["name"] for n in s.names()) == ["cb_premium", "funding_8h"]
