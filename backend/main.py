# backend/main.py

import uuid
from datetime import date
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# Import the Celery app and the results database from the worker
from celery_worker import run_analysis_task, tasks_db

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

class AnalysisRequest(BaseModel):
    bbox: list[float]
    from_date: date
    to_date: date
    analysis_type: str # Add this new field

@app.post("/analyze", status_code=202)
async def analyze_area(request: AnalysisRequest):
    task_id = str(uuid.uuid4())
    # Send the task to the Celery worker
    run_analysis_task.delay(
        task_id, request.bbox, request.from_date.isoformat(), 
        request.to_date.isoformat(), request.analysis_type
    )
    return {"task_id": task_id, "status": "processing"}

@app.get("/results/{task_id}")
async def get_results(task_id: str):
    # Retrieve result from the shared dictionary managed by the worker
    task = tasks_db.get(task_id)
    if not task:
        # Check Celery's backend if not in our dict (more robust)
        task_result = run_analysis_task.AsyncResult(task_id)
        if task_result.state == 'PENDING':
             raise HTTPException(status_code=404, detail="Task not found")
        # You can build more complex logic here if needed
        return {"status": task_result.state}
        
    return task

# ... rest of your main.py ...