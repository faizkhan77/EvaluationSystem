"""
scheduler.py
=============
Continuous evaluation loop — runs inside Docker, replaces the Windows-only
run_evaluations.ps1.  On startup it runs one evaluation pass immediately, then
repeats every EVAL_INTERVAL_HOURS hours (default 1).

Logs go to stdout so `docker compose logs evaluation-runner-iris-india` shows
everything — no file I/O needed inside the container.

Manual one-off run (skips scheduler, runs once and exits):
    docker compose run --rm evaluation-runner-iris-india python run_evaluations.py --hours 24
"""
import logging
import logging.handlers
import os
import time
from pathlib import Path

import schedule
from dotenv import load_dotenv

load_dotenv()

from run_evaluations import run

_LOG_DIR = Path(os.environ.get("LOG_DIR", "/app/logs"))
_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Rotate daily, keep 7 days — older files are deleted automatically.
# Logs also go to stdout so `docker compose logs` still works.
_file_handler = logging.handlers.TimedRotatingFileHandler(
    _LOG_DIR / "run_evaluations.log",
    when="midnight",
    backupCount=7,
    encoding="utf-8",
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), _file_handler],
)
logger = logging.getLogger("scheduler")

INTERVAL_HOURS = int(os.environ.get("EVAL_INTERVAL_HOURS", "1"))
# How long to wait before retrying after a startup failure (seconds)
_STARTUP_RETRY_DELAY = int(os.environ.get("STARTUP_RETRY_DELAY", "30"))


def _run_safe() -> None:
    """Run one evaluation pass, catching all exceptions so the scheduler never crashes."""
    try:
        run()
    except Exception as exc:
        logger.error("[iris-india] Evaluation run failed: %s", exc, exc_info=True)


def main() -> None:
    logger.info(f"[iris-india] Evaluation scheduler started — interval={INTERVAL_HOURS}h")

    # Initial run — retry until Langfuse / backends are reachable
    while True:
        try:
            run()
            break  # success — exit retry loop
        except Exception as exc:
            logger.warning(
                "[iris-india] Startup run failed (%s). Retrying in %ds...",
                exc, _STARTUP_RETRY_DELAY,
            )
            time.sleep(_STARTUP_RETRY_DELAY)

    schedule.every(INTERVAL_HOURS).hours.do(_run_safe)
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
