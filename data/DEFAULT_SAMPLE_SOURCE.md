# Default public project sample: source and preparation record

## What is included

`data/default_project_sample.csv` is the prepared dataset loaded when the public app opens. It has 2,709 common-date observations from 2015-11-02 to 2026-10-30, with columns `Date`, `Equity_TR`, `Bond_TR`, and `Gold_TR`. India VIX is not included.

The file was made from the user's three supplied downloads, which were aligned by an exact inner join on date. No interpolation, forward fill, backfill, resampling, clipping, or return imputation was used. Input-only dates excluded from the intersection: 68 Gold BeES dates, 15 NIFTY TRI dates, and 40 G-Sec dates. The aligned file has no duplicate dates or missing/non-positive asset levels.

| App column | Supplied source file | Source field | Source rows | Source SHA-256 |
|---|---|---|---:|---|
| `Equity_TR` | `NIFTY 50 Total Returns Index (Gross).csv` | `Total Returns Index` | 2,724 | `ed56a5b8c2eb8cc2c7b1f31f69b6bfb056eed5c52326d32b2a89a65138fc0393` |
| `Bond_TR` | `Nifty 10 Yr Benchmark G-Sec.csv` | `Close` | 2,749 | `1588923760ba49beec99a4cde949063644172d057c6ba42a3db8ff79dffc4317` |
| `Gold_TR` | `Nippon India ETF Gold BeES.csv` | `NAV` | 2,777 | `987e00b351d7af300458a98b70eb9c178be956d17544f0780b7f2512e2a0a45f` |

The original locally aligned output SHA-256 is `26ea58b3cc57cbfc7c1cda30bd789e884c15f8ff3ce3b21e8b813c2b03b492b1`. The deployed public copy's SHA-256, shown in the app's Data and method tab, is `979699d0789ff3168bd40e9412838d1c9f6306f0593455e41fa9aa0905bf5c41`. The CSV observations are unchanged; the byte-level hash differs because the published text file has a different line-ending serialization.

## Gold BeES unit adjustment

The supplied Gold BeES NAV file remains on the old unit scale through 2019-12-20, then switches from about ₹3,358.64 to ₹33.73 on 2019-12-23. [NSE circular CML42873](https://archives.nseindia.com/content/circulars/CML42873.pdf) states that Gold BeES face value changed from ₹100 to ₹1 effective 2019-12-19. The preparation step divided each Gold NAV observation dated before 2019-12-23 by 100 (1,079 rows). This is a corporate-action unit adjustment, not a filled or simulated price. The resulting `Gold_TR` is the adjusted Growth Plan NAV proxy: it is not the ETF exchange close or spot-gold price and does not capture ETF market-price premiums/discounts or executable bid/ask spreads.

## Series meaning and interpretation

- `Equity_TR` is the NIFTY 50 Gross Total Returns Index. NSE explains the total-return convention in its [NIFTY indices FAQ](https://www.nseindia.com/static/products-services/indices-faqs). It includes reinvested distributions per that index methodology.
- `Bond_TR` came from the supplied ordinary NIFTY 10 Yr Benchmark G-Sec export's `Close` column. Nifty Indices describes fixed-income indices as total-return indices except the separately named [NIFTY 10 Yr Benchmark G-Sec (Clean Price)](https://www.niftyindices.com/reports/historical-data). Verify the exact series identity when reproducing from another export.
- `Gold_TR` is the split-adjusted domestic Gold BeES Growth Plan NAV described above. NAV is a fund valuation series; it is not an executable ETF market price.

The user confirmed that this prepared sample may be hosted and used by the public Streamlit app on 2026-11-03. That confirmation applies to this prepared sample in the app and repository; it does not make the original provider exports, source manifest, or unrelated research archives part of this repository. The public sample is intended for academic research and demonstration.

## Reproduction

The original three exports are not included in this repository. To reproduce the aligned CSV, obtain the same series and pass the three explicit file paths to `prepare_collected_data.py` with `--gold`, `--equity`, and `--bond`. The script does not search the computer and only writes output inside the project directory. The transformation code uses exact common dates and applies the stated Gold BeES unit adjustment. The SHA-256 values above can be used to identify matching source files. Check the current provider terms and permissions before using any replacement files.

Primary source references: [NSE historical reports](https://www.nseindia.com/resources/historical-reports-capital-market-daily-monthly-archives), [Nifty Indices historical data](https://www.niftyindices.com/reports/historical-data), [NIFTY indices FAQ](https://www.nseindia.com/static/products-services/indices-faqs), and [NSE circular CML42873](https://archives.nseindia.com/content/circulars/CML42873.pdf).
