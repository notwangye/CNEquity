"""Offline unit tests for the real-lake readback quality gate."""
import importlib.util
from pathlib import Path
import unittest

import pandas as pd


FILE = Path(__file__).with_name("e2e_validate_lake.py")
SPEC = importlib.util.spec_from_file_location("cne_lake_e2e", FILE)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class Frame:
    def __init__(self, data):
        self.data = data
    def to_pandas(self):
        return self.data.copy()


def sample(source="tdx_protocol", *, target=True):
    days = pd.bdate_range("2026-09-28", periods=25)
    dates = [str(d.date()) for d in days]
    last = dates[-1]
    rows = []
    status = []
    for symbol in ("600519.SH", "000001.SZ"):
        for date in dates:
            rows.append({"symbol": symbol, "trade_date": date,
                         "open": 10.0, "high": 10.5, "low": 9.5,
                         "close": 10.0, "volume": 100000,
                         "amount": 1000000, "source": source,
                         "data_version": "v2"})
            status.append({"symbol": symbol, "trade_date": date,
                           "is_trading": True, "risk_warning": False,
                           "status": "normal"})
    if not target:
        last = "2026-11-04"
    datasets = {
        "daily_bars": pd.DataFrame(rows),
        "instruments": pd.DataFrame([
            {"symbol": symbol, "asset_type": "stock", "list_date": "2000-01-01"}
            for symbol in ("600519.SH", "000001.SZ")
        ]),
        "trading_calendar": pd.DataFrame({
            "trade_date": dates, "is_trading": [True] * len(dates)
        }),
        "trading_status": pd.DataFrame(status),
    }
    return datasets, last


def run(datasets, date):
    def loader(name, **kwargs):
        return Frame(datasets[name])
    return module.validate_lake("/isolated", ["600519.SH", "000001.SZ"],
                                target_date=date, loader=loader)


class LakeE2EValidatorTests(unittest.TestCase):
    def test_real_readback_passes_but_research_not_approved(self):
        datasets, date = sample()
        result = run(datasets, date)
        self.assertEqual(result["status"], "REAL_DEMO_BARS_READBACK_PASSED_NOT_FULL_UNIVERSE")
        self.assertFalse(result["historical_universe_approved"])
        self.assertFalse(result["strategy_approved"])
        self.assertEqual(result["bars"]["historical_status_coverage"], 1)

    def test_mock_source_is_rejected(self):
        datasets, date = sample("mock")
        self.assertIn("BANNED_OR_MISSING_SOURCE", run(datasets, date)["errors"])

    def test_baostock_source_is_rejected(self):
        datasets, date = sample("baostock")
        self.assertIn("BANNED_OR_MISSING_SOURCE", run(datasets, date)["errors"])

    def test_wrong_target_day_rejected(self):
        datasets, date = sample(target=False)
        result = run(datasets, date)
        self.assertTrue(any(x.startswith("MISSING_TARGET_DATE:")
                            for x in result["errors"]))

    def test_broken_price_geometry_rejected(self):
        datasets, date = sample()
        datasets["daily_bars"].loc[0, "high"] = 1
        self.assertIn("INVALID_DAILY_OHLCV", run(datasets, date)["errors"])

    def test_unknown_st_is_not_evidence(self):
        datasets, date = sample()
        datasets["trading_status"].loc[0, "risk_warning"] = None
        result = run(datasets, date)
        self.assertLess(result["bars"]["historical_status_coverage"], 1)
        self.assertFalse(result["historical_universe_approved"])

    def test_duplicate_bars_rejected(self):
        datasets, date = sample()
        frame = datasets["daily_bars"]
        datasets["daily_bars"] = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
        self.assertIn("DUPLICATE_OR_BAD_DATES", run(datasets, date)["errors"])


if __name__ == "__main__":
    unittest.main()
