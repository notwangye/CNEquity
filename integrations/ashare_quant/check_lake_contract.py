"""A-share research bridge smoke check, never a production data approval.

This script is intentionally read-only. It checks CNEquity's public query
contract and makes sample/mock data ineligible for the live research pipeline.
"""
import argparse
import json
from pathlib import Path

CORE = ("daily_bars", "instruments", "trading_status", "trading_calendar")
EXPECTED = {
    "daily_bars": {"symbol", "trade_date", "open", "high", "low", "close",
                   "volume", "amount", "source", "data_version"},
    "instruments": {"symbol", "name", "exchange", "asset_type", "list_date", "delist_date"},
    "trading_status": {"symbol", "trade_date", "is_trading", "risk_warning", "status"},
    "trading_calendar": {"trade_date", "is_trading"},
}


def inspect_contract(data_root, *, allow_sample=False, loader=None):
    if loader is None:
        from cnequity.query import load
        loader = load
    result = {"schema_version": 1, "data_root": str(Path(data_root)),
              "mode": "SYNTHETIC_SMOKE_ONLY" if allow_sample else "REAL_DATA_CONTRACT_CHECK",
              "datasets": {}, "warnings": [],
              "research_allowed": False}
    failures = []
    for dataset in CORE:
        try:
            frame = loader(dataset, data_root=data_root)
            columns = set(frame.columns)
            missing = EXPECTED[dataset] - columns
            if missing:
                raise ValueError("missing required columns: " + ", ".join(sorted(missing)))
            n = len(frame)
            sources = sorted(set(str(v) for v in frame["source"].unique().to_list())) if "source" in columns else []
            result["datasets"][dataset] = {"rows": n, "columns_verified": True,
                                           "sources": sources[:20]}
            if n == 0:
                failures.append(dataset + ": no published rows")
            if dataset == "daily_bars":
                if "mock" in {v.lower() for v in sources}:
                    failures.append("synthetic/mock bars are not research data")
                version = set(str(v) for v in frame["data_version"].unique().to_list())
                if version != {"v2"}:
                    failures.append("daily_bars: unverified volume unit version")
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            result["datasets"][dataset] = {"error": str(exc)[:250]}
            failures.append(dataset + ": could not verify schema or data")
    result["warnings"] = failures
    # Even a complete set of datasets cannot certify PIT ST evidence,
    # a full historical universe, liquidity/fillability, or model alpha.
    result["status"] = "SAMPLE_SMOKE_COMPLETE" if allow_sample and not any(
        "missing required columns" in d.get("error", "") for d in result["datasets"].values()
    ) else "CONTRACT_READABLE_PENDING_PIT_AUDIT" if not failures else "CONTRACT_INCOMPLETE"
    if allow_sample:
        result["warnings"].append("Sample mode is synthetic and explicitly forbidden for research.")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--allow-sample", action="store_true")
    args = p.parse_args()
    result = inspect_contract(args.data_root, allow_sample=args.allow_sample)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("ASHARE_BRIDGE_CONTRACT", result["status"], flush=True)
    if result["status"] == "CONTRACT_INCOMPLETE":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
