"""Job scheduler (APScheduler). The day-ahead auction closes at 12:00 CET;
the pipeline is scheduled at 10:30 Europe/Berlin (configurable) leaving a
90-minute buffer for review and bid submission. Misfires are coalesced and
a run is never executed twice in parallel."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import get_settings
from .log import get_logger
from .timeutils import TZ

log = get_logger("scheduler")


def _job() -> None:
    from .pipeline import run_pipeline

    try:
        run_pipeline()
    except Exception as exc:  # already logged + recorded in pipeline_runs
        log.error("scheduled run failed: %s", exc)


def _trigger() -> CronTrigger:
    s = get_settings()
    return CronTrigger(hour=s.scheduler_hour, minute=s.scheduler_minute, timezone=TZ)


def start_background() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=TZ)
    sched.add_job(_job, _trigger(), id="daily_pipeline", max_instances=1, coalesce=True,
                  misfire_grace_time=3600, replace_existing=True)
    sched.start()
    log.info("background scheduler started: %s", sched.get_job("daily_pipeline").next_run_time)
    return sched


def run_forever() -> None:
    sched = BlockingScheduler(timezone=TZ)
    sched.add_job(_job, _trigger(), id="daily_pipeline", max_instances=1, coalesce=True,
                  misfire_grace_time=3600)
    log.info("scheduler running — next: %s", _trigger())
    sched.start()
