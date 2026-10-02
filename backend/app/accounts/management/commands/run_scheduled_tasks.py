"""In-process scheduler.

django-crontab entries are never installed by the container entrypoint, so the
credential refresh it declares silently does nothing in Docker. This worker
replaces it and adds the nightly cleanup.
"""
import logging
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from app.accounts.maintenance import cleanup_expired_data
from app.accounts.sessions import promote_waiting, release_expired_slots
from app.cron import check_access_token, update_access_token

logger = logging.getLogger("cron")

DEFAULT_POLL_SECONDS = 30
DEFAULT_TOKEN_INTERVAL_SECONDS = 300
DEFAULT_CLEANUP_HOUR = 3


class Command(BaseCommand):
    help = "常驻进程：定时刷新上游凭据，并在每天凌晨清理过期数据"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="执行一轮后退出，便于手工或外部调度调用")
        parser.add_argument("--poll", type=int, default=DEFAULT_POLL_SECONDS, help="轮询间隔秒数")
        parser.add_argument(
            "--token-interval", type=int, default=DEFAULT_TOKEN_INTERVAL_SECONDS,
            help="刷新上游凭据的间隔秒数",
        )
        parser.add_argument("--cleanup-hour", type=int, default=DEFAULT_CLEANUP_HOUR, help="每天执行清理的本地小时")

    def handle(self, *args, **options):
        self.poll = max(1, options["poll"])
        self.token_interval = max(1, options["token_interval"])
        self.cleanup_hour = min(23, max(0, options["cleanup_hour"]))
        self.last_token_refresh = 0.0
        self.last_cleanup_date = None

        self.refresh_credentials()
        self.sweep_sessions()
        self.cleanup_if_due()
        if options["once"]:
            return

        while True:
            time.sleep(self.poll)
            self.refresh_credentials()
            self.sweep_sessions()
            self.cleanup_if_due()

    def sweep_sessions(self):
        """Idle seats free up on the poll interval so the queue keeps moving."""
        try:
            if release_expired_slots():
                promote_waiting()
        except Exception:
            logger.exception("回收空闲会话失败")

    def refresh_credentials(self):
        if time.monotonic() - self.last_token_refresh < self.token_interval:
            return
        self.last_token_refresh = time.monotonic()
        jobs = (("check_access_token", check_access_token), ("update_access_token", update_access_token))
        for name, job in jobs:
            try:
                job()
            except Exception:
                logger.exception("定时刷新上游凭据失败: %s", name)

    def cleanup_if_due(self):
        today = timezone.localdate()
        if timezone.localtime().hour < self.cleanup_hour or self.last_cleanup_date == today:
            return
        self.last_cleanup_date = today
        try:
            counts = cleanup_expired_data()
        except Exception:
            logger.exception("夜间清理失败")
            return
        logger.info("夜间清理完成: %s", counts)
