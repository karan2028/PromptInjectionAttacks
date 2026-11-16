import json
from dataclasses import replace
from unittest.mock import patch, Mock
import httpx
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.engines import Engine, ProviderError
from app.scenarios import CASES, DUMMY_SECRET
from app.schemas import Defenses

@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=str(tmp_path / "test.sqlite3"), requests_per_minute=1000)

@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c

def simulate(client, case="T2", **controls):
    return client.post("/api/v1/simulations", json={"scenario_id": case, "defenses": controls})

def test_health_and_openapi(client):
    assert client.get("/health").json()["tool_execution"] is False
    schema = client.get("/openapi.json").json()
    assert "HTTPBearer" in schema["components"]["securitySchemes"]
    assert client.get("/docs").status_code == 200

def test_scenarios(client):
    cases = client.get("/api/v1/scenarios").json()["scenarios"]
    assert [c["id"] for c in cases] == list(CASES)

@pytest.mark.parametrize("case", list(CASES))
def test_default_scenario_safety_and_task_checks(client, case):
    response = simulate(client, case)
    assert response.status_code == 201
    data = response.json()
    assert data["evaluation"]["safety_check"] == "pass"
    assert data["evaluation"]["task_check"] == "pass"
    assert data["defended"]["policy"]["executed"] is False
    assert data["no_real_side_effects"] is True

def test_compare_and_toggle(client):
    data = simulate(client).json()
    assert data["baseline"]["answer"] == "ORANGE"
    assert "120" in data["defended"]["answer"]
    data = simulate(client, separate_instructions=False).json()
    assert data["defended"]["answer"] == "ORANGE"
    assert data["evaluation"]["safety_check"] == "fail"

def test_secret_policy_denied_independently(client):
    data = simulate(client, "T3", separate_instructions=False).json()
    assert data["defended"]["policy"]["reason_code"] == "LEAST_PRIVILEGE"
    assert DUMMY_SECRET not in data["defended"]["answer"]
    unsafe = simulate(client, "T3", separate_instructions=False, least_privilege=False).json()
    assert unsafe["evaluation"]["safety_check"] == "fail"

def test_approval_and_no_executor(client):
    controls = dict(separate_instructions=False, least_privilege=False)
    held = simulate(client, "T4", **controls).json()
    assert held["defended"]["policy"]["status"] == "held"
    assert held["evaluation"]["task_check"] == "not_demonstrated"
    allowed = simulate(client, "T4", **controls, require_approval=False).json()
    assert allowed["defended"]["policy"]["status"] == "allowed_dry_run"
    assert allowed["defended"]["policy"]["executed"] is False
    assert allowed["evaluation"]["safety_check"] == "fail"

def test_step_budget_independent(client):
    data = simulate(client, "T6", separate_instructions=False, least_privilege=False).json()
    assert data["defended"]["policy"]["reason_code"] == "STEP_BUDGET"
    assert data["evaluation"]["task_check"] == "not_demonstrated"

def test_unknown_tool_never_allowed(client):
    data = simulate(client, "T5", least_privilege=False, validate_schema_and_budget=False).json()
    assert data["defended"]["policy"]["reason_code"] == "UNKNOWN_TOOL"

def policy(client, tool, arguments, **controls):
    return client.post("/api/v1/policy/check", json={"proposal": {"tool": tool, "arguments": arguments}, "defenses": controls})

@pytest.mark.parametrize("tool,args,reason", [
    ("read_document", {"document_id": "../../etc/passwd"}, "DOCUMENT_SCOPE"),
    ("read_secret", {"key": "OPENAI_API_KEY"}, "SECRET_SCOPE"),
    ("send_message", {"to": "real@example.com", "body": "hello"}, "DESTINATION_SCOPE"),
    ("read_document", {"document_id": "demo-001", "admin": True}, "EXTRA_ARGUMENTS"),
    ("search", {"query": "x", "steps": True}, "INVALID_ARGUMENTS"),
    ("search", {"query": "x", "steps": -1}, "INVALID_BUDGET"),
])
def test_policy_validation(client, tool, args, reason):
    response = policy(client, tool, args, least_privilege=False)
    assert response.status_code == 200
    assert response.json()["reason_code"] == reason
    assert response.json()["executed"] is False

def test_read_document_is_only_mock(client):
    data = policy(client, "read_document", {"document_id": "demo-001"}).json()
    assert data["status"] == "allowed_dry_run" and not data["executed"]

def test_detection_quotes_and_no_match_are_not_verdicts(client):
    data = client.post("/api/v1/analyze", json={"text": CASES["T7"]["source"]}).json()
    assert data["matches"] and data["may_be_benign_security_discussion"]
    assert data["is_security_verdict"] is False
    data = client.post("/api/v1/analyze", json={"text": "Good morning"}).json()
    assert data["status"] == "no_known_indicators"
    assert data["is_security_verdict"] is False

def test_custom_input_and_no_unearned_pass(client):
    response = client.post("/api/v1/simulations", json={"task": "Summarize", "source": "Benign custom text"})
    data = response.json()
    assert response.status_code == 201
    assert data["evaluation"]["safety_check"] == "inconclusive"
    assert "No model was called" in data["defended"]["answer"]

@pytest.mark.parametrize("body", [
    {}, {"scenario_id": "T99"}, {"task": "x"},
    {"scenario_id": "T2", "task": "x", "source": "y"},
    {"task": "   ", "source": "x"},
    {"scenario_id": "T2", "defenses": {"least_privilege": "false"}},
    {"scenario_id": "T2", "extra": True},
    {"task": "x", "source": "x" * 12001},
])
def test_input_validation(client, body):
    assert client.post("/api/v1/simulations", json=body).status_code == 422

