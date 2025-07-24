from celery import Celery
import os
from geospatial import get_analysis, NoDataAvailableException

# Load the Celery broker URL from environment or use default
redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")

# Handle Upstash SSL changes
if "upstash.io" in redis_url:
    if redis_url.startswith("redis://"):
        redis_url = redis_url.replace("redis://", "rediss://", 1)
    if "?ssl_cert_reqs" not in redis_url:
        redis_url += "?ssl_cert_reqs=none"

# Initialize Celery app
celery_app = Celery("tasks", broker=redis_url, backend=redis_url)

# Simulated task status storage (you can later use Redis or DB for persistent tracking)
tasks_db = {}

@celery_app.task
def run_analysis_task(task_id: str, bbox: list, from_date: str, to_date: str, analysis_type: str):
    """
    Celery task to perform geospatial analysis using SentinelHub.
    """
    global tasks_db
    tasks_db[task_id] = {"status": "processing"}
    print(f"Celery worker started analysis for task: {task_id}")

    try:
        result_data = get_analysis(bbox, from_date, to_date, analysis_type)
        tasks_db[task_id] = {
            "status": "completed",
            "result": result_data
        }
        print(f"Task {task_id} completed successfully.")
    except NoDataAvailableException as e:
        tasks_db[task_id] = {
            "status": "failed",
            "error": str(e)
        }
        print(f"Task {task_id} failed: {str(e)}")
    except Exception as e:
        tasks_db[task_id] = {
            "status": "failed",
            "error": "An unexpected server error occurred."
        }
        print(f"Task {task_id} failed due to unexpected error: {e}")

    return tasks_db[task_id]
