import logging
import os

from celery import Celery, signals
from dotenv import load_dotenv
from kombu import Exchange, Queue

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Define exchanges
default_exchange = Exchange("default", type="direct")
dead_letter_exchange = Exchange("dead_letter", type="direct")

# Define queues with dead letter routing
default_queue = Queue(
    "celery",
    exchange=default_exchange,
    routing_key="celery",
    queue_arguments={
        "x-dead-letter-exchange": "dead_letter",
        "x-dead-letter-routing-key": "dead_letter",
    },
)

dead_letter_queue = Queue(
    "dead_letter",
    exchange=dead_letter_exchange,
    routing_key="dead_letter",
)

celery_app = Celery(
    "meeting_intelligence",
    broker=redis_url,
    backend=redis_url,
    include=["workers.tasks"],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task tracking
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3300,  # Soft limit at 55 minutes

    # Worker settings
    worker_prefetch_multiplier=1,  # Process one task at a time (ML tasks are heavy)

    # Reliability
    task_acks_late=True,  # Acknowledge after task completes
    task_reject_on_worker_lost=True,

    # Dead letter queue
    task_queues=[default_queue, dead_letter_queue],
    task_default_queue="celery",
    task_default_exchange="default",
    task_default_routing_key="celery",

    # Store failed task info
    task_store_errors_even_if_ignored=True,
)


@signals.task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None,
                        args=None, kwargs=None, traceback=None, einfo=None, **kw):
    """
    Handle task failures after all retries are exhausted.
    Logs the failure and stores it for later inspection.
    """
    logger.error(
        f"Task {sender.name}[{task_id}] failed permanently after all retries. "
        f"Args: {args}, Kwargs: {kwargs}, Exception: {exception}"
    )

    # Store failed task info in Redis for later inspection
    try:
        import json
        import redis

        r = redis.from_url(redis_url)
        failed_task = {
            "task_id": task_id,
            "task_name": sender.name,
            "args": args,
            "kwargs": kwargs,
            "exception": str(exception),
            "traceback": str(einfo) if einfo else None,
        }
        r.lpush("failed_tasks", json.dumps(failed_task))
        r.ltrim("failed_tasks", 0, 999)  # Keep last 1000 failed tasks
        logger.info(f"Failed task {task_id} stored in dead letter queue")
    except Exception as e:
        logger.error(f"Could not store failed task in Redis: {e}")


@signals.task_retry.connect
def handle_task_retry(sender=None, reason=None, request=None, **kw):
    """Log task retry attempts."""
    logger.warning(
        f"Task {sender.name}[{request.id}] retrying: {reason}"
    )
