"""
调度服务
负责管理定时任务的调度
"""
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from typing import List

from src.core.cron_utils import build_cron_trigger
from src.domain.models.task import Task
from src.services.process_service import ProcessService
from src.services.sale_check_config import (
    SALE_CHECK_BATCH_SIZE,
    SALE_CHECK_CRON,
    SALE_CHECK_ENABLED,
    SALE_CHECK_LOOKBACK_DAYS,
    load_sale_check_config,
)


SALE_CHECK_JOB_ID = "system:sale_check"


class SchedulerService:
    """调度服务"""

    def __init__(self, process_service: ProcessService):
        self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        self.process_service = process_service

    def start(self):
        """启动调度器"""
        if not self.scheduler.running:
            self.scheduler.start()
            print("调度器已启动")
            self._ensure_sale_check_job()

    def stop(self):
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            print("调度器已停止")

    def get_next_run_time(self, task_id: int):
        job = self.scheduler.get_job(f"task_{task_id}")
        if job is None:
            return None

        next_run_time = getattr(job, "next_run_time", None)
        if next_run_time is not None:
            return next_run_time

        trigger = getattr(job, "trigger", None)
        if trigger is None or not hasattr(trigger, "get_next_fire_time"):
            return None

        try:
            now = datetime.now(self.scheduler.timezone)
            return trigger.get_next_fire_time(None, now)
        except Exception:
            return None

    async def reload_jobs(self, tasks: List[Task]):
        """重新加载所有定时任务"""
        print("正在重新加载定时任务...")
        for job in self.scheduler.get_jobs():
            if job.id.startswith("task_"):
                self.scheduler.remove_job(job.id)

        for task in tasks:
            if task.enabled and task.cron:
                try:
                    trigger = build_cron_trigger(
                        task.cron,
                        timezone=self.scheduler.timezone,
                    )
                    self.scheduler.add_job(
                        self._run_task,
                        trigger=trigger,
                        args=[task.id, task.task_name],
                        id=f"task_{task.id}",
                        name=f"Scheduled: {task.task_name}",
                        replace_existing=True
                    )
                    print(f"  -> 已为任务 '{task.task_name}' 添加定时规则: '{task.cron}'")
                except ValueError as e:
                    print(f"  -> [警告] 任务 '{task.task_name}' 的 Cron 表达式无效: {e}")

        print("定时任务加载完成")

    def _ensure_sale_check_job(self) -> None:
        """注册商品售卖状态巡检的后台任务（不受任务重载影响）。"""
        config = load_sale_check_config()
        if not config[SALE_CHECK_ENABLED]:
            print("商品状态巡检已禁用 (SALE_CHECK_ENABLED=false)")
            return
        cron = config[SALE_CHECK_CRON]
        try:
            trigger = build_cron_trigger(cron, timezone=self.scheduler.timezone)
        except ValueError as exc:
            print(f"[警告] SALE_CHECK_CRON 无效: {cron} ({exc})")
            return
        self.scheduler.add_job(
            self._run_sale_check,
            trigger=trigger,
            id=SALE_CHECK_JOB_ID,
            name="System: sale check",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        print(f"已启用商品状态巡检: '{cron}'")

    def reload_sale_check_job(self) -> None:
        """按最新配置重建巡检任务（关闭时移除）。"""
        if self.scheduler.get_job(SALE_CHECK_JOB_ID) is not None:
            self.scheduler.remove_job(SALE_CHECK_JOB_ID)
        self._ensure_sale_check_job()

    def get_sale_check_next_run_time(self) -> str | None:
        job = self.scheduler.get_job(SALE_CHECK_JOB_ID)
        next_run = getattr(job, "next_run_time", None) if job else None
        return next_run.isoformat() if next_run else None

    def _has_running_tasks(self) -> bool:
        return any(
            process.returncode is None
            for process in self.process_service.processes.values()
        )

    async def _run_sale_check(self) -> None:
        if self._has_running_tasks():
            print("有爬虫任务正在运行，跳过本轮商品状态巡检")
            return

        config = load_sale_check_config()
        limit = max(int(config[SALE_CHECK_BATCH_SIZE]), 1)
        lookback_days = max(int(config[SALE_CHECK_LOOKBACK_DAYS]), 1)

        from src.services.sale_check_service import spawn_sale_check

        pid = await spawn_sale_check(limit, lookback_days)
        if pid is None:
            print("已有商品状态巡检在运行，跳过本轮")
            return
        print(f"商品状态巡检已启动 (PID: {pid})")

    async def _run_task(self, task_id: int, task_name: str):
        """执行定时任务"""
        print(f"定时任务触发: 正在为任务 '{task_name}' 启动爬虫...")
        await self.process_service.start_task(task_id, task_name)
