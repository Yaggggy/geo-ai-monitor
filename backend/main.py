# backend/main.py
import os
import uuid
from datetime import date
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Make sure geospatial.py is in the same directory
from geospatial import get_ndvi_change

# --- App Initialization ---
app = FastAPI(
    title="Geospatial AI Monitor API",
    description="An API to analyze vegetation change using Sentinel Hub data.",
    version="1.0.0"
)

# --- CORS Middleware ---
# This allows your React frontend to communicate with this backend.
# In a real production environment, you should restrict this to your frontend's domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# --- Pydantic Models ---
# Defines the structure of the incoming API request body.
class AnalysisRequest(BaseModel):
    bbox: list[float]  # Bounding box: [min_lon, min_lat, max_lon, max_lat]
    from_date: date
    to_date: date

# --- In-memory "database" for tracking task status ---
# A simple dictionary to store the state of each analysis task.
# For a production app, this would be replaced by a more robust solution like Redis or a database table.
tasks = {}

# --- Background Task Function ---
def run_analysis_and_store_results(task_id: str, bbox: list[float], from_date: str, to_date: str):
    """
    A wrapper function that runs the heavy geospatial analysis in the background.
    It updates the shared 'tasks' dictionary with the result or error.
    """
    print(f"Starting analysis for task: {task_id}")
    try:
        # Call the core function that communicates with Sentinel Hub
        result_data = get_ndvi_change(bbox, from_date, to_date)
        tasks[task_id] = {"status": "completed", "result": result_data}
        print(f"Task {task_id} completed successfully.")
    except Exception as e:
        # If anything goes wrong, store the error message
        print(f"Task {task_id} failed: {e}")
        tasks[task_id] = {"status": "failed", "error": str(e)}


# --- API Endpoints ---
@app.post("/analyze", status_code=202)
async def analyze_area(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """
    Accepts an analysis request, assigns it a unique task ID, and starts
    the processing in the background. Returns the task ID immediately.
    """
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing"}

    # Add the heavy lifting to FastAPI's background task queue
    background_tasks.add_task(
        run_analysis_and_store_results,
        task_id,
        request.bbox,
        request.from_date.isoformat(),
        request.to_date.isoformat()
    )

    return {"task_id": task_id, "status": "processing"}


@app.get("/results/{task_id}")
async def get_results(task_id: str):
    """
    Allows the frontend to poll for the result of a task using its ID.
    Returns the status and, if completed, the final analysis data.
    """
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/")
async def root():
    """
    A simple root endpoint to confirm the API is running.
    """
    return {"message": "Geospatial AI Monitor API is running."}