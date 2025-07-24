# backend/main.py
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import date
import uuid

app = FastAPI()

# --- CORS Middleware ---
# This allows your React frontend to communicate with your backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, change "*" to your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models ---
# Defines the structure of the request body
class AnalysisRequest(BaseModel):
    bbox: list[float] # Bounding box: [min_lon, min_lat, max_lon, max_lat]
    from_date: date
    to_date: date

# --- In-memory "database" for task tracking ---
# In a real app, you'd use a proper database like Postgres/Redis here.
tasks = {}

# Placeholder for the real analysis function
def perform_ndvi_analysis(task_id: str, bbox: list[float], from_date: str, to_date: str):
    print(f"Starting analysis for task {task_id}...")
    # Simulate a long-running task
    import time
    time.sleep(15)

    # In the next step, we'll replace this with real analysis
    result_data = {
        "from_date_str": from_date,
        "to_date_str": to_date,
        "mean_ndvi_from": 0.65, # Dummy data
        "mean_ndvi_to": 0.45,   # Dummy data
        "change_percentage": -30.7,
        # We'll also add image data later
    }

    tasks[task_id] = {"status": "completed", "result": result_data}
    print(f"Task {task_id} completed.")


# --- API Endpoints ---
@app.post("/analyze")
async def analyze_area(request: AnalysisRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing"}

    # Add the long-running analysis to the background
    background_tasks.add_task(
        perform_ndvi_analysis,
        task_id,
        request.bbox,
        request.from_date.isoformat(),
        request.to_date.isoformat()
    )

    return {"task_id": task_id, "status": "processing"}


@app.get("/results/{task_id}")
async def get_results(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task