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
