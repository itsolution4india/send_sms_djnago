import logging
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = None

def dummy_function():
    logger.info("Dummy function executed.")
    print("Dummy function executed.")

def scheduled_task():
    logger.info("Scheduler ran successfully.")
    dummy_function()

def start_scheduler():
    global scheduler
    if os.environ.get('RUN_MAIN') == 'true':
        if scheduler is None:
            scheduler = BackgroundScheduler()
            scheduler.add_job(scheduled_task, IntervalTrigger(minutes=1))
            scheduler.start()
            logger.info("Scheduler started successfully.")
