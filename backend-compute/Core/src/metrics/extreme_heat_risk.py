"""
Implementation of the Extreme Heat Risk metric based on green space coverage and future temperature projections.
Uses the Open-Meteo Climate API with minimal API calls (10km resolution grid).
"""
import time
import requests
import numpy as np
import pandas as pd
from shapely.geometry import Point
from src.metrics.base_metric import BaseMetric
from config.settings import CHUNK_SIZE


class ExtremeHeatRiskMetric(BaseMetric):
    """
    Metric that calculates extreme heat risk based on two main factors:
    1. Green space coverage (already calculated in the grid)
    2. Projected temperature increases from climate models

    Higher scores indicate HIGHER risk (opposite of most other metrics)
    """

    def __init__(self, weight=1.0, data_manager=None):
        """
        Initialize extreme heat risk metric.

        Parameters:
        -----------
        weight : float
            Weight of the metric in the final score
        data_manager : DataManager, optional
            Data manager instance for efficient data access
        """
        super().__init__("extreme_heat_resistance", weight)
        self.data_manager = data_manager

        # OpenMeteo Climate API endpoint
        self.api_url = "https://climate-api.open-meteo.com/v1/climate"

        # Climate model to use
        self.model = "MPI_ESM1_2_XR"

        # Time period for future projection (2030-2040)
        self.start_date = "2030-01-01"
        self.end_date = "2040-12-31"

        # Temperature parameters to request
        self.daily_params = ["temperature_2m_mean", "temperature_2m_max"]

        # Resolution of data in km
        self.resolution_km = 10

        # Maximum grid points to minimize redundant API calls
        self.max_grid_points = 20  # 5x5 grid should cover most cities

        # Cache for temperature data
        self.temperature_data_cache = {}

        # Weights for the components of the heat risk score
        self.temp_rise_weight = 0.7     # 70% for temperature projections
        self.green_space_weight = 0.3    # 30% for green space (inverse relationship)

        # Temperature thresholds for risk scoring (in °C)
        # Based on scientific literature about heat stress thresholds
        self.mean_temp_thresholds = {
            16: 0,     # Below 16°C: No heat risk
            20: 20,    # 16-20°C: Low risk
            24: 40,    # 20-24°C: Moderate risk
            28: 70,    # 24-28°C: High risk
            32: 90,    # 28-32°C: Very high risk
            100: 100   # Above 32°C: Extreme risk
        }

        self.max_temp_thresholds = {
            25: 0,     # Below 25°C: No heat risk
            30: 20,    # 25-30°C: Low risk
            35: 50,    # 30-35°C: High risk
            40: 80,    # 35-40°C: Very high risk
            100: 100   # Above 40°C: Extreme risk
        }

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

        # Calculate grid step size in meters (using resolution_km)
        step_size = self.resolution_km * 1000  # Convert to meters

        # Calculate number of points needed in each dimension
        width = maxx - minx
        height = maxy - miny

        # Calculate number of points (max 5 in each direction to limit API calls)
        cols = min(5, max(2, int(width / step_size) + 1))
        rows = min(5, max(2, int(height / step_size) + 1))

        print(f"Creating sampling grid with {rows}x{cols} points ({rows*cols} total)")

        # Calculate total API calls that would be needed (1 call per lat/lon pair)
        total_api_calls = rows * cols
        print(f"This will require approximately {total_api_calls} API calls to Open-Meteo Climate API")

        # Generate grid points
        sampling_points = []
        for r in range(rows):
            for c in range(cols):
                # Calculate evenly distributed points
                x = minx + (c / max(1, cols-1)) * width
                y = miny + (r / max(1, rows-1)) * height

                # Convert to WGS84 (lat, lon)
                lon, lat = transformer.transform(x, y)
                sampling_points.append((lat, lon))

        return sampling_points

    def _fetch_temperature_data(self, latitude, longitude):
        """
        Fetch climate projection data for a specific location.
        Uses caching to avoid redundant API calls.

        Parameters:
        -----------
        latitude : float
            Location latitude
        longitude : float
            Location longitude

        Returns:
        --------
        dict:
            Dictionary with processed temperature data
        """
        # Round coordinates to reduce redundant API calls (0.01° ≈ 1km)
        cache_key = f"{round(latitude, 2)}_{round(longitude, 2)}"

        # Check memory cache first
        if cache_key in self.temperature_data_cache:
            return self.temperature_data_cache[cache_key]

        # Then check data manager cache if available
        if self.data_manager:
            cache_path = self.data_manager._get_cache_path(
                "processed", "", f"climate_{cache_key}_{self.start_date}_{self.end_date}"
            )

            if self.data_manager._is_cache_valid(cache_path):
                result = self.data_manager._load_from_cache(cache_path)
                self.temperature_data_cache[cache_key] = result
                return result

        # Make API request
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "daily": self.daily_params,
            "models": self.model,
            "temperature_unit": "celsius"
        }

        try:
            print("--------API CALL--------")
            print(f"Making Climate API call for coordinates: {latitude:.4f}, {longitude:.4f}")
            response = requests.get(self.api_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            # Process the data
            result = self._process_temperature_data(data)

            # Store in memory cache
            self.temperature_data_cache[cache_key] = result

            # Store in data manager cache if available
            if self.data_manager:
                self.data_manager._save_to_cache(result, cache_path)

            return result

        except Exception as e:
            print(f"Error fetching climate data for {latitude}, {longitude}: {e}")
            # Return default values
            return {
                "mean_temp": 20.0,
                "max_temp": 30.0,
                "mean_temp_score": 40,
                "max_temp_score": 20,
                "temp_rise_score": 30,
                "has_data": False
            }

    def _process_temperature_data(self, data):
        """
        Process temperature data from the API focusing on heat extremes.
        """
        if not data or "daily" not in data:
            return {
                "mean_temp": 20.0,
                "max_temp": 30.0,
                "hot_days_pct": 0,
                "temp_rise_score": 30,
                "has_data": False
            }

        # Extract temperature data
        try:
            # Mean temperature
            mean_temps = data["daily"]["temperature_2m_mean"]
            mean_temp = np.mean(mean_temps) if mean_temps else 20.0

            # Maximum temperature
            max_temps = data["daily"]["temperature_2m_max"]
            max_temp = np.mean(max_temps) if max_temps else 30.0

            # Calculate percentage of "hot days" (days over 25°C)
            hot_days = sum(1 for t in max_temps if t >= 25) if max_temps else 0
            hot_days_pct = (hot_days / len(max_temps) * 100) if max_temps else 0

            # Calculate "very hot days" (days over 30°C)
            very_hot_days = sum(1 for t in max_temps if t >= 30) if max_temps else 0
            very_hot_days_pct = (very_hot_days / len(max_temps) * 100) if max_temps else 0

            # Heat risk score based on frequency of hot days rather than absolute temperatures
            # Scientific literature suggests frequency of extremes is more important than averages
            if hot_days_pct >= 15:
                temp_rise_score = 70 + (very_hot_days_pct * 1.5)  # Higher score for more very hot days
            elif hot_days_pct >= 10:
                temp_rise_score = 50 + (hot_days_pct - 10) * 4
            elif hot_days_pct >= 5:
                temp_rise_score = 25 + (hot_days_pct - 5) * 5
            else:
                temp_rise_score = hot_days_pct * 5

            # Cap at 100
            temp_rise_score = min(100, temp_rise_score)

            return {
                "mean_temp": mean_temp,
                "max_temp": max_temp,
                "hot_days_pct": hot_days_pct,
                "very_hot_days_pct": very_hot_days_pct,
                "temp_rise_score": temp_rise_score,
                "has_data": True
            }

        except Exception as e:
            print(f"Error processing temperature data: {e}")
            return {
                "mean_temp": 20.0,
                "max_temp": 30.0,
                "hot_days_pct": 0,
                "temp_rise_score": 30,
                "has_data": False
            }

    def _score_from_thresholds(self, value, thresholds):
        """
        Calculate score based on thresholds.

        Parameters:
        -----------
        value : float
            Value to score
        thresholds : dict
            Dictionary of threshold:score pairs

        Returns:
        --------
        float:
            Score between 0-100
        """
        for threshold, score in sorted(thresholds.items()):
            if value <= threshold:
                return score

        # If value exceeds all thresholds
        return 100

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

            # Simple Euclidean distance (sufficient for this purpose)
            distance = ((lat - sample_lat) ** 2 + (lon - sample_lon) ** 2) ** 0.5

            if distance < min_distance:
                min_distance = distance
                nearest_key = key

        return nearest_key, min_distance

    def calculate(self, grid_gdf, city_name=None):
        """
        Calculate extreme heat risk score for each hexagon in the grid.

        Parameters:
        -----------
        grid_gdf : GeoDataFrame
            Hexagon grid
        city_name : str, optional
            Name of the city (used for logging only)

        Returns:
        --------
        grid_gdf : GeoDataFrame
            Grid with added extreme heat risk score columns
        """
        print(f"Calculating Extreme Heat Risk metric for {city_name or 'unknown area'}...")
        start_time = time.time()

        # Make a copy of the grid to avoid modifying the original
        grid_gdf = grid_gdf.copy()

        # Check if green space percentage is already calculated
        # This avoids redundant calculations and uses existing data
        has_green_data = False
        if 'green_percentage' in grid_gdf.columns:
            has_green_data = True
            print("Found existing green space percentage data - will use for heat risk")
        elif 'green_space' in grid_gdf.columns:
            has_green_data = True
            print("Found existing green space score data - will use for heat risk")
        else:
            print("No green space data found - this component will be excluded")
            self.temp_rise_weight = 1.0  # Only temperature data will be used
            self.green_space_weight = 0.0

        # Ensure we have centroid data for calculations
        if 'centroid' not in grid_gdf.columns:
            grid_gdf['centroid'] = grid_gdf.geometry.centroid

        # Get bounds and CRS from the grid
        bounds = grid_gdf.total_bounds
        crs = grid_gdf.crs

        # Generate sampling grid at specified resolution
        print("Generating sampling grid for climate data...")
        sampling_points = self._generate_sampling_grid(bounds, crs)
        print(f"Generated {len(sampling_points)} sampling points at {self.resolution_km}km resolution")

        # Fetch temperature data for each sampling point
        print("Fetching climate projection data for sampling points...")
        sampling_points_data = {}
        for i, (lat, lon) in enumerate(sampling_points):
            print(f"Processing point {i+1}/{len(sampling_points)}: ({lat:.4f}, {lon:.4f})")
            result = self._fetch_temperature_data(lat, lon)
            sampling_points_data[f"{lat}_{lon}"] = result

        # Initialize score columns
        grid_gdf[self.name] = 0.0
        grid_gdf[f"{self.name}_score"] = 0.0  # Keep consistent with other metrics
        grid_gdf[f"{self.name}_temp_rise"] = 0.0
        grid_gdf[f"{self.name}_green_factor"] = 0.0
        grid_gdf[f"{self.name}_mean_temp"] = 0.0
        grid_gdf[f"{self.name}_max_temp"] = 0.0

        # Create function to convert points to lat/lon
        from pyproj import Transformer
        transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

        # Assign scores to hexagons
        print("Assigning heat risk scores to hexagons...")
        for idx, hexagon in grid_gdf.iterrows():
            # Convert centroid to lat/lon
            centroid = hexagon.centroid
            lon, lat = transformer.transform(centroid.x, centroid.y)

            # Find nearest sampling point
            nearest_key, distance = self._find_nearest_point((lat, lon), sampling_points_data)
            result = sampling_points_data[nearest_key]

            # Calculate green space factor if data available
            green_factor = 0
            if has_green_data:
                if 'green_percentage' in grid_gdf.columns:
                    # Higher green percentage = lower risk (inverse relationship)
                    green_percentage = hexagon['green_percentage']
                    green_factor = 100 - min(100, green_percentage * 1.3)  # 67% green space or more is optimal (0 risk)
                elif 'green_space' in grid_gdf.columns:
                    # Convert green space score to risk factor (inverse)
                    green_factor = 100 - hexagon['green_space']

            # Combined score: Temperature rise (70%) + Green Space Factor (30%)
            temp_rise_score = result["temp_rise_score"]
            final_risk = (
                    temp_rise_score * self.temp_rise_weight +
                    green_factor * self.green_space_weight
            )

            # Invert score to get resistance score (higher = more resistant)
            resistance_score = 100 - final_risk
            #resistance_score = final_risk

            # Store results in grid
            grid_gdf.at[idx, f"{self.name}_temp_rise"] = temp_rise_score
            grid_gdf.at[idx, f"{self.name}_green_factor"] = green_factor
            grid_gdf.at[idx, f"{self.name}_mean_temp"] = result["mean_temp"]
            grid_gdf.at[idx, f"{self.name}_max_temp"] = result["max_temp"]
            grid_gdf.at[idx, self.name] = resistance_score
            grid_gdf.at[idx, f"{self.name}_score"] = resistance_score

        # Generate debug statistics
        print("\n----- Extreme Heat Risk Metric: DEBUG INFORMATION -----")
        print(f"Average Projected Mean Temperature: {grid_gdf[f'{self.name}_mean_temp'].mean():.2f}°C")
        print(f"Average Projected Max Temperature: {grid_gdf[f'{self.name}_max_temp'].mean():.2f}°C")


        print("\nIndividual sampling point data:")
        for i, (key, data) in enumerate(sampling_points_data.items()):
            lat, lon = key.split('_')
            print(f"  Point {i+1} ({lat}, {lon}):")
            print(f"    Mean Temp: {data['mean_temp']:.2f}°C")
            print(f"    Max Temp: {data['max_temp']:.2f}°C")

            # Check if the new fields exist in the data
            if 'hot_days_pct' in data:
                print(f"    Hot Days (>25°C): {data['hot_days_pct']:.1f}%")

            if 'very_hot_days_pct' in data:
                print(f"    Very Hot Days (>30°C): {data['very_hot_days_pct']:.1f}%")

            # Use a default key that should exist in all versions of the data
            temp_score_key = 'temp_rise_score' if 'temp_rise_score' in data else 'mean_temp_score'
            print(f"    Temperature Risk Score: {data[temp_score_key]:.1f}")

        print(f"\nTemperature Risk Score Range: {grid_gdf[f'{self.name}_temp_rise'].min():.1f} - {grid_gdf[f'{self.name}_temp_rise'].max():.1f}")

        if has_green_data:
            print(f"Green Factor Score Range: {grid_gdf[f'{self.name}_green_factor'].min():.1f} - {grid_gdf[f'{self.name}_green_factor'].max():.1f}")

        print(f"Final Heat Risk Score Range: {grid_gdf[self.name].min():.1f} - {grid_gdf[self.name].max():.1f}")
        print(f"Component weights used: Temperature {self.temp_rise_weight:.2f}, Green Space {self.green_space_weight:.2f}")

        print(f"Extreme heat risk calculation complete. Total time: {time.time() - start_time:.2f} seconds")
        return grid_gdf