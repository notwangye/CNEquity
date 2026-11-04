# CNEquity → ashare-quant integration (fork-specific)

This fork provides a separate data foundation for
https://github.com/notwangye/ashare-quant. Keep vendor ingest, storage and
quality logic upstream-compatible. Custom investment screening stays in the
private `ashare-quant` repository.

## The first safe test

Go to **Actions → A-share bridge isolated smoke → Run workflow**.
Choose `sample` for the default offline synthetic test. It installs this fork,
runs isolated unit tests and builds a disposable, explicitly synthetic lake.
The result is uploaded as artifact `ashare-bridge-contract`. No R2 credentials,
market orders, or persistent market data are used.

Choose `demo` only when ready for a **live-source network connectivity** test
with a handful of securities. It is not an all-market backtest.

The contract checker reads `daily_bars`, `instruments`, `trading_status`
and `trading_calendar`. It ensures the minimal schema is present, the volume
unit is the documented v2 share-based unit, and no synthetic data is claimed
research-eligible. A successful smoke proves *wiring only*. A real-data result
must still pass historical ST/PIT, coverage, quality and universe audits.

For an existing isolated lake, run a read-only contract diagnostic:

```bash
python integrations/ashare_quant/check_lake_contract.py \
  --data-root /absolute/persistent/cnequity-lake \
  --output /tmp/ashare-lake-contract.json
```

The contract JSON always has `research_allowed=false` because this minimal
check is intentionally insufficient to approve a historical study. Never use
the offline `sample` dataset for a real trading signal.

## Production plan — intentionally not enabled yet

1. Run an isolated small live `demo`; inspect actual source quality.
2. Initialize a persistent CNEquity lake with normal incremental updates; do not enable backup or restore workflows.
3. Verify PIT historical ST evidence, market status, daily bars, coverage
   and reported schema version. Cross-check a sample with old BaoStock rows.
4. Do not migrate or retain the retired BaoStock collector or its backup scripts.
5. Only after explicit data acceptance, feed validated records through
   `ashare-quant/cnequity_lake_screen.py` into the research-only model.

The strategy remains T+1/T+2 with planned 5% target and 3% stop, 100-share
lots, no artificial cash/order cap, and **no automatic live orders**.
