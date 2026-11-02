import asyncio
import json
import sqlite3
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import results

FILENAME = "demo_full_data.jsonl"


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _record(item_id: str, title: str):
    return {
        "爬取时间": datetime.now().isoformat(),
        "商品信息": {
            "商品ID": item_id,
            "商品标题": title,
            "商品链接": f"https://www.goofish.com/item?id={item_id}",
            "当前售价": "¥5000",
        },
        "ai_analysis": {"is_recommended": True, "analysis_source": "ai"},
    }


def _prepare(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    jsonl_dir = tmp_path / "jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(
        jsonl_dir / FILENAME,
        [_record("1001", "sold item"), _record("1002", "delisted item"), _record("1003", "active item")],
    )
    app = FastAPI()
    app.include_router(results.router)
    return TestClient(app), tmp_path / "data" / "app.sqlite3"


def _set_listing_status(db_path, item_id, status):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE result_items SET sale_status = ?, sale_checked_at = ? WHERE item_id = ?",
            (status, "2026-11-02T12:00:00", item_id),
        )
        conn.commit()


def test_sold_and_delisted_are_excluded_by_default(tmp_path, monkeypatch):
    client, db_path = _prepare(tmp_path, monkeypatch)

    first = client.get(f"/api/results/{FILENAME}")
    assert first.status_code == 200
    assert first.json()["total_items"] == 3

    _set_listing_status(db_path, "1001", "sold")
    _set_listing_status(db_path, "1002", "delisted")

    default_resp = client.get(f"/api/results/{FILENAME}")
    assert default_resp.status_code == 200
    default_payload = default_resp.json()
    assert default_payload["total_items"] == 1
    assert default_payload["items"][0]["商品信息"]["商品ID"] == "1003"

    with_unavailable = client.get(
        f"/api/results/{FILENAME}", params={"include_unavailable": True}
    )
    assert with_unavailable.status_code == 200
    payload = with_unavailable.json()
    assert payload["total_items"] == 3
    by_id = {item["商品信息"]["商品ID"]: item for item in payload["items"]}
    assert by_id["1001"]["_listing_status"] == "sold"
    assert by_id["1002"]["_listing_status"] == "delisted"
    assert by_id["1003"]["_listing_status"] == "unknown"


def test_export_respects_include_unavailable(tmp_path, monkeypatch):
    client, db_path = _prepare(tmp_path, monkeypatch)
    client.get(f"/api/results/{FILENAME}")
    _set_listing_status(db_path, "1001", "sold")

    default_export = client.get(f"/api/results/{FILENAME}/export")
    assert default_export.status_code == 200
    assert "sold item" not in default_export.text

    full_export = client.get(
        f"/api/results/{FILENAME}/export", params={"include_unavailable": True}
    )
    assert full_export.status_code == 200
    assert "sold item" in full_export.text


def test_sale_check_candidates_skip_sold_and_apply_results(tmp_path, monkeypatch):
    from src.services.result_storage_service import (
        apply_sale_check_results,
        load_sale_check_candidates,
    )

    client, db_path = _prepare(tmp_path, monkeypatch)
    client.get(f"/api/results/{FILENAME}")
    _set_listing_status(db_path, "1001", "sold")

    candidates = asyncio.run(load_sale_check_candidates(limit=10, lookback_days=7))
    candidate_ids = {candidate["item_id"] for candidate in candidates}
    assert candidate_ids == {"1002", "1003"}

    limited = asyncio.run(load_sale_check_candidates(limit=1, lookback_days=7))
    assert len(limited) == 1
    assert limited[0]["item_id"] in {"1002", "1003"}

    asyncio.run(
        apply_sale_check_results(
            [{"item_id": "1002", "sale_status": "delisted", "checked_at": "2026-11-02T12:30:00"}]
        )
    )
    resp = client.get(f"/api/results/{FILENAME}", params={"include_unavailable": True})
    by_id = {item["商品信息"]["商品ID"]: item for item in resp.json()["items"]}
    assert by_id["1002"]["_listing_status"] == "delisted"
