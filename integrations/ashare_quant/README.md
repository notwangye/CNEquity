# CNEquity × ashare-quant

The CNEquity fork owns A-share data updates and a local Parquet/DuckDB
data lake. The separate `ashare-quant` repository owns all research,
selection, backtesting, and optional strategy analysis.

## Active configuration

Use `configs/ashare-quant.toml` for the dedicated lake:

- BaoStock source disabled.
- TDX enabled, mock data disabled.
- No R2 mirror, backup, restore, or historical snapshot workflow.
- No auto-trading or brokerage connectivity.

Run a smoke test from **Actions → A-share bridge isolated smoke**.
Sample mode only proves installation and schema wiring. Demo mode tests
a small real-source dataset. Neither certifies full-universe historical
completeness or a profitable strategy.

The minimal read-only contract checker is
`integrations/ashare_quant/check_lake_contract.py`. Its
`research_allowed=false` flag is intentional: it checks columns and
declared units, but cannot certify complete historical ST evidence.

Production research needs validated mainboard listing dates, complete
daily bars, historical risk-warning evidence, and a trading calendar.
Unknown ST state is excluded instead of being assumed clean.

The upstream CNEquity Python package still includes optional BaoStock
implementation/dependency code. The dedicated config **disables use**
of that source in our workflow; removing the vendor dependency itself
would require an upstream compatibility and installation audit.

## Real 2026-11-04 end-to-end acceptance

GitHub Actions workflow:
`https://github.com/notwangye/CNEquity/actions/workflows/ashare-lake-e2e.yml`

This automatically runs on changes to the E2E validator/workflow, or
manually using **Run workflow**. It uses the **real TDX provider**, NOT
sample/mock data, with two explicitly named demo stocks:

- `600519.SH` and `000001.SZ`, exactly **2026-11-04** as the end session
- An isolated, disposable lake; no R2, no backup or broker actions
- Fresh-process `query.load` readback of unadjusted daily bars
- At least **60 consecutive exchange sessions** for each symbol, with no
  missing middle session, duplicate, or invalid bar geometry
- Instrument identity, exchange calendar and raw source/volume metadata
- Separate historical ST evidence accounting; not falsely approved by
  successful demo bars

Read the workflow's **Summary** for per-stock last date and missing sessions,
or download `cnequity-real-demo-e2e-report` containing `readback.json`
and `ingestion.log`. A failed source connection is a *failed real-data
test*, not a successful mock fallback.

An acceptable demo-level verdict is
`REAL_DEMO_BARS_READBACK_PASSED_NOT_FULL_UNIVERSE`, with
`provider_live_bars_verified=true`. This does **not** approve the
strategy: full-universe PIT listing coverage, historical ST, future signal
validation, and brokerage fills are separate gates.

If the workflow never starts, inspect fork Actions settings and workflow
permissions. Commits to a YAML file alone are not proof of execution.
