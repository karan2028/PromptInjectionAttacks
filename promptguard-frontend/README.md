# PromptGuard frontend

A dependency-free frontend for the PromptGuard MDC backend. It provides scenario and custom simulations, lexical text analysis, dry-run policy checks, the fixture test suite, and paginated audit summaries and JSON export.

## Run locally

1. Start the backend from `promptguard-backend` with its dependencies installed. Enable CORS for the frontend origin **before** starting it:

   macOS/Linux:
   ```sh
   export PG_CORS_ORIGINS='http://127.0.0.1:5173,http://localhost:5173'
   python run.py
   ```

   Windows PowerShell:
   ```powershell
   $env:PG_CORS_ORIGINS = 'http://127.0.0.1:5173,http://localhost:5173'
   py run.py
   ```

2. In a second terminal, from this frontend directory, run:
   ```sh
   python -m http.server 5173 --bind 127.0.0.1
   ```
3. Open `http://127.0.0.1:5173`. The frontend defaults to `http://127.0.0.1:8000`. Use **Connection settings** to change the backend origin or enter the optional `PG_API_KEY` bearer key. The key is held in the tab's memory only and is lost on reload; never enter the OpenAI provider key in the browser.

If `localhost` and `127.0.0.1` are mixed, both origins still need to be in `PG_CORS_ORIGINS`. If the backend runs elsewhere, configure its CORS and allowed hosts appropriately. HTTPS is required to protect credentials over untrusted networks. This is a local educational prototype, not a production-ready authentication model.

## Notes

- Demo mode is scripted, not a live model. In live mode, each simulation makes two provider calls; the suite may make 14 and requires backend opt-in. Provider charges may apply.
- Policy outcomes are dry runs: no tools or messages are executed. Indicators are not a safety verdict; no match does not establish safety. Safety and legitimate-task checks are distinct.
- Only synthetic inputs should be used. Custom demo inputs select a teaching script and require manual evaluation.
- Audit exports contain only the current page of summaries. Use Next and export each page to cover all records. Full task/source text and responses are not stored by the backend.
- This frontend does not modify the backend; see the backend README for prerequisites and security limitations.
