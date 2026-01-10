import * as h3 from 'h3-js';

/**
 * Get hexagons in rings around a center point
 * @param {number} lat - Center latitude
 * @param {number} lng - Center longitude
 * @param {number} resolution - H3 resolution (default 9)
 * @param {number} rings - Number of rings around center (default 3)
 * @returns {string[]} - Array of H3 hexagon IDs
 */
export const getHexagonsAroundPoint = (lat, lng, resolution = 9, rings = 4) => {
  try {
    const centerHex = h3.latLngToCell(lat, lng, resolution);
    const hexagons = [centerHex];
    
    for (let ring = 1; ring <= rings; ring++) {
      const ringHexagons = h3.gridRingUnsafe(centerHex, ring);
      hexagons.push(...ringHexagons);
    }
    
    return hexagons;
  } catch (error) {
    console.error('Error calculating hexagons:', error);
    return [];
  }
};

/**
 * Convert H3 hexagon to Leaflet polygon coordinates
 * @param {string} hexId - H3 hexagon ID
 * @returns {number[][]} - Array of [lat, lng] coordinates
 */
export const hexToPolygon = (hexId) => {
  try {
    const boundary = h3.cellToBoundary(hexId);
    return boundary;
  } catch (error) {
    console.error('Error converting hex to polygon:', error);
    return [];
  }
};

/**
 * Get color based on score value
 * @param {number} score - Score value (0-100)
 * @returns {string} - Hex color code
 */
export const getScoreColor = (score) => {
  if (score >= 80) return '#22c55e'; // Green
  if (score >= 60) return '#84cc16'; // Light green
  if (score >= 40) return '#eab308'; // Yellow
  if (score >= 20) return '#f97316'; // Orange
  return '#ef4444'; // Red
};

/**
 * Calculate average score for hexagon coloring
 * @param {Object} scores - Scores object
 * @returns {number} - Average score
 */
export const calculateAverageScore = (scores) => {
  const values = Object.values(scores).filter(v => typeof v === 'number');
  if (values.length === 0) return 0;
  return values.reduce((sum, val) => sum + val, 0) / values.length;
};
