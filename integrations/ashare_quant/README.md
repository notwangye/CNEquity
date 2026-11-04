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
2. On a separately provisioned persistent runner/storage volume, initialize
   the proper full-universe data lake. **GitHub-hosted ephemeral runners are
   not persistent storage.** Do not schedule `cne run daily` there without
   designing and verifying durable backup/restore first.
3. Verify PIT historical ST evidence, market status, daily bars, coverage
   and reported schema version. Cross-check a sample with old BaoStock rows.
4. Design independent R2 storage paths for the new lake; never overwrite
   the old `ashare-quant-data/history.tar.gz` or its SHA manifest.
5. Only after explicit data acceptance, feed validated records through
   `ashare-quant/cnequity_lake_screen.py` into the research-only model.

The strategy remains T+1/T+2 with planned 5% target and 3% stop, 100-share
lots, no artificial cash/order cap, and **no automatic live orders**.

## Separate durable R2 snapshot (manual only)

A new `snapshot_r2.sh` implements immutable backups at
`<remote>:<bucket>/cnequity-v1/lake-<run>-<attempt>.tar.gz`, with a SHA-256
sidecar. It refuses to overwrite existing snapshots, and restore refuses
nonempty destinations and unsafe archive members. This is **not yet an
automated daily production pipeline**. It requires a persisted CNEquity lake
and explicitly paused lake writers.

```bash
export CNE_LAKE_ROOT=/absolute/persistent/cnequity-lake
export CNE_R2_REMOTE=primary
export CNE_R2_BUCKET=ashare-quant-data
export CNE_WRITERS_STOPPED=true
bash integrations/ashare_quant/snapshot_r2.sh backup

# Set the exact ID printed after successful backup.
export CNE_SNAPSHOT_ID=lake-RUN-1.tar.gz
bash integrations/ashare_quant/snapshot_r2.sh verify
# Restore only to a NEW, empty destination after the hash passes.
# bash integrations/ashare_quant/snapshot_r2.sh restore
```

The `primary` rclone remote must already be configured with independent
credentials; **do not commit tokens or secret files**. Production will use
GitHub Actions secrets and serialized jobs only after a real-data smoke
and a full restore dry run are verified. The legacy BaoStock
`history.tar.gz` and `history.sha256` keys are never referenced.
