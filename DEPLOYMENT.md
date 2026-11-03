# GitHub and Streamlit deployment

GitHub contains the source code and the prepared public project sample. Streamlit Community Cloud runs the live application.

## Public files and data

The repository includes `data/default_project_sample.csv`, an aligned common-date dataset of 2,709 observations from 2015-11-02 to 2026-10-30. Its complete preparation record is in [`data/DEFAULT_SAMPLE_SOURCE.md`](data/DEFAULT_SAMPLE_SOURCE.md). The user confirmed public hosted use of this prepared sample on 2026-11-03.

The original three provider exports, local source manifest, research archives, saved run outputs, local environments and credentials are excluded. The application calculates its output from the prepared data; it does not hard-code saved performance results or fetch live market prices.

The hosted app reads its bundled sample and the single CSV a visitor explicitly selects for upload. Its code does not scan the visitor's device, open other local paths, execute uploaded content, or save uploaded CSVs to disk or GitHub. The selected CSV is sent to Streamlit Community Cloud for analysis. Do not upload personal or sensitive files. The uploader limits files to 10 MB, 10,000 data rows and 50 columns. The app's code cannot set or verify Streamlit's separate service-level data-retention practices.

## What a visitor sees

1. Opening the public app loads the prepared sample and starts the walk-forward model analysis automatically.
2. To try a newer dataset, uncheck **Use the prepared project sample**, upload a daily CSV, map its date/equity/bond/gold columns, enter a source note, and confirm that the data is authorized and comparable.
3. Once confirmed, the app aligns the dates and automatically reruns when the uploaded file, mapping, or evaluation settings change.
4. The uploaded file and its results stay within that visitor's current app session; they do not overwrite the shared sample or update the code. Replacing the default for all visitors requires reviewing and publishing a replacement sample in the repository.

The app sorts valid observations, rejects duplicate dates, excludes rows with missing or non-numeric required levels and never interpolates them. Use total-return or adjusted levels consistently. Do not use provider data in another hosted demo unless its terms and your permissions allow that use.

## Current public deployment

- App: [Financial Risk Intelligence](https://financial-risk-intelligence-mfzjzfwa4itnzspf3r5skz.streamlit.app/)
- Source: [public GitHub repository](https://github.com/prabhatseemasingh/financial-risk-intelligence), branch `main`, entrypoint `app.py`
- Visibility: public; the app does not require visitors to sign in
- Default input: `data/default_project_sample.csv`

GitHub changes to `main` trigger the connected Streamlit app to rebuild. After each change, wait for the deployment to finish and open the public app to verify the result. Do not share the local address displayed by Streamlit, since it only works on the computer running that local app.

## Run locally

From this project folder, install the packages pinned in `requirements.txt` and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Streamlit opens the application in a browser on that computer. The same default sample and upload workflow are available.

For host-specific details, see Streamlit's [deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) and [dependency guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies).
