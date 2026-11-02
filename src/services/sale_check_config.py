"""商品巡检配置读取与校验。"""
from __future__ import annotations

from src.infrastructure.config.env_manager import env_manager

SALE_CHECK_ENABLED = "SALE_CHECK_ENABLED"
SALE_CHECK_CRON = "SALE_CHECK_CRON"
SALE_CHECK_BATCH_SIZE = "SALE_CHECK_BATCH_SIZE"
SALE_CHECK_LOOKBACK_DAYS = "SALE_CHECK_LOOKBACK_DAYS"
SALE_CHECK_RECHECK_HOURS = "SALE_CHECK_RECHECK_HOURS"

SALE_CHECK_ENV_KEYS = (
    SALE_CHECK_ENABLED,
    SALE_CHECK_CRON,
    SALE_CHECK_BATCH_SIZE,
    SALE_CHECK_LOOKBACK_DAYS,
    SALE_CHECK_RECHECK_HOURS,
)

DEFAULT_CRON = "20 */2 * * *"
DEFAULT_BATCH_SIZE = 40
DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_RECHECK_HOURS = 12.0

BATCH_SIZE_LIMITS = (1, 500)
LOOKBACK_DAYS_LIMITS = (1, 90)
RECHECK_HOURS_LIMITS = (0.0, 168.0)


def _as_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(raw: str | None, default: int) -> int:
    text = str(raw or "").strip()
    return int(text) if text.isdigit() else default


def _as_float(raw: str | None, default: float) -> float:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


def load_sale_check_config() -> dict:
    return {
        SALE_CHECK_ENABLED: _as_bool(
            env_manager.get_value(SALE_CHECK_ENABLED), True
        ),
        SALE_CHECK_CRON: (
            str(env_manager.get_value(SALE_CHECK_CRON, DEFAULT_CRON) or "").strip()
            or DEFAULT_CRON
        ),
        SALE_CHECK_BATCH_SIZE: _as_int(
            env_manager.get_value(SALE_CHECK_BATCH_SIZE), DEFAULT_BATCH_SIZE
        ),
        SALE_CHECK_LOOKBACK_DAYS: _as_int(
            env_manager.get_value(SALE_CHECK_LOOKBACK_DAYS), DEFAULT_LOOKBACK_DAYS
        ),
        SALE_CHECK_RECHECK_HOURS: _as_float(
            env_manager.get_value(SALE_CHECK_RECHECK_HOURS), DEFAULT_RECHECK_HOURS
        ),
    }


def validate_sale_check_config(payload: dict) -> dict:
    """校验并规范化设置，返回可直接写入 .env 的字符串字典。"""
    batch = int(payload.get(SALE_CHECK_BATCH_SIZE, DEFAULT_BATCH_SIZE))
    lookback = int(payload.get(SALE_CHECK_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS))
    recheck = float(payload.get(SALE_CHECK_RECHECK_HOURS, DEFAULT_RECHECK_HOURS))

    if not BATCH_SIZE_LIMITS[0] <= batch <= BATCH_SIZE_LIMITS[1]:
        raise ValueError(
            f"单轮条数需在 {BATCH_SIZE_LIMITS[0]}-{BATCH_SIZE_LIMITS[1]} 之间"
        )
    if not LOOKBACK_DAYS_LIMITS[0] <= lookback <= LOOKBACK_DAYS_LIMITS[1]:
        raise ValueError(
            f"回看天数需在 {LOOKBACK_DAYS_LIMITS[0]}-{LOOKBACK_DAYS_LIMITS[1]} 之间"
        )
    if not RECHECK_HOURS_LIMITS[0] <= recheck <= RECHECK_HOURS_LIMITS[1]:
        raise ValueError(
            f"冷却小时数需在 {RECHECK_HOURS_LIMITS[0]}-{RECHECK_HOURS_LIMITS[1]} 之间"
        )

    cron = str(payload.get(SALE_CHECK_CRON) or "").strip() or DEFAULT_CRON

    return {
        SALE_CHECK_ENABLED: "true" if payload.get(SALE_CHECK_ENABLED) else "false",
        SALE_CHECK_CRON: cron,
        SALE_CHECK_BATCH_SIZE: str(batch),
        SALE_CHECK_LOOKBACK_DAYS: str(lookback),
        SALE_CHECK_RECHECK_HOURS: str(recheck),
    }
