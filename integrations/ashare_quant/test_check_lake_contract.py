"""Offline contract tests; never access a live data provider."""
import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).with_name("check_lake_contract.py")
SPEC = importlib.util.spec_from_file_location("ashare_contract", MODULE)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class Column(list):
    def unique(self):
        return self

    def to_list(self):
        return list(self)


class FakeFrame:
    def __init__(self, columns, rows=1, *, sources=None, versions=None):
        self.columns = list(columns)
        self.rows = rows
        self.sources = sources or ["tdx"]
        self.versions = versions or ["v2"]

    def __len__(self):
        return self.rows

    def __getitem__(self, item):
        return Column(self.sources if item == "source" else self.versions)


def frames(*, source="tdx", version="v2"):
    return {
        dataset: FakeFrame(fields, sources=[source], versions=[version])
        for dataset, fields in mod.EXPECTED.items()
    }


class ContractTests(unittest.TestCase):
    def test_real_schema_still_requires_historical_audit(self):
        data = frames()
        result = mod.inspect_contract("/tmp/isolated", loader=lambda key, **_: data[key])
        self.assertEqual(result["status"], "CONTRACT_READABLE_PENDING_PIT_AUDIT")
        self.assertFalse(result["research_allowed"])

    def test_mock_never_approved_for_live_research(self):
        data = frames(source="mock")
        result = mod.inspect_contract("/tmp/sample", allow_sample=True,
                                      loader=lambda key, **_: data[key])
        self.assertEqual(result["status"], "SAMPLE_SMOKE_COMPLETE")
        self.assertFalse(result["research_allowed"])
        self.assertTrue(any("mock" in error for error in result["warnings"]))

    def test_empty_sample_fails_even_if_columns_exist(self):
        data = frames()
        data["daily_bars"].rows = 0
        result = mod.inspect_contract("/tmp/sample", allow_sample=True,
                                      loader=lambda key, **_: data[key])
        self.assertEqual(result["status"], "CONTRACT_INCOMPLETE")

    def test_old_volume_unit_fails(self):
        data = frames(version="v1")
        result = mod.inspect_contract("/tmp/isolated", loader=lambda key, **_: data[key])
        self.assertEqual(result["status"], "CONTRACT_INCOMPLETE")
        self.assertTrue(any("volume unit" in x for x in result["warnings"]))

    def test_missing_status_schema_fails(self):
        data = frames()
        data["trading_status"] = FakeFrame({"symbol", "trade_date"})
        result = mod.inspect_contract("/tmp/isolated", loader=lambda key, **_: data[key])
        self.assertEqual(result["status"], "CONTRACT_INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
