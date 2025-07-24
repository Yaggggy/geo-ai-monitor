# backend/celery_worker.py

from celery import Celery
import os
from geospatial import get_analysis  # We will rename get_ndvi_change later

# Configure Celery
# Replace with your Upstash Redis URL in an environment variable for production
redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
celery_app = Celery("tasks", broker=redis_url, backend=redis_url)

# This dictionary will be our in-memory "database" for results.
# In a real app, the worker would write results to a proper database.
tasks_db = {}

@celery_app.task
def run_analysis_task(task_id: str, bbox: list, from_date: str, to_date: str, analysis_type: str):
    """
    This is the Celery task that performs the heavy lifting.
    It updates a shared dictionary with the status and result.
    """
    global tasks_db
    tasks_db[task_id] = {"status": "processing"}
    try:
        result_data = get_analysis(bbox, from_date, to_date, analysis_type)
        tasks_db[task_id] = {"status": "completed", "result": result_data}
    except Exception as e:
        tasks_db[task_id] = {"status": "failed", "error": str(e)}
    return tasks_db[task_id]