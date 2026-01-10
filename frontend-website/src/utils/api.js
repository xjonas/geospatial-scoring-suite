const API_BASE_URL = import.meta.env.VITE_NEIVO_API_BASE_URL;
const API_KEY = import.meta.env.VITE_NEIVO_API_KEY;

const METRICS = [
  'walkability',
  'healthcare_access',
  'green_space_access',
  'poi_access_overall',
  'crime_safety_living',
  'air_quality',
  'noise_pollution',
  'climate_change_resilience',
  'drought_resistance',
].join(',');

export const fetchLocationScores = async (latitude, longitude) => {
  try {
    const url = `${API_BASE_URL}/scores?lat=${latitude}&lon=${longitude}&metrics=${METRICS}`;
    const response = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${API_KEY}`,
        'Content-Type': 'application/json',
      }
    });

    if (!response.ok) {
      const errorStatus = response.status;
      const errorText = await response.text();
      console.error(`API error (${errorStatus}): ${errorText}`);

      if (errorStatus === 404) {
        throw new Error('LOCATION_NOT_FOUND');
      } else if (errorStatus === 429) {
        throw new Error('SERVER_LIMIT');
      } else if (errorStatus === 401) {
        throw new Error('UNAUTHORIZED');
      } else {
        throw new Error('API_ERROR');
      }
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching location scores:', error);
    throw error;
  }
};

export const fetchBulkScores = async (hexagons) => {
  try {
    const url = `${API_BASE_URL}/scores/bulk`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        hexagons: hexagons,
        metrics: METRICS.split(',')
      })
    });

    if (!response.ok) {
      const errorStatus = response.status;
      const errorText = await response.text();
      console.error(`Bulk API error (${errorStatus}): ${errorText}`);

      if (errorStatus === 429) {
        throw new Error('SERVER_LIMIT');
      } else if (errorStatus === 401) {
        throw new Error('UNAUTHORIZED');
      } else {
        throw new Error('API_ERROR');
      }
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching bulk scores:', error);
    throw error;
  }
};
