# Financial Risk Intelligence

An India-focused research application for forecasting a future high-volatility event and testing a simple risk-responsive portfolio rule. It runs locally in Streamlit and uses an authorized data file supplied by the user.

## Current state

- Application and model pipeline are implemented.
- The local research workspace contains a prepared sample and saved analysis outputs. The input data, source manifest, research archives and generated results are excluded from GitHub.
- In the local workspace, the app can restore saved outputs when the prepared sample and evaluation settings match. A clean GitHub clone has no bundled sample: upload an authorized CSV and run the analysis there.
- Dashboard plots thin long daily histories for browser responsiveness; model calculations and downloaded regime/forecast/portfolio files retain the complete daily series. The regime plot keeps regime changes and every higher-volatility cluster point visible.
- The Streamlit Community Cloud app and GitHub repository are public. The hosted app shows the CSV-upload workflow; it contains no market data, source manifest or saved results.
- Permission to publish or redistribute the raw market data was not established. The public app and repository contain code and documentation only; viewers must upload a CSV whose terms allow hosted use.
- Historical results are research outputs, not investment advice or a promise of future performance.

## Run locally on Windows

Use Python 3.12 or a compatible version for the pinned packages. From the project folder, install requirements.txt and run the app:

```powershell
python -m streamlit run app.py
```

Open `http://127.0.0.1:8501` on the same computer. This is a local demo address, not a public deployment URL. The presentation links to the hosted Streamlit app below; use that address for a remote demonstration. The local address works only on this computer.

For a fresh Python installation that includes `ensurepip`, create an environment and install the pinned packages:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run app.py
```

On macOS or Linux, create a Python 3.13 virtual environment, install `requirements.txt`, then run `streamlit run app.py`.

## Data file

Upload a CSV with one row per trading session. The app lets you map the columns, so source column names can differ. Required content:

| Field | Meaning |
|---|---|
| Date | Trading date |
| Equity level | NIFTY 50 Total Returns Index (TRI) or another documented equity total-return level |
| Bond level | NIFTY 10 Yr Benchmark G-Sec total-return index, or another documented Indian government-bond return level; do not use the separately identified clean-price index |
| Gold level | Adjusted INR level for a documented domestic gold ETF or other domestic-gold proxy |
| India VIX | Optional risk feature, if available and timestamp-aligned |

`data/market_data_template.csv` gives the canonical header names. It has no observations. Use adjusted or total-return levels consistently. For the flagship comparison, prefer an equity TRI, a government-bond total-return index and a corporate-action-adjusted domestic gold ETF price series. ETF prices are a tradable proxy with tracking costs and market-price effects; they are not spot-gold returns. Do not mix an unadjusted equity price index with total-return series. The app sorts dates, rejects duplicate dates and excludes rows missing a required asset level. It never interpolates prices.

If official downloads arrive as separate files, `prepare_data.py` combines them on exact matching dates and writes a SHA-256 source manifest. It does not contact data providers or fill missing values. Example command shape:

```powershell
python prepare_data.py `
  --equity-file data/raw/equity.csv --equity-date Date --equity-value TRI `
  --bond-file data/raw/bonds.csv --bond-date Date --bond-value TotalReturnIndex `
  --gold-file data/raw/gold.csv --gold-date Date --gold-value INRLevel `
  --source-note "Provider, series, retrieval date, return convention"
```

Replace file paths and column names with the actual downloaded files. Inspect the generated manifest and aligned rows before uploading the output CSV in the app.

### Data sources and access

- NSE's [historical reports area](https://www.nseindia.com/resources/historical-reports-capital-market-daily-monthly-archives) links to historical indices, Total Returns Index values, India VIX and ETF price archives. For bonds, the Nifty Indices [historical-data page](https://www.niftyindices.com/reports/historical-data) states that fixed-income indices are total-return indices except the separately named NIFTY 10 Yr Benchmark G-Sec (Clean Price). Use the ordinary NIFTY 10 Yr Benchmark G-Sec series only after confirming the downloaded column and date range. NSE explains why equity benchmarks should use the [NIFTY Total Returns Index](https://www.nseindia.com/static/products-services/indices-faqs).
- RBI's [Database on Indian Economy](https://dbie.rbi.org.in/) is a source to review for supplemental official Indian financial series.
- For gold, select an official or otherwise authorized domestic-gold series. If using an NSE-listed gold ETF, download daily prices from its ETF archive, adjust for corporate actions, and document the ETF symbol, currency, adjustment method and retrieval date. Record exact series, source terms and transformations in the app's source note.
- The app does not download data automatically. Check each provider's access and reuse terms before downloading, storing, deploying or sharing data.

For a first study run, aim for at least ten years of aligned daily observations. The default design uses a three-year final holdout, three one-year development folds, 21-session forward labels, and a 21-session purge. The exact data history depends on series availability and licensing; inspect the aligned date range before committing to this design. If the app reports insufficient history, obtain more data or get supervisor approval before changing the windows.

## Model and backtest

1. Features use information through close `t`: lagged returns, trailing volatility, drawdown, cross-asset correlations and optional India VIX.
2. The target is whether forward annualized equity volatility over `t+1` through `t+21` exceeds the training-only 80th percentile.
3. Development folds compare a one-feature volatility logistic baseline, logistic regression, random forest and gradient boosting. The model family with the lowest development-fold Brier score is selected before the holdout.
4. The selected family is refit at declared annual blocks in the final holdout. Training labels whose forward window overlaps the next block are purged.
5. The allocation rule sets equity weight to `60% - 30% × predicted probability`; it splits the remaining allocation equally between bonds and gold. These are illustrative research assumptions, not optimized weights.
6. Signals formed after a month-end close are applied at the next session close. With close-only data, the new allocation earns returns after that execution close. Costs are charged on initial entry and subsequent one-way turnover.
7. Benchmarks are equity buy-and-hold, static 60/20/20, equal weight and a rolling-volatility rule. Report exact dates, assumptions and the zero-risk-free Sharpe convention.

## Main modules

- `risk_intelligence/data.py` maps uploaded columns, aligns dates and reports exclusions.
- `risk_intelligence/features.py` builds point-in-time features and forward volatility.
- `risk_intelligence/evaluation.py` selects a model on development folds and evaluates a chronological holdout.
- `risk_intelligence/portfolio.py` applies the bounded allocation rule, execution lag and cost schedule.
- `risk_intelligence/regimes.py` fits descriptive K-means groups using development history only.
- `risk_intelligence/metrics.py` calculates forecast and portfolio measures.

## Deployment

The [live Streamlit app](https://financial-risk-intelligence-mfzjzfwa4itnzspf3r5skz.streamlit.app/) is public, and the [GitHub source repository](https://github.com/prabhatseemasingh/financial-risk-intelligence) is public. The app was verified to load its CSV-upload workflow; neither the app nor repository contains the collected market data, source manifest, or saved results. Upload only a CSV whose provider terms and permissions allow hosted-app use. See [`DEPLOYMENT.md`](DEPLOYMENT.md) for deployment details.

