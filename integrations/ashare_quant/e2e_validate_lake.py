"""End-to-end readback audit of an EXISTING CNEquity data lake.

No ingestion, no network requests, no backups and no brokerage actions.
Validates actual curated bytes through CNEquity's public query.load API
after ingestion in a fresh Python process. Demo scope is never all-market
or PIT/ST approved even when the live bars themselves pass.
"""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from cnequity.query import load


def validate_lake(data_root, expected_symbols, *, require_real=True, target_date=None,
                  min_sessions=20, loader=None):
    result = {"status": "FAIL", "data_root": str(data_root),
              "target_date": target_date,
              "requested_symbols": expected_symbols, "bars": {}, "coverage": {},
              "errors": [], "historical_universe_approved": False,
              "strategy_approved": False, "provider_live_bars_verified": False,
              "strategy_blockers": []}
    if not expected_symbols or len(set(expected_symbols)) != len(expected_symbols):
        raise ValueError("Require distinct explicit symbols")
    if type(min_sessions) is not int or min_sessions < 2:
        raise ValueError("Invalid minimum trading sessions")
    if target_date is not None:
        try:
            day = pd.Timestamp(target_date).normalize()
        except (ValueError, TypeError):
            raise ValueError("Invalid target date") from None
        if pd.isna(day) or day.strftime("%Y-%m-%d") != target_date:
            raise ValueError("Invalid target date")
    reader = loader or load
    bars = reader("daily_bars", data_root=data_root, symbols=expected_symbols,
                adjust=None).to_pandas()
    instruments = reader("instruments", data_root=data_root).to_pandas()
    calendar = reader("trading_calendar", data_root=data_root).to_pandas()
    if bars.empty:
        result["errors"].append("NO_PUBLISHED_DAILY_BARS")
        return result
    required = {"symbol", "trade_date", "open", "high", "low", "close",
                "volume", "amount", "source", "data_version"}
    if not required.issubset(bars.columns):
        result["errors"].append("MISSING_BAR_COLUMNS")
        return result
    if not {"symbol", "asset_type", "list_date"}.issubset(instruments.columns):
        result["errors"].append("MISSING_INSTRUMENT_COLUMNS")
    else:
        if instruments["symbol"].duplicated().any():
            result["errors"].append("DUPLICATE_INSTRUMENTS")
        for symbol in expected_symbols:
            listing = instruments.loc[instruments["symbol"].eq(symbol)]
            if len(listing) != 1 or str(listing.iloc[0]["asset_type"]).lower() != "stock":
                result["errors"].append("MISSING_OR_WRONG_INSTRUMENT:" + symbol)
    if not {"trade_date", "is_trading"}.issubset(calendar.columns):
        result["errors"].append("MISSING_CALENDAR_COLUMNS")
        return result
    dates = pd.to_datetime(bars.trade_date, errors="coerce").dt.normalize()
    cal_dates = pd.to_datetime(calendar.trade_date, errors="coerce").dt.normalize()
    if (dates.isna().any() or cal_dates.isna().any()
            or calendar.trade_date.duplicated().any()
            or bars.duplicated(["symbol", "trade_date"]).any()):
        result["errors"].append("DUPLICATE_OR_BAD_DATES")
    # False/unknown calendar rows are not admissible as trading sessions.
    def parse_flag(x):
        if hasattr(x, "item") and not isinstance(x, str):
            x = x.item()
        if isinstance(x, bool):
            return x
        if isinstance(x, int) and x in (0, 1):
            return bool(x)
        if isinstance(x, str) and x.strip().lower() in {"true", "false", "1", "0"}:
            return x.strip().lower() in {"true", "1"}
        return None
    cal_flags = calendar.is_trading.map(parse_flag)
    trading_dates = set()
    if cal_flags.isna().any():
        result["errors"].append("UNKNOWN_CALENDAR_FLAG")
    else:
        trading_dates = set(cal_dates.loc[cal_flags].tolist())
        if not set(dates.tolist()).issubset(trading_dates):
            result["errors"].append("BARS_ON_NONTRADING_DATES")
    numeric = bars[["open", "high", "low", "close", "volume", "amount"]].apply(
        pd.to_numeric, errors="coerce")
    traded = numeric.volume.gt(0)
    if (numeric.isna().any().any()
            or numeric[["volume", "amount"]].lt(0).any().any()
            or numeric.loc[traded, ["open", "high", "low", "close"]].le(0).any().any()
            or numeric.loc[traded, "high"].lt(
                numeric.loc[traded, ["open", "close", "low"]].max(axis=1)).any()
            or numeric.loc[traded, "low"].gt(
                numeric.loc[traded, ["open", "close", "high"]].min(axis=1)).any()):
        result["errors"].append("INVALID_DAILY_OHLCV")
    if not bars.data_version.astype(str).eq("v2").all():
        result["errors"].append("UNVERIFIED_VOLUME_UNIT")
    sources = sorted(bars.source.dropna().astype(str).unique().tolist())
    # This narrow demo is explicitly TDX-only, not a general provider
    # certification. Accept no unexpected or user-labelled fake sources.
    if (bars.source.isna().any() or not sources
            or any(x != "tdx_protocol" for x in sources)):
        result["errors"].append("BANNED_OR_MISSING_SOURCE")
    if require_real and not sources:
        result["errors"].append("NO_REAL_SOURCE")
    if bars.symbol.isna().any() or not set(bars.symbol).issubset(set(expected_symbols)):
        result["errors"].append("UNEXPECTED_SYMBOLS")
    target_ts = pd.Timestamp(target_date) if target_date else (dates.max() if not dates.empty else None)
    verified_sessions = sorted(d for d in trading_dates if target_ts is not None and d <= target_ts)
    expected_tail = set(verified_sessions[-min_sessions:]) if len(verified_sessions) >= min_sessions else set()
    if len(verified_sessions) < min_sessions:
        result["errors"].append("INSUFFICIENT_EXCHANGE_CALENDAR")
    if target_ts is not None and target_ts not in trading_dates:
        result["errors"].append("TARGET_DATE_NOT_CONFIRMED_TRADING_SESSION")
    for symbol in expected_symbols:
        frame = bars.loc[bars.symbol.eq(symbol)].sort_values("trade_date")
        if frame.empty:
            result["errors"].append("MISSING_EXPECTED_SYMBOL:" + symbol)
        elif target_date is not None and str(frame.trade_date.iloc[-1])[:10] != target_date:
            result["errors"].append("MISSING_TARGET_DATE:" + symbol)
        actual_sessions = set(pd.to_datetime(frame.trade_date, errors="coerce").dt.normalize())
        missing = sorted(expected_tail - actual_sessions)
        if len(frame) < min_sessions:
            result["errors"].append("INSUFFICIENT_SAMPLE_SESSIONS:" + symbol)
        if missing:
            result["errors"].append("MISSING_CONSECUTIVE_SESSIONS:" + symbol)
        result["coverage"][symbol] = {
            "most_recent_sessions_expected": len(expected_tail),
            "missing_recent_sessions": [str(d.date()) for d in missing[:15]],
            "missing_recent_session_count": len(missing),
            "bars": len(frame),
            "first": str(frame.trade_date.iloc[0])[:10] if not frame.empty else None,
            "last": str(frame.trade_date.iloc[-1])[:10] if not frame.empty else None,
        }
    # Hash of canonical readback values for later reproducibility; this is
    # not a vendor-authenticated immutable source-revision receipt.
    digest_data = bars.sort_values(["symbol", "trade_date"]).to_csv(index=False)
    result["bars"] = {"rows": len(bars), "sources": sources,
                      "content_sha256": hashlib.sha256(digest_data.encode()).hexdigest(),
                      "units": "volume=shares (v2)", "from_curated_query": True}
    # Historical ST can be partial or nonexistent in demo mode. Never pretend
    # the absence of status rows means a stock is non-ST.
    try:
        status = reader("trading_status", data_root=data_root).to_pandas()
        for col in ("symbol", "trade_date", "is_trading", "risk_warning"):
            if col not in status.columns:
                raise ValueError("Missing trading_status column " + col)
        subset = status.loc[status.symbol.isin(expected_symbols)]
        # A derived trading row with unknown risk_warning is NOT ST evidence.
        risk = subset.risk_warning.map(parse_flag)
        trading = subset.is_trading.map(parse_flag)
        known = subset.loc[risk.notna() & trading.notna()]
        if subset.duplicated(["symbol", "trade_date"]).any():
            result["strategy_blockers"].append("DUPLICATE_TRADING_STATUS")
        keys = set(zip(known.symbol.astype(str), known.trade_date.astype(str).str[:10]))
        required_keys = set(zip(bars.symbol.astype(str), bars.trade_date.astype(str).str[:10]))
        result["bars"]["historical_status_coverage"] = len(required_keys & keys) / len(required_keys)
        result["bars"]["unverified_status_records"] = len(required_keys - keys)
        if required_keys - keys:
            result["strategy_blockers"].append("HISTORICAL_STATUS_NOT_COMPLETE")
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        result["bars"]["historical_status_coverage"] = None
        result["bars"]["status_read_warning"] = str(exc)[:180]
        result["strategy_blockers"].append("TRADING_STATUS_DATASET_MISSING")
    if not result["errors"]:
        result["strategy_blockers"].append("DEMO_NOT_FULL_POINT_IN_TIME_UNIVERSE")
    result["provider_live_bars_verified"] = not result["errors"] and require_real
    result["status"] = ("REAL_DEMO_BARS_READBACK_PASSED_NOT_FULL_UNIVERSE"
                        if result["provider_live_bars_verified"]
                        else "DEMO_DATA_FAILED_OR_INCOMPLETE")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--expected-symbols", default="600519.SH,000001.SZ")
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-sessions", type=int, default=20,
                        help="Required contiguous recent exchange sessions per demo stock")
    parser.add_argument("--target-date", help="Require a bar on this YYYY-MM-DD date for each expected symbol")
    args = parser.parse_args()
    symbols = [x.strip() for x in args.expected_symbols.split(",")]
    try:
        report = validate_lake(
            args.data_root, symbols, target_date=args.target_date,
            min_sessions=args.min_sessions,
        )
    except Exception as exc:
        # A missing parquet partition or incompatible query schema must
        # still leave a useful artifact for the developer to diagnose.
        report = {
            "status": "READBACK_RUNTIME_ERROR",
            "target_date": args.target_date,
            "requested_symbols": symbols,
            "provider_live_bars_verified": False,
            "historical_universe_approved": False,
            "strategy_approved": False,
            "errors": ["LAKE_READBACK_EXCEPTION"],
            "exception_type": type(exc).__name__,
            "exception": str(exc)[:500],
        }
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8")
    print("CN_E2E_LAKE_READBACK", report["status"], report.get("bars", {}).get("rows", 0))
    if report["status"] not in {"REAL_DEMO_BARS_READBACK_PASSED_NOT_FULL_UNIVERSE"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
