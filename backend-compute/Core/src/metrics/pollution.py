"""
Implementation of the Pollution metric based on air quality data.
Uses a grid-based sampling approach to minimize API calls.
"""
import time
import pandas as pd
import numpy as np
import requests
from datetime import datetime
from src.metrics.base_metric import BaseMetric
from shapely.geometry import Point



class PollutionMetric(BaseMetric):
    """
    Metric that calculates air pollution scores based on multiple factors.
    Optimized for efficiency with Open-Meteo's 11km resolution data.
    """

    def __init__(self, weight=1.0, data_manager=None):
        """
        Initialize pollution metric.

        Parameters:
        -----------
        weight : float
            Weight of the metric in the final score
        data_manager : DataManager, optional
            Data manager instance for efficient data access
        """
        super().__init__("pollution", weight)
        self.data_manager = data_manager

        # API endpoint
        self.api_url = "https://air-quality-api.open-meteo.com/v1/air-quality"

        # Fixed time period (year 2023)
        self.start_date = "2023-01-01"
        self.end_date = "2023-12-31"

        # WHO thresholds based on 2021 guidelines
        self.who_thresholds = {
            "pm2_5": 15,            # Short-term guideline (24h)
            "pm10": 45,             # Short-term guideline (24h)
            "nitrogen_dioxide": 25,  # Short-term guideline (24h)
            "ozone": 100,           # 8-hour guideline
            "sulphur_dioxide": 40    # 24-hour guideline
        }

        # List of pollutants to request
        self.pollutants = [
            "european_aqi", "pm10", "pm2_5",
            "nitrogen_dioxide", "ozone", "sulphur_dioxide"
        ]

        # Resolution of Open-Meteo data in km
        self.resolution_km = 11

        # Cache for pollution data
        self.pollution_data_cache = {}

    def _generate_sampling_grid(self, bounds, crs):
        """
        Generate a grid of sampling points at Open-Meteo's resolution.

        Parameters:
        -----------
        bounds : tuple
            (minx, miny, maxx, maxy) bounds in the grid's CRS
        crs : CRS
            Coordinate reference system of the bounds

        Returns:
        --------
        list:
            List of (latitude, longitude) tuples for sampling points
        """
        from pyproj import Transformer

        # Extract bounds
        minx, miny, maxx, maxy = bounds

        # Create transformer to convert from grid CRS to WGS84
        transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

        # Calculate grid step size in meters (EPSG:3035 uses meters)
        # Open-Meteo resolution is 11km = 11,000 meters
        step_size = self.resolution_km * 1000  # 11,000 meters

        # Generate grid points
        sampling_points = []
        x = minx
        while x <= maxx:
            y = miny
            while y <= maxy:
                # Convert to WGS84 (lat, lon)
                lon, lat = transformer.transform(x, y)
                sampling_points.append((lat, lon))
                y += step_size
            x += step_size

        return sampling_points

    def _fetch_pollution_data(self, latitude, longitude):
        """
        Fetch air quality data for a specific location.
        Uses caching to avoid redundant API calls.

        Parameters:
        -----------
        latitude : float
            Location latitude
        longitude : float
            Location longitude

        Returns:
        --------
        pandas.DataFrame:
            DataFrame with hourly pollution data
        """
        # Round coordinates to reduce redundant API calls
        # 3 decimal places ≈ 111 meters at the equator
        cache_key = f"{round(latitude, 3)}_{round(longitude, 3)}"

        # Check memory cache first
        if cache_key in self.pollution_data_cache:
            return self.pollution_data_cache[cache_key]

        # Then check data manager cache if available
        if self.data_manager:
            cache_path = self.data_manager._get_cache_path(
                "processed", "", f"pollution_{cache_key}_{self.start_date}_{self.end_date}"
            )

            if self.data_manager._is_cache_valid(cache_path):
                result = self.data_manager._load_from_cache(cache_path)
                self.pollution_data_cache[cache_key] = result
                return result

        # Make API request
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "hourly": self.pollutants,
            "timezone": "auto"
        }

        try:
            response = requests.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Create DataFrame from API response
            hourly_time = pd.to_datetime(data['hourly']['time'])

            df = pd.DataFrame({'time': hourly_time})
            for pollutant in self.pollutants:
                if pollutant in data['hourly']:
                    df[pollutant] = data['hourly'][pollutant]

            # Calculate the result directly to avoid storing large dataframes
            result = self._process_pollution_data(df)

            # Store in memory cache
            self.pollution_data_cache[cache_key] = result

            # Store in data manager cache if available
            if self.data_manager:
                self.data_manager._save_to_cache(result, cache_path)

            return result

        except Exception as e:
            print(f"Error fetching pollution data for {latitude}, {longitude}: {e}")
            # Return default values
            return {
                "final_score": 50,
                "component_scores": {
                    "health_impact": 50,
                    "exceedance": 50,
                    "peak": 50
                },
                "pollutant_data": {},
                "has_data": False
            }

    def _process_pollution_data(self, df):
        """
        Process pollution data and calculate scores.

        Parameters:
        -----------
        df : pandas.DataFrame
            DataFrame with pollution data

        Returns:
        --------
        dict:
            Dictionary with scores and pollutant data
        """
        if df.empty:
            return {
                "final_score": 50,
                "component_scores": {
                    "health_impact": 50,
                    "exceedance": 50,
                    "peak": 50
                },
                "pollutant_data": {},
                "has_data": False
            }

        # Calculate median values for each pollutant
        pollutant_medians = {}
        for pollutant in self.pollutants:
            if pollutant in df.columns:
                pollutant_medians[pollutant] = df[pollutant].median()

        # 1. Calculate health impact score (50% of final score)
        # PM2.5 score (70% weight in health impact)
        pm25_median = pollutant_medians.get("pm2_5", 0)
        if pm25_median <= 5:
            pm25_score = 100
        elif pm25_median <= 10:
            pm25_score = 90 - ((pm25_median - 5) * 2)
        elif pm25_median <= 15:
            pm25_score = 80 - ((pm25_median - 10) * 2)
        elif pm25_median <= 25:
            pm25_score = 70 - ((pm25_median - 15) * 2.5)
        else:
            pm25_score = max(0.0, 45 - ((pm25_median - 25) * 1.5))

        # NO2 score (30% weight in health impact)
        no2_median = pollutant_medians.get("nitrogen_dioxide", 0)
        if no2_median <= 10:
            no2_score = 100
        elif no2_median <= 20:
            no2_score = 90 - ((no2_median - 10) * 1.5)
        elif no2_median <= 30:
            no2_score = 75 - ((no2_median - 20) * 1.5)
        elif no2_median <= 40:
            no2_score = 60 - ((no2_median - 30) * 1.5)
        else:
            no2_score = max(0.0, 45 - ((no2_median - 40) * 1.5))

        # Combined health impact score
        health_score = (pm25_score * 0.7) + (no2_score * 0.3)

        # 2. Calculate exceedance score (30% of final score)
        # Calculate daily maximums
        df['date'] = df['time'].dt.date
        daily_max = df.groupby('date').max()

        # Count exceedances
        exceedance_days = 0
        for pollutant, threshold in self.who_thresholds.items():
            if pollutant in daily_max.columns:
                exceedance_days += sum(daily_max[pollutant] > threshold)

        # Normalize
        exceedance_score = max(0, min(100, 100 - (exceedance_days / 3.65)))

        # 3. Calculate peak score (20% of final score)
        if 'european_aqi' in df.columns:
            # Calculate 95th percentile of AQI
            aqi_95th = np.percentile(df['european_aqi'].dropna(), 95)

            # Scale based on thresholds
            if aqi_95th <= 50:
                peak_score = 100 - (aqi_95th * 0.4)
            elif aqi_95th <= 100:
                peak_score = 80 - ((aqi_95th - 50) * 0.6)
            elif aqi_95th <= 150:
                peak_score = 50 - ((aqi_95th - 100) * 0.4)
            else:
                peak_score = max(0, 30 - ((aqi_95th - 150) * 0.2))
        else:
            peak_score = 50

        # Calculate final weighted score
        final_score = (
                (health_score * 0.5) +
                (exceedance_score * 0.3) +
                (peak_score * 0.2)
        )

        return {
            "final_score": round(final_score, 1),
            "component_scores": {
                "health_impact": round(health_score, 1),
                "exceedance": round(exceedance_score, 1),
                "peak": round(peak_score, 1)
            },
            "pollutant_data": pollutant_medians,
            "has_data": True
        }

    def _find_nearest_point(self, point, sampling_points_data):
        """
        Find the nearest sampling point with data.

        Parameters:
        -----------
        point : tuple
            (latitude, longitude) tuple
        sampling_points_data : dict
            Dictionary of sampling points and their data

        Returns:
        --------
        tuple:
            (nearest point key, distance)
        """
        lat, lon = point
        nearest_key = None
        min_distance = float('inf')

        for key in sampling_points_data:
            sample_lat, sample_lon = [float(x) for x in key.split('_')]

            # Simple Euclidean distance - for more accuracy, could use haversine
            distance = ((lat - sample_lat) ** 2 + (lon - sample_lon) ** 2) ** 0.5

            if distance < min_distance:
                min_distance = distance
                nearest_key = key

        return nearest_key, min_distance

    def calculate(self, grid_gdf, city_name=None):
        """
        Calculate pollution score for each hexagon in the grid.

        Parameters:
        -----------
        grid_gdf : GeoDataFrame
            Hexagon grid
        city_name : str, optional
            Name of the city (used for logging only)

        Returns:
        --------
        grid_gdf : GeoDataFrame
            Grid with added pollution score columns
        """
        print(f"Calculating Pollution metric for {city_name or 'unknown area'}...")
        start_time = time.time()

        # Make a copy of the grid to avoid modifying the original
        grid_gdf = grid_gdf.copy()

        # Ensure we have centroid data for calculations
        if 'centroid' not in grid_gdf.columns:
            grid_gdf['centroid'] = grid_gdf.geometry.centroid

        # Get bounds and CRS from the grid
        bounds = grid_gdf.total_bounds
        crs = grid_gdf.crs

        # Generate sampling grid at Open-Meteo's resolution
        print("Generating sampling grid...")
        sampling_points = self._generate_sampling_grid(bounds, crs)
        print(f"Generated {len(sampling_points)} sampling points at {self.resolution_km}km resolution")

        # Fetch pollution data for each sampling point
        print("Fetching pollution data for sampling points...")
        sampling_points_data = {}
        for i, (lat, lon) in enumerate(sampling_points):
            print(f"Fetching data for sampling point {i+1}/{len(sampling_points)}: ({lat:.4f}, {lon:.4f})")
            result = self._fetch_pollution_data(lat, lon)
            sampling_points_data[f"{lat}_{lon}"] = result

        # Initialize score columns
        grid_gdf[self.name] = 0.0
        grid_gdf[f"{self.name}_score"] = 0.0

        # Add columns for component scores
        for component in ["health_impact", "exceedance", "peak"]:
            grid_gdf[f"{self.name}_{component}"] = 0.0

        # Add columns for key pollutants
        for pollutant in ["pm2_5", "nitrogen_dioxide", "european_aqi"]:
            grid_gdf[f"{self.name}_{pollutant}"] = 0.0

        # Create function to convert points to lat/lon
        from pyproj import Transformer
        transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

        # Assign scores to hexagons
        print("Assigning pollution scores to hexagons...")
        for idx, hexagon in grid_gdf.iterrows():
            # Convert centroid to lat/lon
            centroid = hexagon.centroid
            lon, lat = transformer.transform(centroid.x, centroid.y)

            # Find nearest sampling point
            nearest_key, distance = self._find_nearest_point((lat, lon), sampling_points_data)
            result = sampling_points_data[nearest_key]

            # Store results in grid
            grid_gdf.at[idx, self.name] = result["final_score"]
            grid_gdf.at[idx, f"{self.name}_score"] = result["final_score"]

            # Store component scores
            for component, score in result["component_scores"].items():
                grid_gdf.at[idx, f"{self.name}_{component}"] = score

            # Store key pollutant data
            for pollutant in ["pm2_5", "nitrogen_dioxide", "european_aqi"]:
                if pollutant in result["pollutant_data"]:
                    grid_gdf.at[idx, f"{self.name}_{pollutant}"] = result["pollutant_data"][pollutant]

        print(f"Pollution score calculation complete. Total time: {time.time() - start_time:.2f} seconds")
        return grid_gdf