import React, { useState, useEffect, useRef } from "react";
import {
  MapContainer,
  TileLayer,
  FeatureGroup,
  Marker,
  Popup,
  useMapEvents,
} from "react-leaflet";
import { EditControl } from "react-leaflet-draw";
import "leaflet/dist/leaflet.css";
import "leaflet-draw/dist/leaflet.draw.css";
import "./App.css";

import L from "leaflet";
function LeafletIconFix() {
  useEffect(() => {
    if (L.Icon.Default.prototype._getIconUrl) {
      delete L.Icon.Default.prototype._getIconUrl;
    }
    L.Icon.Default.mergeOptions({
      iconRetinaUrl:
        "https://unpkg.com/leaflet@1.7.1/dist/images/marker-icon-2x.png",
      iconUrl: "https://unpkg.com/leaflet@1.7.1/dist/images/marker-icon.png",
      shadowUrl:
        "https://unpkg.com/leaflet@1.7.1/dist/images/marker-shadow.png",
    });
  }, []);
  return null;
}


const getCurrentYear = () => new Date().getFullYear();

const getDefaultPastYear = () => getCurrentYear() - 5;

function App() {
  const [mapCenter, setMapCenter] = useState([28.6139, 77.209]);
 
  const [startYear, setStartYear] = useState(getDefaultPastYear());
  const [endYear, setEndYear] = useState(getCurrentYear()); 
  const [llmResponse, setLlmResponse] = useState("");
  const [fetchedImageUrl1, setFetchedImageUrl1] = useState(""); 
  const [fetchedImageUrl2, setFetchedImageUrl2] = useState(""); 
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isCached, setIsCached] = useState(false); 

  const BACKEND_URL =
    process.env.REACT_APP_BACKEND_URL || "http://127.0.0.1:8000";

  const featureGroupRef = useRef(); 
 
    const { layerType, layer } = e;
    if (layerType === "rectangle") {
      const bounds = layer.getBounds();
      setDrawnBounds({
        north: bounds.getNorth(),
        south: bounds.getSouth(),
        east: bounds.getEast(),
        west: bounds.getWest(),
      });
 
      if (featureGroupRef.current) {
        featureGroupRef.current.clearLayers();
        featureGroupRef.current.addLayer(layer); 
      }
    }
    setLlmResponse(""); 
    setError(null);
    setIsCached(false);
    setFetchedImageUrl1("");
    setFetchedImageUrl2("");
  };

 
  const onEdited = (e) => {
    e.layers.eachLayer((layer) => {
      if (layer instanceof L.Rectangle) {
        const bounds = layer.getBounds();
        setDrawnBounds({
          north: bounds.getNorth(),
          south: bounds.getSouth(),
          east: bounds.getEast(),
          west: bounds.getWest(),
        });
      }
    });
    setLlmResponse("");
    setError(null);
    setIsCached(false);
    setFetchedImageUrl1("");
    setFetchedImageUrl2("");
  };

  const onDeleted = () => {
    setDrawnBounds(null);
    setLlmResponse("");
    setError(null);
    setIsCached(false);
    setFetchedImageUrl1("");
    setFetchedImageUrl2("");
  };

  const handleGenerateResponse = async () => {
    setLlmResponse("");
    setError(null);
    setIsCached(false);
    setFetchedImageUrl1("");
    setFetchedImageUrl2("");
    setIsLoading(true);

    if (!drawnBounds) {
      setError("Please draw a rectangle on the map first.");
      setIsLoading(false);
      return;
    }
    if (startYear > endYear) {
      setError("Start year cannot be after end year.");
      setIsLoading(false);
      return;
    }

    try {
      const startDateFull = `${startYear}-01-01`;
      const endDateFull = `${endYear}-01-01`;

      const payload = {
        bbox: drawnBounds,
        start_date: startDateFull,
        end_date: endDateFull,
       
      };

      const response = await fetch(`${BACKEND_URL}/generate-ai-response/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(
          `Backend error: ${response.status} - ${
            errorData.detail || "Unknown error"
          }`
        );
      }

      const result = await response.json();

      if (result.ai_response) {
        setLlmResponse(result.ai_response);
        setFetchedImageUrl1(result.image_url_1 || "");
        setFetchedImageUrl2(result.image_url_2 || "");
        setIsCached(result.cached);
      } else {
        setLlmResponse(
          "No content generated or unexpected response structure from backend."
        );
      }
    } catch (err) {
      console.error("Error generating response:", err);
      setError(
        `Failed to generate response: ${err.message}. Please ensure the backend is running, accessible, and your API keys are configured correctly.`
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      <LeafletIconFix />

      <h1 className="app-title">Geo AI Vision Explorer</h1>

      <div className="map-section-wrapper">
        <div className="map-container">
          <MapContainer
            center={mapCenter}
            zoom={6}
            scrollWheelZoom={true}
            className="leaflet-map"
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {}
            <FeatureGroup ref={featureGroupRef}>
              <EditControl
                position="topleft"
                onCreated={onCreated}
                onEdited={onEdited}
                onDeleted={onDeleted}
                draw={{
                  polyline: false,
                  polygon: false,
                  circle: false,
                  marker: false,
                  circlemarker: false,
                  rectangle: {
                    shapeOptions: {
                      color: "#2563eb", // Blue color for the rectangle
                      fillOpacity: 0.1,
                      weight: 2,
                    },
                  },
                }}
              />
            </FeatureGroup>
          </MapContainer>
        </div>
      </div>

      <div className="controls-section">
        <div className="location-display">
          <h2 className="section-title">Area of Interest (AOI):</h2>
          {drawnBounds ? (
            <p className="location-coords">
              N: {drawnBounds.north.toFixed(4)}, S:{" "}
              {drawnBounds.south.toFixed(4)}, <br />
              E: {drawnBounds.east.toFixed(4)}, W: {drawnBounds.west.toFixed(4)}
            </p>
          ) : (
            <p className="location-hint">
              Use the drawing tools (top-left of map) to draw a rectangle.
            </p>
          )}
        </div>

        {}
        <div className="date-selection-section">
          <h2 className="section-title">Select Years for Imagery:</h2>
          <p className="location-hint">
            Sentinel-2 imagery will be fetched for January 1st of these years.
          </p>
          <div className="date-input-group">
            <label htmlFor="start-year" className="date-label">
              Start Year:
            </label>
            <input
              type="number"
              id="start-year"
              className="date-input"
              value={startYear}
              onChange={(e) => setStartYear(parseInt(e.target.value))}
              min="2015"
              max={getCurrentYear()}
            />
            <label htmlFor="end-year" className="date-label">
              End Year:
            </label>
            <input
              type="number"
              id="end-year"
              className="date-input"
              value={endYear}
              onChange={(e) => setEndYear(parseInt(e.target.value))}
              min="2015"
              max={getCurrentYear()}
            />
          </div>
        </div>

        {}
        {}

        <button
          onClick={handleGenerateResponse}
          disabled={isLoading || !drawnBounds || startYear > endYear}
          className={`generate-button ${
            isLoading || !drawnBounds || startYear > endYear ? "disabled" : ""
          }`}
        >
          {isLoading ? (
            <div className="loading-spinner">
              <svg className="spinner-icon" viewBox="0 0 24 24">
                <circle
                  className="path"
                  cx="12"
                  cy="12"
                  r="10"
                  fill="none"
                  strokeWidth="4"
                ></circle>
                <path
                  className="fill"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                ></path>
              </svg>
              Analyzing...
            </div>
          ) : (
            "Analyze AOI with AI"
          )}
        </button>

        {error && (
          <div className="error-message">
            <p className="error-title">Error:</p>
            <p>{error}</p>
          </div>
        )}

        {llmResponse && (
          <div className="ai-response-section">
            <h2 className="section-title">
              AI Response {isCached && "(Cached)"}:
            </h2>
            {fetchedImageUrl1 && (
              <div className="fetched-images-preview">
                {fetchedImageUrl1 && (
                  <div className="image-preview-container">
                    <p>Image 1 ({startYear}):</p>
                    <img
                      src={fetchedImageUrl1}
                      alt={`Satellite Image ${startYear}`}
                      className="fetched-image"
                      onError={(e) =>
                        (e.target.src =
                          "https://placehold.co/150x150/e0e0e0/000000?text=Image+Load+Error")
                      }
                    />
                  </div>
                )}
                {fetchedImageUrl2 && (
                  <div className="image-preview-container">
                    <p>Image 2 ({endYear}):</p>
                    <img
                      src={fetchedImageUrl2}
                      alt={`Satellite Image ${endYear}`}
                      className="fetched-image"
                      onError={(e) =>
                        (e.target.src =
                          "https://placehold.co/150x150/e0e0e0/000000?text=Image+Load+Error")
                      }
                    />
                  </div>
                )}
              </div>
            )}
            <div className="ai-response-content">
              <p className="ai-response-text">{llmResponse}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
