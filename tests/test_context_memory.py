from utils.recent_trades import load_recent
import csv


def _write_dummy_trades(csv_path):
    rows = [
        [
            "2025-08-05 09:31:00",
            "SPY",
            "CALL",
            "430",
            "2025-08-05",
            "BUY",
            "1",
            "1.00",
            "100",
            "signal",
            "0",
            "0",
        ],
        [
            "2025-08-05 09:45:00",
            "SPY",
            "CALL",
            "430",
            "2025-08-05",
            "SELL",
            "1",
            "1.20",
            "120",
            "tp",
            "20",
            "20",
        ],
    ]
    with open(csv_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        for r in rows:
            writer.writerow(r)


def test_load_recent(tmp_path):
    csv_path = tmp_path / "trade_log.csv"
    _write_dummy_trades(csv_path)
    # monkeypatch config path
    from utils.llm import load_config  # noqa

    original = load_config()
    original["TRADE_LOG_FILE"] = str(csv_path)

    recent = load_recent(2)
    assert len(recent) == 2
    assert recent[0]["decision"] in {"CALL", "PUT", "NO_TRADE"}
