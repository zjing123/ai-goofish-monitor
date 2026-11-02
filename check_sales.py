"""推荐商品售卖状态巡检入口。

用法:
  python check_sales.py                      # 巡检最近 7 天的推荐商品（每轮 40 个）
  python check_sales.py --limit 20 --lookback-days 3
  python check_sales.py --dry-run            # 只打印识别结果，不写库
"""
import argparse
import asyncio
import os

from src.services.sale_check_service import run_sale_check


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw.isdigit() else default


def main() -> None:
    parser = argparse.ArgumentParser(description="巡检推荐商品是否已售出或下架")
    parser.add_argument(
        "--limit",
        type=int,
        default=_int_env("SALE_CHECK_BATCH_SIZE", 40),
        help="本轮最多巡检多少个商品",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=_int_env("SALE_CHECK_LOOKBACK_DAYS", 7),
        help="只巡检最近 N 天抓取到的推荐商品",
    )
    parser.add_argument("--dry-run", action="store_true", help="只输出识别结果，不写数据库")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口（调试用）")
    args = parser.parse_args()

    asyncio.run(
        run_sale_check(
            limit=max(args.limit, 1),
            lookback_days=max(args.lookback_days, 1),
            dry_run=args.dry_run,
            headless=False if args.headed else None,
        )
    )


if __name__ == "__main__":
    main()
