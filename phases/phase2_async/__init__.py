from phases.phase2_async.worker import celery_app
from phases.phase2_async.tasks import ingest_task

__all__ = ["celery_app", "ingest_task"]