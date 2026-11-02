from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import dependencies as deps
from src.api.routes import settings
from src.infrastructure.config.env_manager import env_manager
from src.services import sale_check_service
from src.services.sale_check_config import SALE_CHECK_ENV_KEYS


class _FakeScheduler:
    def __init__(self) -> None:
        self.reload_calls = 0

    def get_sale_check_next_run_time(self):
        return "2026-11-02T14:20:00+08:00"

    def reload_sale_check_job(self) -> None:
        self.reload_calls += 1


def _build_client(scheduler: _FakeScheduler) -> TestClient:
    app = FastAPI()
    app.include_router(settings.router)
    app.dependency_overrides[deps.get_scheduler_service] = lambda: scheduler
    return TestClient(app)


def _prepare_env(tmp_path, monkeypatch) -> tuple[TestClient, _FakeScheduler, object]:
    for key in SALE_CHECK_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(env_manager, "env_file", env_file)

    scheduler = _FakeScheduler()
    return _build_client(scheduler), scheduler, env_file


def test_get_sale_check_settings_returns_defaults(tmp_path, monkeypatch):
    client, _scheduler, _env_file = _prepare_env(tmp_path, monkeypatch)

    response = client.get("/api/settings/sale-check")
    assert response.status_code == 200
    payload = response.json()
    assert payload["SALE_CHECK_ENABLED"] is True
    assert payload["SALE_CHECK_CRON"] == "20 */2 * * *"
    assert payload["SALE_CHECK_BATCH_SIZE"] == 40
    assert payload["SALE_CHECK_LOOKBACK_DAYS"] == 7
    assert payload["SALE_CHECK_RECHECK_HOURS"] == 12
    assert payload["next_run_time"] == "2026-11-02T14:20:00+08:00"
    assert payload["is_running"] is False


def test_update_sale_check_settings_persists_and_reloads_job(tmp_path, monkeypatch):
    client, scheduler, env_file = _prepare_env(tmp_path, monkeypatch)

    response = client.put(
        "/api/settings/sale-check",
        json={
            "SALE_CHECK_ENABLED": False,
            "SALE_CHECK_CRON": "0 */3 * * *",
            "SALE_CHECK_BATCH_SIZE": 25,
            "SALE_CHECK_LOOKBACK_DAYS": 3,
            "SALE_CHECK_RECHECK_HOURS": 6,
        },
    )
    assert response.status_code == 200
    assert response.json()["SALE_CHECK_CRON"] == "0 */3 * * *"
    assert scheduler.reload_calls == 1

    saved = env_file.read_text(encoding="utf-8")
    assert "SALE_CHECK_ENABLED=false" in saved
    assert 'SALE_CHECK_CRON="0 */3 * * *"' in saved
    assert "SALE_CHECK_BATCH_SIZE=25" in saved
    assert "SALE_CHECK_LOOKBACK_DAYS=3" in saved
    assert "SALE_CHECK_RECHECK_HOURS=6.0" in saved


def test_update_sale_check_settings_rejects_invalid_cron(tmp_path, monkeypatch):
    client, scheduler, _env_file = _prepare_env(tmp_path, monkeypatch)

    response = client.put(
        "/api/settings/sale-check",
        json={
            "SALE_CHECK_ENABLED": True,
            "SALE_CHECK_CRON": "not a cron",
            "SALE_CHECK_BATCH_SIZE": 40,
            "SALE_CHECK_LOOKBACK_DAYS": 7,
            "SALE_CHECK_RECHECK_HOURS": 12,
        },
    )
    assert response.status_code == 422
    assert scheduler.reload_calls == 0


def test_update_sale_check_settings_rejects_out_of_range_batch(tmp_path, monkeypatch):
    client, _scheduler, _env_file = _prepare_env(tmp_path, monkeypatch)

    response = client.put(
        "/api/settings/sale-check",
        json={
            "SALE_CHECK_ENABLED": True,
            "SALE_CHECK_CRON": "20 */2 * * *",
            "SALE_CHECK_BATCH_SIZE": 9999,
            "SALE_CHECK_LOOKBACK_DAYS": 7,
            "SALE_CHECK_RECHECK_HOURS": 12,
        },
    )
    assert response.status_code == 422


def test_sale_check_log_returns_tail(tmp_path, monkeypatch):
    client, _scheduler, _env_file = _prepare_env(tmp_path, monkeypatch)
    log_path = tmp_path / "sale_check.log"
    log_path.write_text(
        "\n".join(f"line-{index}" for index in range(1, 301)),
        encoding="utf-8",
    )
    monkeypatch.setattr(sale_check_service, "SALE_CHECK_LOG_PATH", str(log_path))

    response = client.get("/api/settings/sale-check/log", params={"lines": 50})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["lines"]) == 50
    assert payload["lines"][-1] == "line-300"
    assert payload["is_running"] is False
    assert payload["updated_at"]
