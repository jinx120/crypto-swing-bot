from swingbot.backfill_cli import build_parser, config_from_args


def test_parser_reads_ccxt_args():
    args = build_parser().parse_args(
        ["--exchange", "kraken", "--symbols", "BTC/USD,ETH/USD",
         "--timeframes", "15m,1h", "--start", "2023-01-01"])
    cfg = config_from_args(args)
    assert cfg.exchange == "kraken"
    assert cfg.symbols == ["BTC/USD", "ETH/USD"]
    assert cfg.timeframes == ["15m", "1h"]
    assert cfg.history_start == "2023-01-01"


def test_parser_defaults_match_archive_config():
    args = build_parser().parse_args([])
    cfg = config_from_args(args)
    assert cfg.exchange == "binance"
    assert "BTC/USD" in cfg.symbols


def test_csv_args_are_parsed():
    args = build_parser().parse_args(
        ["--csv", "/tmp/x.csv", "--symbol", "BTC/USD",
         "--timeframe", "15m", "--csv-layout", "binance"])
    assert args.csv == "/tmp/x.csv"
    assert args.symbol == "BTC/USD"
    assert args.timeframe == "15m"
    assert args.csv_layout == "binance"
