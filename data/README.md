# Data folder

- `default_project_sample.csv` is the 2,709-row prepared dataset loaded by default in the public Streamlit app. It covers 2015-11-02 to 2026-10-30.
- `market_data_template.csv` is an empty CSV template for uploads.
- `DEFAULT_SAMPLE_SOURCE.md` documents the source series, exact-date alignment, exclusions, Gold BeES split adjustment, provenance fingerprints, and limitations.

Local processed data, original source exports, source manifests, research archives and analysis outputs are kept out of the public repository. For new uploads, provide an equity total-return level, an Indian government-bond return level, and an adjusted domestic-gold proxy level in INR. India VIX is optional. The app does not fill missing observations or fetch live market data.

