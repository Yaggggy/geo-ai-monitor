import React, { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet-draw";

import "leaflet/dist/leaflet.css";
import "leaflet-draw/dist/leaflet.draw.css";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

// This is a robust component to handle the Leaflet Draw controls.
const DrawControl = ({ onBboxChange }) => {
  const map = useMap();
  const drawnItemsRef = useRef(new L.FeatureGroup());

  useEffect(() => {
    const drawnItems = drawnItemsRef.current;
    map.addLayer(drawnItems);

    const drawControl = new L.Control.Draw({
      position: "topright",
      draw: {
        polygon: false,
        marker: false,
        circle: false,
        polyline: false,
        circlemarker: false,
        rectangle: {
          shapeOptions: { color: "#3498db" },
          showArea: false, // Don't show area calculation on draw
        },
      },
      edit: {
        featureGroup: drawnItems,
      },
    });
    map.addControl(drawControl);

    const handleCreate = (e) => {
      drawnItems.clearLayers(); // Ensure only one shape can be drawn
      drawnItems.addLayer(e.layer);
      const bounds = e.layer.getBounds();
      onBboxChange([
        bounds.getWest(),
        bounds.getSouth(),
        bounds.getEast(),
        bounds.getNorth(),
      ]);
    };

    const handleEdit = (e) => {
      const layer = e.layers.getLayers()[0];
      if (layer) {
        const bounds = layer.getBounds();
        onBboxChange([
          bounds.getWest(),
          bounds.getSouth(),
          bounds.getEast(),
          bounds.getNorth(),
        ]);
      }
    };

    const handleDelete = () => {
      // When layers are deleted, drawnItems becomes empty
      onBboxChange(null);
    };

    map.on(L.Draw.Event.CREATED, handleCreate);
    map.on(L.Draw.Event.EDITED, handleEdit);
    map.on(L.Draw.Event.DELETED, handleDelete);

    // Cleanup function to remove controls and listeners when component unmounts
    return () => {
      map.removeControl(drawControl);
      map.removeLayer(drawnItems);
      map.off(L.Draw.Event.CREATED, handleCreate);
      map.off(L.Draw.Event.EDITED, handleEdit);
      map.off(L.Draw.Event.DELETED, handleDelete);
    };
  }, [map, onBboxChange]);

  return null;
};

function App() {
  const [bbox, setBbox] = useState(null);
  const [dates, setDates] = useState({ from: "", to: "" });
  const [taskId, setTaskId] = useState(null);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // This callback is passed to the DrawControl to update the state
  const handleBboxChange = useCallback((newBbox) => {
    setBbox(newBbox);
  }, []);

  // Polling logic to fetch results from the backend
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
    if (!bbox) {
      setError("Please draw a rectangle on the map to select an area.");
      return;
    }
    if (!dates.from || !dates.to) {
      setError("Please select both start and end dates.");
      return;
    }
    setError("");
    setLoading(true);
    setResults(null);
    try {
      const response = await axios.post(`${API_URL}/analyze`, {
        bbox: bbox,
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
          Use the tools on the map to draw, resize, or move your area of
          interest.
        </p>
      </header>
      <div className="content-wrapper">
        <div className="map-container">
          <MapContainer
            center={[28.9845, 77.7064]}
            zoom={10}
            className="leaflet-map"
          >
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution='&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors'
            />
            <DrawControl onBboxChange={handleBboxChange} />
          </MapContainer>
        </div>
        <div className="sidebar">
          <div className="controls">
            <h2>Controls</h2>
            <form onSubmit={handleSubmit}>
              <div className="date-picker">
                <label>From:</label>
                <input
                  type="date"
                  name="from"
                  onChange={(e) => setDates({ ...dates, from: e.target.value })}
                  required
                />
              </div>
              <div className="date-picker">
                <label>To:</label>
                <input
                  type="date"
                  name="to"
                  onChange={(e) => setDates({ ...dates, to: e.target.value })}
                  required
                />
              </div>
              <button type="submit" disabled={loading || !bbox}>
                {loading ? "Analyzing..." : "Analyze Selected Area"}
              </button>
            </form>
            {error && <p className="error">{error}</p>}
          </div>
          {loading && (
            <div className="loading-container">
              <div className="loading-spinner"></div>
              <p>Analyzing... This may take a moment.</p>
            </div>
          )}
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
                  A higher NDVI value (closer to 1) generally indicates
                  healthier, denser vegetation.
                </p>
              </div>
              <div className="image-container">
                <div className="image-card">
                  <h4>{results.from_date_str}</h4>
                  <img
                    src={results.image_from}
                    alt={`NDVI map for ${results.from_date_str}`}
                  />
                  <p>Mean NDVI: {results.mean_ndvi_from}</p>
                </div>
                <div className="image-card">
                  <h4>{results.to_date_str}</h4>
                  <img
                    src={results.image_to}
                    alt={`NDVI map for ${results.to_date_str}`}
                  />
                  <p>Mean NDVI: {results.mean_ndvi_to}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
