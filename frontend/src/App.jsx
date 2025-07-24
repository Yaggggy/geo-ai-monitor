// frontend/src/App.jsx
import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { MapContainer, TileLayer, FeatureGroup } from 'react-leaflet';
import { EditControl } from 'react-leaflet-draw';
import 'leaflet/dist/leaflet.css';
import 'leaflet-draw/dist/leaflet.draw.css';
import './App.css';

// Fix for leaflet-draw icon issue with React
import L from 'leaflet';
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});


// Backend API URL - update this when you deploy
const API_URL = 'http://127.0.0.1:8000';

function App() {
  const [bbox, setBbox] = useState(null);
  const [dates, setDates] = useState({ from: '', to: '' });
  const [taskId, setTaskId] = useState(null);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const featureGroupRef = useRef();

  // Polling effect to check for results
  useEffect(() => {
    if (!taskId || loading === false) return;

    const interval = setInterval(async () => {
      try {
        const response = await axios.get(`${API_URL}/results/${taskId}`);
        if (response.data.status === 'completed') {
          setResults(response.data.result);
          setLoading(false);
          setTaskId(null);
          clearInterval(interval);
        } else if (response.data.status === 'failed') {
          setError('Analysis failed. Please try a different area or date range.');
          setLoading(false);
          setTaskId(null);
          clearInterval(interval);
        }
      } catch (err) {
        setError('Could not fetch results.');
        setLoading(false);
        setTaskId(null);
        clearInterval(interval);
      }
    }, 5000); // Poll every 5 seconds

    return () => clearInterval(interval);
  }, [taskId, loading]);

  const onCreated = (e) => {
    const { layer } = e;
    const bounds = layer.getBounds();
    const bboxArray = [
      bounds.getWest(),
      bounds.getSouth(),
      bounds.getEast(),
      bounds.getNorth(),
    ];
    setBbox(bboxArray);
  };

  const onEdited = (e) => {
    const layer = e.layers.getLayers()[0];
    const bounds = layer.getBounds();
    const bboxArray = [
        bounds.getWest(),
        bounds.getSouth(),
        bounds.getEast(),
        bounds.getNorth(),
    ];
    setBbox(bboxArray);
  }

  const onDeleted = () => {
    setBbox(null);
  }

  const handleDateChange = (e) => {
    setDates({ ...dates, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!bbox || !dates.from || !dates.to) {
      setError('Please select an area on the map and both start and end dates.');
      return;
    }
    setError('');
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
      setError('Failed to start analysis.');
      setLoading(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Geospatial AI: Environmental Change Monitor</h1>
        <p>Draw a rectangle on the map and select a date range to analyze changes in vegetation.</p>
      </header>
      <main>
        <div className="controls">
          <form onSubmit={handleSubmit}>
            <div className="date-picker">
              <label>From: <input type="date" name="from" value={dates.from} onChange={handleDateChange} required /></label>
              <label>To: <input type="date" name="to" value={dates.to} onChange={handleDateChange} required /></label>
            </div>
            <button type="submit" disabled={loading || !bbox}>
              {loading ? 'Analyzing...' : 'Analyze Area'}
            </button>
          </form>
          {error && <p className="error">{error}</p>}
        </div>

        <MapContainer center={[28.9845, 77.7064]} zoom={10} style={{ height: '500px', width: '100%' }}>
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors'
          />
          <FeatureGroup ref={featureGroupRef}>
            <EditControl
              position="topright"
              onCreated={onCreated}
              onEdited={onEdited}
              onDeleted={onDeleted}
              draw={{
                rectangle: true,
                circle: false,
                polygon: false,
                polyline: false,
                marker: false,
                circlemarker: false,
              }}
              edit={{
                featureGroup: featureGroupRef.current,
                edit: true,
                remove: true,
              }}
            />
          </FeatureGroup>
        </MapContainer>

        {loading && <div className="loading-spinner"></div>}

        {results && (
          <div className="results">
            <h2>Analysis Results</h2>
            <div className="result-summary">
              <h3>Change in Average NDVI: <span className={results.change_percentage > 0 ? 'positive' : 'negative'}>{results.change_percentage}%</span></h3>
              <p>A higher NDVI value (closer to 1) generally indicates healthier, denser vegetation.</p>
            </div>
            <div className="image-container">
              <div className="image-card">
                <h3>{results.from_date_str}</h3>
                <img src={results.image_from} alt={`NDVI map for ${results.from_date_str}`} />
                <p>Mean NDVI: {results.mean_ndvi_from}</p>
              </div>
              <div className="image-card">
                <h3>{results.to_date_str}</h3>
                <img src={results.image_to} alt={`NDVI map for ${results.to_date_str}`} />
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