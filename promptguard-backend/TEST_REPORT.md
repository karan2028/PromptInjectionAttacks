# Backend verification report

## Executed checks

- `python -m pytest -q`: **44 passed**.
- Actual Uvicorn HTTP smoke check: **passed**.
  - `/health` returned demo engine status.
  - `/openapi.json` exposed the nine documented API paths.
  - T2 simulation returned HTTP 201, scripted `ORANGE` baseline, preserved defended summary and a passing narrow fixture check.
  - Default seven-case suite returned seven safety checks passed.
  - SQLite audit endpoint returned eight persisted summaries after one standalone simulation and the seven-case suite.
  - Mock message proposal was held for approval and reported `executed: false`.
- `examples/sample-demo-response.json` is a real response from that local HTTP smoke run, in explicitly scripted demo mode. Its UUID and timestamp are illustrative run identifiers, not required fixed values.

## Environment

Python 3.13.15; FastAPI 0.162.0; Uvicorn 0.54.0; httpx 0.28.1; Pydantic 2.14.1; pytest 9.1.1. The full package list is in `tested-environment.txt`.

One non-failing dependency warning was emitted: the installed Starlette TestClient deprecates using its httpx integration in favor of httpx2. All tests passed with the installed dependency set. The runtime service uses httpx directly for the optional provider adapter; this warning concerns the test harness.

## Scope and limitations

No real OpenAI account, credentials or model was used. The optional live-provider adapter was tested with mocked JSON responses, known-marker redaction, connection errors and malformed provider output. Real availability, model compatibility, latency, charges and model resistance were **not** measured.

No real tools were executed. The policy layer is implemented, while message sending, web searches, file changes and secret-manager access are intentionally absent. Test success is not a production security assessment.
