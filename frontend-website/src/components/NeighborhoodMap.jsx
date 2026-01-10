import { fetchBulkScores } from '../utils/api';

import { useState, useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, Polygon, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { getHexagonsAroundPoint, hexToPolygon, getScoreColor, calculateAverageScore } from '../utils/mapUtils';

// Fix for default markers in react-leaflet
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

const SCORE_METRICS = {
  walkability: 'Walkability',
  healthcare_access: 'Gesundheitsversorgung',
  green_space_access: 'Grünflächenzugang',
  poi_access_overall: 'Point of Interests',
  crime_safety_living: 'Sicherheit',
  air_quality: 'Luftqualität',
  noise_pollution: 'Lärmbelästigung',
  climate_change_resilience: 'Klimawandelresilienz',
  drought_resistance: 'Dürreresistenz'
};

const NeighborhoodMap = ({ centerLat, centerLng, city }) => {
  const [hexagonData, setHexagonData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [visibleMetrics, setVisibleMetrics] = useState(new Set(['walkability']));

  // Get hexagons around the center point
  const hexagons = useMemo(() => {
    return getHexagonsAroundPoint(centerLat, centerLng, 9, 3);
  }, [centerLat, centerLng]);

  // Load hexagon data
  useEffect(() => {
    const loadHexagonData = async () => {
      if (hexagons.length === 0) return;
      
      setLoading(true);
      setError('');
      
      try {
        const response = await fetchBulkScores(hexagons);
        const dataMap = {};
        
        response.results.forEach(result => {
          if (result.status === 'success') {
            dataMap[result.hexagon_id] = result;
          }
        });
        
        setHexagonData(dataMap);
      } catch (err) {
        console.error('Error loading hexagon data:', err);
        setError('Failed to load neighborhood data');
      } finally {
        setLoading(false);
      }
    };

    loadHexagonData();
  }, [hexagons]);

  // Toggle metric visibility
  const toggleMetric = (metric) => {
    const newVisible = new Set(visibleMetrics);
    if (newVisible.has(metric)) {
      newVisible.delete(metric);
    } else {
      newVisible.add(metric);
    }
    setVisibleMetrics(newVisible);
  };

  // Render hexagon polygons
  const renderHexagons = () => {
    return hexagons.map(hexId => {
      const data = hexagonData[hexId];
      if (!data) return null;

      const polygon = hexToPolygon(hexId);
      if (polygon.length === 0) return null;

      // Get scores for visible metrics
      const visibleScores = {};
      visibleMetrics.forEach(metric => {
        if (data[metric] !== undefined) {
          visibleScores[metric] = data[metric];
        }
      });

      if (Object.keys(visibleScores).length === 0) return null;

      const avgScore = calculateAverageScore(visibleScores);
      const color = getScoreColor(avgScore);

      return (
        <Polygon
          key={hexId}
          positions={polygon}
          pathOptions={{
            fillColor: color,
            fillOpacity: 0.6,
            color: color,
            weight: 2,
            opacity: 0.8
          }}
        >
          <Popup>
            <div className="text-sm">
              <div className="font-semibold mb-2">{data.city_name || 'Unknown'}</div>
              {Object.entries(visibleScores).map(([metric, score]) => (
                <div key={metric} className="flex justify-between">
                  <span>{SCORE_METRICS[metric]}:</span>
                  <span className="font-medium">{score}</span>
                </div>
              ))}
            </div>
          </Popup>
        </Polygon>
      );
    });
  };

  if (loading) {
    return (
      <div className="neighborhood-map-container">
        <div className="map-header">
          <h3 className="text-xl font-semibold mb-2">Map Übersicht</h3>
          <p className="text-gray-600 text-sm mb-4">Loading neighborhood data...</p>
        </div>
        <div className="map-loading">
          <div className="animate-pulse bg-gray-200 rounded-lg h-96"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="neighborhood-map-container">
        <div className="map-header">
          <h3 className="text-xl font-semibold mb-2">Map Übersicht</h3>
          <p className="text-red-600 text-sm">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="neighborhood-map-container">
      <div className="map-header">
        <h2 className="text-2xl font-semibold mb-6">Map Übersicht - {city}</h2>
        <p className="text-gray-600 text-sm mb-4">
          Erkunden Sie die Scores in der Umgebung. Schalten Sie die Metriken ein/aus, um die Ansicht anzupassen.
        </p>
      </div>

      {/* Metric Controls */}
      <div className="metric-controls">
        <div className="metric-toggles">
          {Object.entries(SCORE_METRICS).map(([key, label]) => (
            <button
              key={key}
              onClick={() => toggleMetric(key)}
              className={`metric-toggle ${visibleMetrics.has(key) ? 'active' : ''}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Map */}
      <div className="map-wrapper">
        <MapContainer
          center={[centerLat, centerLng]}
          zoom={14}
          className="neighborhood-map"
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          
          {/* Center marker */}
          <Marker position={[centerLat, centerLng]}>
            <Popup>
              <div className="text-sm font-medium">Your Location</div>
            </Popup>
          </Marker>
          
          {/* Hexagon overlays */}
          {renderHexagons()}
        </MapContainer>
      </div>

      {/* Legend */}
      <div className="map-legend">
        <div className="legend-title">Score Range:</div>
        <div className="legend-items">
          <div className="legend-item">
            <div className="legend-color" style={{ backgroundColor: '#22c55e' }}></div>
            <span>80-100</span>
          </div>
          <div className="legend-item">
            <div className="legend-color" style={{ backgroundColor: '#84cc16' }}></div>
            <span>60-79</span>
          </div>
          <div className="legend-item">
            <div className="legend-color" style={{ backgroundColor: '#eab308' }}></div>
            <span>40-59</span>
          </div>
          <div className="legend-item">
            <div className="legend-color" style={{ backgroundColor: '#f97316' }}></div>
            <span>20-39</span>
          </div>
          <div className="legend-item">
            <div className="legend-color" style={{ backgroundColor: '#ef4444' }}></div>
            <span>0-19</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default NeighborhoodMap;
