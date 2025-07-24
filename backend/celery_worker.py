from backend.celery import celery_app

# This file is used to start the Celery worker with:
# celery -A backend.celery_worker.celery_app worker --loglevel=info
