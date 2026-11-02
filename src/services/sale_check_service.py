"""商品售卖状态巡检。

通过复用登录态访问商品详情页，读取闲鱼详情接口的 itemStatus 判断商品是否
仍在售；接口不可用时回退到页面文案。已标记为已售/下架的商品不会再次巡检。
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from datetime import datetime

from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.config import RUN_HEADLESS, STATE_FILE
from src.domain import sale_status as sale_state
from src.rotation import load_state_files
from src.services.result_storage_service import (
    apply_sale_check_results,
    load_sale_check_candidates,
)

SALE_CHECK_LOG_PATH = "logs/sale_check.log"
DETAIL_RESPONSE_MARKER = "mtop.taobao.idle.pc.detail"
ITEM_URL_TEMPLATE = "https://www.goofish.com/item?id={item_id}"
HOME_URL = "https://www.goofish.com/"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

RISK_CONTROL_MARKER = "FAIL_SYS_USER_VALIDATE"
DELETED_RET_MARKER = "FAIL_BIZ_ITEM_DEL_NOT_FOUND"
SOLD_TEXT_MARKERS = ("卖掉了", "已售出", "已卖出")
DELISTED_TEXT_MARKERS = ("宝贝被删掉了", "已下架", "宝贝不存在", "该宝贝已失效")


class SaleCheckAborted(RuntimeError):
    """巡检需要整体中止（登录态失效或触发风控）。"""


def _log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def extract_item_id(item_id: str | None, link: str | None) -> str | None:
    text = str(item_id or "").strip()
    if text:
        return text
    raw_link = str(link or "")
    marker = "id="
    if marker in raw_link:
        candidate = raw_link.split(marker, 1)[1].split("&", 1)[0].strip()
        return candidate or None
    return None


def classify_sale_state(
    detail_payload: dict | None,
    page_text: str = "",
) -> tuple[str, str]:
    """把详情接口响应/页面文案映射为 (sale_status, evidence)。"""
    detail_payload = detail_payload if isinstance(detail_payload, dict) else {}
    raw_ret = detail_payload.get("ret")
    if isinstance(raw_ret, (list, tuple)):
        ret_text = " ".join(str(part) for part in raw_ret)
    else:
        ret_text = str(raw_ret or "")

    if DELETED_RET_MARKER in ret_text or "宝贝不存在或已被删除" in ret_text:
        return sale_state.DELISTED, "detail_api_deleted"

    data = detail_payload.get("data") or {}
    item_do = data.get("itemDO") or {}

    code = item_do.get("itemStatus")
    if isinstance(code, int) and not isinstance(code, bool):
        mapped = sale_state.ITEM_STATUS_CODE_MAP.get(code)
        if mapped is not None:
            return mapped, f"itemStatus={code}"

    status_text = str(item_do.get("itemStatusStr") or "")
    if status_text:
        if "卖掉" in status_text or "已售" in status_text:
            return sale_state.SOLD, status_text
        if "在线" in status_text or "在售" in status_text:
            return sale_state.ON_SALE, status_text
        if "下架" in status_text:
            return sale_state.DELISTED, status_text

    text = page_text or ""
    if any(marker in text for marker in SOLD_TEXT_MARKERS):
        return sale_state.SOLD, "page_text_sold"
    if any(marker in text for marker in DELISTED_TEXT_MARKERS):
        return sale_state.DELISTED, "page_text_delisted"
    return sale_state.UNKNOWN, ret_text or "no_signal"


def resolve_state_file() -> str | None:
    if os.path.exists(STATE_FILE):
        return STATE_FILE
    state_dir = os.getenv("ACCOUNT_STATE_DIR", "state")
    for path in load_state_files(state_dir):
        if os.path.isfile(path):
            return path
    return None


def _load_storage_state(state_file: str):
    """兼容普通 storage_state 与 Chrome 扩展导出的增强快照。"""
    with open(state_file, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict) and any(
        key in payload for key in ("env", "headers", "page", "storage")
    ):
        return {"cookies": payload.get("cookies", [])}
    return payload


def _is_login_url(url: str) -> bool:
    lowered = (url or "").lower()
    return "login" in lowered or "passport" in lowered


def _resolve_launch_channel() -> str:
    """与 src.scraper 的浏览器通道选择保持一致。"""
    if os.getenv("RUNNING_IN_DOCKER", "false").strip().lower() == "true":
        return "chromium"
    if os.getenv("LOGIN_IS_EDGE", "false").strip().lower() == "true":
        return "msedge"
    return "chrome"


async def _probe_item(page, item_id: str) -> dict:
    detail_payload: dict | None = None
    page_text = ""
    error = ""

    try:
        async with page.expect_response(
            lambda response: DETAIL_RESPONSE_MARKER in response.url,
            timeout=15000,
        ) as response_info:
            await page.goto(
                ITEM_URL_TEMPLATE.format(item_id=item_id),
                wait_until="domcontentloaded",
                timeout=40000,
            )
        response = await response_info.value
        detail_payload = await response.json()
    except PlaywrightTimeoutError:
        error = "detail_timeout"
    except Exception as exc:  # noqa: BLE001 - 单条失败不应中断整轮
        error = f"detail_error: {exc}"[:200]

    if _is_login_url(page.url):
        raise SaleCheckAborted("登录态失效，已跳转登录页")

    try:
        page_text = await page.inner_text("body")
    except Exception:  # noqa: BLE001
        page_text = ""

    sale_status, evidence = classify_sale_state(detail_payload, page_text)

    if RISK_CONTROL_MARKER in str((detail_payload or {}).get("ret", "")):
        raise SaleCheckAborted("触发闲鱼风控验证 (FAIL_SYS_USER_VALIDATE)")

    return {
        "item_id": item_id,
        "sale_status": sale_status,
        "evidence": evidence,
        "error": error,
        "checked_at": datetime.now().isoformat(),
    }


async def check_items_state(
    items: list[dict],
    *,
    state_file: str,
    headless: bool = True,
    delay_range: tuple[float, float] = (2.0, 4.0),
) -> tuple[list[dict], bool]:
    """逐个巡检商品，返回 (结果列表, 是否被中止)。"""
    results: list[dict] = []
    aborted = False

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
            channel=_resolve_launch_channel(),
        )
        try:
            context = await browser.new_context(
                storage_state=_load_storage_state(state_file),
                locale="zh-CN",
                user_agent=USER_AGENT,
                viewport={"width": 1366, "height": 768},
            )
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page = await context.new_page()
            try:
                await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(random.uniform(1.0, 2.0))

                for index, item in enumerate(items, start=1):
                    item_id = item.get("item_id")
                    if not item_id:
                        continue
                    try:
                        result = await _probe_item(page, str(item_id))
                    except SaleCheckAborted as exc:
                        _log(f"巡检中止: {exc}")
                        aborted = True
                        break
                    results.append(result)
                    _log(
                        f"[{index}/{len(items)}] {item_id} -> {result['sale_status']}"
                        f" ({result['evidence']})"
                    )
                    await asyncio.sleep(random.uniform(*delay_range))
            finally:
                await page.close()
                await context.close()
        finally:
            await browser.close()

    return results, aborted


async def run_sale_check(
    *,
    limit: int = 40,
    lookback_days: int = 7,
    dry_run: bool = False,
    headless: bool | None = None,
) -> dict:
    candidates = await load_sale_check_candidates(limit=limit, lookback_days=lookback_days)
    if not candidates:
        _log("没有需要巡检的推荐商品（可能都已售/下架或超出回看天数）")
        return {"checked": 0, "updated": 0, "aborted": False}

    state_file = resolve_state_file()
    if not state_file:
        _log("未找到可用的登录态文件，跳过巡检")
        return {"checked": 0, "updated": 0, "aborted": False, "error": "no_state_file"}

    _log(f"开始巡检 {len(candidates)} 个商品，登录态: {state_file}")
    results, aborted = await check_items_state(
        candidates,
        state_file=state_file,
        headless=RUN_HEADLESS if headless is None else headless,
    )

    updated = 0
    if not dry_run and results:
        # 未知状态也写入 checked_at，避免同一批商品被反复巡检。
        updated = await apply_sale_check_results(results)

    summary = {
        "checked": len(results),
        "updated": updated,
        "aborted": aborted,
        "sold": sum(1 for r in results if r["sale_status"] == sale_state.SOLD),
        "delisted": sum(1 for r in results if r["sale_status"] == sale_state.DELISTED),
        "on_sale": sum(1 for r in results if r["sale_status"] == sale_state.ON_SALE),
        "unknown": sum(1 for r in results if r["sale_status"] == sale_state.UNKNOWN),
    }
    _log(
        "巡检完成: "
        f"检查 {summary['checked']}，已售 {summary['sold']}，"
        f"下架 {summary['delisted']}，在售 {summary['on_sale']}，"
        f"未知 {summary['unknown']}，更新 {summary['updated']}"
    )
    return summary


_active_process: asyncio.subprocess.Process | None = None


async def spawn_sale_check(limit: int, lookback_days: int) -> int | None:
    """后台启动巡检子进程；已有巡检在跑时返回 None。"""
    global _active_process
    if _active_process is not None and _active_process.returncode is None:
        return None

    os.makedirs(os.path.dirname(SALE_CHECK_LOG_PATH) or ".", exist_ok=True)
    log_handle = open(SALE_CHECK_LOG_PATH, "a", encoding="utf-8")
    command = [
        sys.executable,
        "-u",
        "check_sales.py",
        "--limit",
        str(limit),
        "--lookback-days",
        str(lookback_days),
    ]
    try:
        _active_process = await asyncio.create_subprocess_exec(
            *command,
            stdout=log_handle,
            stderr=log_handle,
        )
    except Exception:
        log_handle.close()
        raise

    process = _active_process

    async def _wait() -> None:
        await process.wait()
        log_handle.close()

    asyncio.create_task(_wait())
    return process.pid