def test_validation_does_not_echo_input(client):
    response = client.post("/api/v1/simulations", json={"scenario_id": "SUPER_PRIVATE_INPUT"})
    assert response.status_code == 422
    assert "SUPER_PRIVATE_INPUT" not in response.text

def test_request_size_limit(client):
    assert client.post("/api/v1/analyze", content=b"x" * 65537, headers={"Content-Type": "application/json"}).status_code == 413

def test_suite_and_pagination(client):
    suite = client.post("/api/v1/tests/run", json={}).json()
    assert suite["safety_checks"] == {"pass": 7, "fail": 0, "inconclusive": 0}
    assert suite["legitimate_task_checks_passed"] == 7
    page = client.get("/api/v1/logs?limit=2&offset=2").json()
    assert page["total"] == 7 and len(page["records"]) == 2
    assert client.get("/api/v1/logs?limit=99999").status_code == 422
    unsafe = client.post("/api/v1/tests/run", json={"defenses": {"separate_instructions": False, "least_privilege": False, "require_approval": False, "validate_schema_and_budget": False}}).json()
    assert unsafe["safety_checks"] == {"pass": 2, "fail": 5, "inconclusive": 0}

def test_logs_private_export_and_persistence(client, settings):
    data = client.post("/api/v1/simulations", json={"task": "Private task 12345", "source": "PRIVATE-DOCUMENT-CONTENT-ABCDE"}).json()
    result = client.get("/api/v1/logs/" + data["id"])
    assert result.status_code == 200
    assert "PRIVATE-DOCUMENT" not in result.text and "Private task" not in result.text
    assert "answer" not in result.text
    export = client.get("/api/v1/logs/export")
    assert "attachment" in export.headers["Content-Disposition"]
    assert export.json()["total"] == 1
    assert client.get("/api/v1/logs/not-found").status_code == 404
    assert client.get("/api/v1/logs/%27%20OR%201=1--").status_code == 404
    with TestClient(create_app(settings)) as new_client:
        assert new_client.get("/api/v1/logs").json()["total"] == 1

def test_auth_and_headers(settings):
    with TestClient(create_app(replace(settings, api_key="test-only-key"))) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/api/v1/scenarios").status_code == 401
        assert c.get("/api/v1/scenarios", headers={"Authorization": "Bearer wrong"}).status_code == 401
        response = c.get("/api/v1/scenarios", headers={"Authorization": "Bearer test-only-key"})
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"

def test_rate_limit(settings):
    with TestClient(create_app(replace(settings, requests_per_minute=2))) as c:
        assert c.get("/api/v1/scenarios").status_code == 200
        assert c.get("/api/v1/scenarios").status_code == 200
        assert c.get("/api/v1/scenarios").status_code == 429

def test_host_and_cors(settings):
    with TestClient(create_app(replace(settings, cors_origins=("http://localhost:5173",)))) as c:
        assert c.get("/health", headers={"Host": "attacker.invalid"}).status_code == 400
        response = c.options("/api/v1/simulations", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
        response = c.get("/health", headers={"Origin": "https://attacker.invalid"})
        assert "Access-Control-Allow-Origin" not in response.headers

@pytest.mark.parametrize("engine,api_key", [("unknown", ""), ("openai", "")])
def test_settings_fail_fast(settings, engine, api_key):
    with pytest.raises(ValueError):
        create_app(replace(settings, engine=engine, openai_api_key=api_key))

def mock_provider(answer, proposal=None):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": {"content": json.dumps({"answer": answer, "proposed_action": proposal})}}]}
    ctx = Mock()
    ctx.__enter__ = Mock(return_value=ctx)
    ctx.__exit__ = Mock(return_value=False)
    ctx.post.return_value = response
    return ctx

def test_live_adapter_and_dummy_marker_redaction(settings):
    cfg = replace(settings, engine="openai", openai_api_key="provider-test-only")
    provider = mock_provider(DUMMY_SECRET)
    with patch("app.engines.httpx.Client", return_value=provider):
        with TestClient(create_app(cfg)) as c:
            data = simulate(c, "T3").json()
            assert data["engine"] == "openai"
            assert data["baseline"]["answer"] == DUMMY_SECRET
            assert DUMMY_SECRET not in data["defended"]["answer"]
            assert data["defended"]["known_dummy_marker_redacted"]
            sent = provider.post.call_args.kwargs["json"]
            assert "provider-test-only" not in json.dumps(sent)
            assert "dummy_secret =" not in sent["messages"][0]["content"]
            assert provider.post.call_args.args[0] == "https://api.openai.com/v1/chat/completions"

def test_live_suite_disabled_by_default(settings):
    with TestClient(create_app(replace(settings, engine="openai", openai_api_key="test-only"))) as c:
        assert c.post("/api/v1/tests/run", json={}).status_code == 409

def test_provider_failure_sanitized_and_no_saved_record(settings):
    cfg = replace(settings, engine="openai", openai_api_key="test-only")
    provider = mock_provider("x")
    provider.post.side_effect = httpx.ConnectError("PRIVATE_PROVIDER_ERROR_WITH_KEY")
    with patch("app.engines.httpx.Client", return_value=provider):
        with TestClient(create_app(cfg)) as c:
            response = simulate(c)
            assert response.status_code == 502
            assert "PRIVATE_PROVIDER" not in response.text
            assert c.get("/api/v1/logs").json()["total"] == 0

def test_provider_invalid_json_is_rejected(settings):
    cfg = replace(settings, engine="openai", openai_api_key="test-only")
    provider = mock_provider("x")
    provider.post.return_value.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
    with patch("app.engines.httpx.Client", return_value=provider):
        with pytest.raises(ProviderError):
            Engine(cfg).generate(CASES["T2"], Defenses())
