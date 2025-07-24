import os
import uuid
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from tasks import run_analysis_task, tasks_db

# Load environment variables from .env
load_dotenv()

# FastAPI App
app = FastAPI()

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this to your frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request schema
class AnalysisRequest(BaseModel):
    bbox: list  # [minLon, minLat, maxLon, maxLat]
    from_date: str  # "YYYY-MM-DD"
    to_date: str    # "YYYY-MM-DD"
    analysis_type: str  # e.g., "ndvi", "ndwi", etc.

# Root route
@app.get("/")
def root():
    return {"message": "Geospatial API is running 🚀"}

# Submit analysis task
@app.post("/analyze")
def submit_analysis(request: AnalysisRequest):
    task_id = str(uuid.uuid4())
    tasks_db[task_id] = {"status": "queued"}
    run_analysis_task.delay(task_id, request.bbox, request.from_date, request.to_date, request.analysis_type)
    return {"task_id": task_id, "status": "queued"}

# Check task status
@app.get("/status/{task_id}")
def get_task_status(task_id: str):
    task_info = tasks_db.get(task_id)
    if not task_info:
        raise HTTPException(status_code=404, detail="Task ID not found")
    return task_info
