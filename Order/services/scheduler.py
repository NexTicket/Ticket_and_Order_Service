"""
Task Scheduler for Order Service
This module initializes and manages background scheduled tasks for the order service.
"""

import logging
import threading
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from Order.services.order_cleanup_service import cleanup_expired_orders

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create scheduler
scheduler = BackgroundScheduler()

def init_scheduled_tasks():
    """Initialize all scheduled tasks"""
    logger.info("Initializing scheduled tasks")
    
    # Add job to clean up expired orders every minute
    scheduler.add_job(
        func=cleanup_expired_orders,
        trigger=IntervalTrigger(minutes=1),
        id='cleanup_expired_orders',
        name='Cleanup expired orders',
        replace_existing=True
    )
    
    # Start the scheduler if it's not already running
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")
    
    return scheduler

def shutdown_scheduler():
    """Shutdown the scheduler gracefully"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shut down")

# For manual testing
if __name__ == "__main__":
    print("Starting scheduler test...")
    init_scheduled_tasks()
    
    try:
        # Keep the main thread alive
        while True:
            print(f"[{datetime.now()}] Scheduler is running...")
            time.sleep(60)  # Sleep for 60 seconds
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down scheduler...")
        shutdown_scheduler()