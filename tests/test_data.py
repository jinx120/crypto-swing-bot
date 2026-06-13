
from swingbot.data.historical import load_csv, REQUIRED_COLUMNS


def test_load_csv_returns_sorted_typed_frame(tmp_path):
    csv = tmp_path / "trx.csv"
    csv.write_text(
        "ts,open,high,low,close,volume\n"
        "2026-01-01T00:15:00Z,2,3,1,2,100\n"
        "2026-01-01T00:00:00Z,1,2,0.5,1,50\n"
    )
    df = load_csv(str(csv))
    assert list(df.columns) == REQUIRED_COLUMNS
    assert df["ts"].is_monotonic_increasing                # sorted ascending
    assert str(df["ts"].dt.tz) == "UTC"
    assert df["close"].dtype == float

def test_load_csv_rejects_missing_columns(tmp_path):
    csv = tmp_path / "bad.csv"
    csv.write_text("ts,open\n2026-01-01T00:00:00Z,1\n")
    try:
        load_csv(str(csv))
        assert False, "expected ValueError"
    except ValueError as e:
        assert "missing columns" in str(e).lower()
