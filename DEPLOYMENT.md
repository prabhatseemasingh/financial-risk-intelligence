# GitHub and Streamlit deployment

GitHub stores the project's source files. Streamlit Community Cloud runs the live Streamlit application. A GitHub repository by itself does not create a running app.

## What this project publishes

The repository is designed to contain the application code, documentation, dependency list and empty CSV template. It excludes prepared market data, research archives, saved predictions, portfolio results, local environments and credentials. The public app therefore starts without the private/local project sample and asks the viewer to upload an authorized CSV before analysis.

The app does not fetch live market prices. Do not upload a dataset to a hosted app unless its provider's terms and your permissions allow that use. The project currently has permission to train on its collected data; public redistribution and hosted-app upload permissions have not been established.

## Prepare the GitHub repository

1. Create a repository in your GitHub account. Choose **Private** if you want to control who can see the source. Choose **Public** only if you are comfortable making the code and documentation visible to anyone. Keep the data files out of either repository.
2. Put the contents of this `financial-risk-intelligence` folder at the repository root. The entrypoint is `app.py` and dependencies are listed in `requirements.txt`.
3. Before publishing, inspect the selected files. Do not add `data/processed/market_data_aligned.csv`, `data/processed/data_manifest.json`, anything under `data/research_inputs/`, anything under `results/`, `.venv/`, or credential files.
4. Push the reviewed source files to the repository's default branch (commonly `main`).

## Deploy with Streamlit Community Cloud

1. Sign in at [share.streamlit.io](https://share.streamlit.io/) using GitHub and grant the access needed for the repository you chose.
2. Select **Create app**, then select the repository, branch and `app.py` entrypoint.
3. Use a Python version compatible with `requirements.txt`; choose the same Python version used for local development when available.
4. Deploy and wait for the build to finish. If it fails, review the build logs and correct the reported dependency or application issue.
5. Open the resulting `*.streamlit.app` address and confirm that the app loads. With no bundled dataset, confirm that it displays the upload workflow. Only call it ready for a full project demonstration after an authorized data workflow has been approved and verified.
6. After the host issues a real URL, replace the placeholder in the presentation with that exact verified address. Never present `http://127.0.0.1:8501` as a public URL; it works only on the computer running the local app.

## Local run

From this folder, install the pinned packages in `requirements.txt` and run:

```powershell
python -m streamlit run app.py
```

See the [Streamlit deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) and [dependency guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies) for current host instructions.

## Current deployment

- App: [Financial Risk Intelligence](https://financial-risk-intelligence-mfzjzfwa4itnzspf3r5skz.streamlit.app/)
- Source: private GitHub repository, branch `main`, entrypoint `app.py`
- Visibility: private on Streamlit Community Cloud
- Verified behavior: the hosted page loads and shows the CSV upload workflow; no market data or saved research results are bundled.

For a department presentation, either invite viewers in Streamlit or make the app public while keeping the GitHub source repository private. The public setting makes the app accessible to anyone with its URL. The viewer must still provide a CSV allowed for hosted use to run an analysis.

