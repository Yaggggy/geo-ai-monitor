// frontend/src/App.jsx

import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { MapContainer, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "./App.css";

// Backend API URL - update this when you deploy
const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

function App() {
  const [dates, setDates] = useState({ from: "", to: "" });
  const [taskId, setTaskId] = useState(null);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const mapRef = useRef(null); // Create a ref to hold the map instance

  // This effect will poll for results when a task is running
  useEffect(() => {
    if (!taskId || loading === false) return;

    const interval = setInterval(async () => {
      try {
        const response = await axios.get(`${API_URL}/results/${taskId}`);
        if (response.data.status === "completed") {
          setResults(response.data.result);
          setLoading(false);
          setTaskId(null);
          clearInterval(interval);
        } else if (response.data.status === "failed") {
          setError(
            `Analysis failed: ${
              response.data.error ||
              "Please try a different area or date range."
            }`
          );
          setLoading(false);
          setTaskId(null);
          clearInterval(interval);
        }
      } catch (err) {
        setError("Could not fetch results.");
        setLoading(false);
        setTaskId(null);
        clearInterval(interval);
      }
    }, 5000); // Poll every 5 seconds

    return () => clearInterval(interval);
  }, [taskId, loading]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!mapRef.current) {
      setError("Map is not ready.");
      return;
    }
    if (!dates.from || !dates.to) {
      setError("Please select both start and end dates.");
      return;
    }

    // Get the bounding box from the current map view
    const bounds = mapRef.current.getBounds();
    const bboxArray = [
      bounds.getWest(),
      bounds.getSouth(),
      bounds.getEast(),
      bounds.getNorth(),
    ];

    setError("");
    setLoading(true);
    setResults(null);

    try {
      const response = await axios.post(`${API_URL}/analyze`, {
        bbox: bboxArray,
        from_date: dates.from,
        to_date: dates.to,
      });
      setTaskId(response.data.task_id);
    } catch (err) {
      setError("Failed to start analysis. Is the backend running?");
      setLoading(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Geospatial AI: Environmental Change Monitor</h1>
        <p>
          Pan and zoom the map to your area of interest, then click Analyze.
        </p>
      </header>
      <main>
        <div className="controls">
          <form onSubmit={handleSubmit}>
            <div className="date-picker">
              <label>
                From:{" "}
                <input
                  type="date"
                  name="from"
                  value={dates.from}
                  onChange={(e) => setDates({ ...dates, from: e.target.value })}
                  required
                />
              </label>
              <label>
                To:{" "}
                <input
                  type="date"
                  name="to"
                  value={dates.to}
                  onChange={(e) => setDates({ ...dates, to: e.target.value })}
                  required
                />
              </label>
            </div>
            <button type="submit" disabled={loading}>
              {loading ? "Analyzing..." : "Analyze Current Map View"}
            </button>
          </form>
          {error && <p className="error">{error}</p>}
        </div>

        <MapContainer
          center={[28.9845, 77.7064]} // Centered on Meerut, India
          zoom={10}
          style={{ height: "500px", width: "100%" }}
          ref={mapRef} // Attach the ref to the map container
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors'
          />
        </MapContainer>

        {loading && <div className="loading-spinner"></div>}

        {results && (
          <div className="results">
            <h2>Analysis Results</h2>
            <div className="result-summary">
              <h3>
                Change in Average NDVI:{" "}
                <span
                  className={
                    results.change_percentage >= 0 ? "positive" : "negative"
                  }
                >
                  {results.change_percentage}%
                </span>
              </h3>
              <p>
                A higher NDVI value (closer to 1) generally indicates healthier,
                denser vegetation.
              </p>
            </div>
            <div className="image-container">
              <div className="image-card">
                <h3>{results.from_date_str}</h3>
                <img
                  src={results.image_from}
                  alt={`NDVI map for ${results.from_date_str}`}
                />
                <p>Mean NDVI: {results.mean_ndvi_from}</p>
              </div>
              <div className="image-card">
                <h3>{results.to_date_str}</h3>
                <img
                  src={results.image_to}
                  alt={`NDVI map for ${results.to_date_str}`}
                />
                <p>Mean NDVI: {results.mean_ndvi_to}</p>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
