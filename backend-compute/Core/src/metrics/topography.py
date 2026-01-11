
import time
import requests
import numpy as np
import pandas as pd
from shapely.geometry import Point
from src.metrics.base_metric import BaseMetric
from scipy.interpolate import RegularGridInterpolator


class TopographyMetric(BaseMetric):
    """
    Metric that evaluates terrain steepness for walkability.
    Uses OpenMeteo elevation API to get elevation data at 90m resolution.
    """

    def __init__(self, weight=1.0, data_manager=None):

        super().__init__("topography", weight)
        self.data_manager = data_manager

        # OpenMeteo Elevation API endpoint
        self.api_url = "https://api.open-meteo.com/v1/elevation"

        # Resolution of OpenMeteo elevation data in meters
        self.resolution = 90

        # Maximum number of points per API call (OpenMeteo limit)
        self.max_points_per_call = 100

        # Batch size for hexagon processing to improve memory efficiency
        self.batch_size = 100

        # Slope thresholds in percentage and corresponding scores
        self.slope_scores = {
            2: 100,  
            5: 90,     
            8: 75,     
            10: 60,    
            15: 40,    
            20: 20,    
            25: 10,    
            100: 0     
        }

    def _generate_sampling_grid(self, bounds, resolution_m):
        # Generate a regular sampling grid for the entire region.    
        minx, miny, maxx, maxy = bounds

        # Calculate number of points
        width = maxx - minx
        height = maxy - miny

        # Calculate rows and columns (with one extra point to ensure coverage)
        cols = max(3, int(width / resolution_m) + 1)
        rows = max(3, int(height / resolution_m) + 1)

        # Limit total points to avoid excessive API calls
        total_points = cols * rows
        if total_points > 400:  # Arbitrary limit for memory
            scale_factor = np.sqrt(400 / total_points)
            cols = max(3, int(cols * scale_factor))
            rows = max(3, int(rows * scale_factor))

        # Generate grid coordinates
        x_coords = np.linspace(minx, maxx, cols)
        y_coords = np.linspace(miny, maxy, rows)

        # Create all grid points as tuples
        sampling_points = []
        for y in y_coords:
            for x in x_coords:
                sampling_points.append((x, y))

        return x_coords, y_coords, sampling_points

    def _fetch_elevations_batch(self, coords_list, city_name=None):
        # Fetch elevations for a list of coordinates in batches

        # Check if we can retrieve from cache
        cache_path = None
        if self.data_manager:
            cache_path = self.data_manager._get_cache_path("processed", "", f"elevation_data_{city_name}")
            if self.data_manager._is_cache_valid(cache_path):
                return self.data_manager._load_from_cache(cache_path)

        # Initialize results dictionary
        elevation_map = {}

        # Process in batches to respect API limits
        for i in range(0, len(coords_list), self.max_points_per_call):
            batch = coords_list[i:i+self.max_points_per_call]

            # Extract lat/lon for API request
            latitudes = [lat for lat, lon in batch]
            longitudes = [lon for lat, lon in batch]

            print(f"Making elevation API call {i//self.max_points_per_call + 1} for {len(batch)} points")

            # Make API request
            params = {
                "latitude": ",".join(map(str, latitudes)),
                "longitude": ",".join(map(str, longitudes))
            }

            try:

                response = requests.get(self.api_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()

                # Process results
                if 'elevation' in data:
                    for j, elev in enumerate(data['elevation']):
                        if j < len(batch):
                            elevation_map[batch[j]] = elev

            except Exception as e:
                print(f"Error fetching elevation data: {e}")
                # Continue with other batches

        # Cache the results if data manager is available
        if self.data_manager and cache_path:
            self.data_manager._save_to_cache(elevation_map, cache_path)

        return elevation_map

    def _create_elevation_grid(self, sampling_points, elevation_map, transformer, x_coords, y_coords):
        # Create 2D arrays for the elevation grid
        elevation_grid = np.zeros((len(y_coords), len(x_coords)))

        # Fill the grid with elevation values
        for i, y in enumerate(y_coords):
            for j, x in enumerate(x_coords):
                # Convert to WGS84
                lon, lat = transformer.transform(x, y)
                key = (round(lat, 4), round(lon, 4))

                # Get elevation from map
                if key in elevation_map:
                    elevation_grid[i, j] = elevation_map[key]
                else:
                    # If point is missing, use nearest available elevation
                    # This should be rare due to our grid generation
                    elevation_grid[i, j] = 0

        # Create bilinear interpolator function
        interpolator = RegularGridInterpolator((y_coords, x_coords), elevation_grid,
                                               method='linear', bounds_error=False, fill_value=None)

        return elevation_grid, interpolator

    def _calculate_slope(self, center_point, interpolator, resolution):
        x, y = center_point

        # Sample elevation at center point
        center_elev = interpolator([y, x])[0]

        # Sample elevations in cardinal directions
        points = [
            (x + resolution, y), # East
            (x - resolution, y), # West
            (x, y + resolution), # North
            (x, y - resolution) # South
        ]

        # Calculate slopes in each direction
        slopes = []
        for px, py in points:
            try:
                elev = interpolator([py, px])[0]
                elevation_diff = abs(elev - center_elev)
                slope = (elevation_diff / resolution) * 100 # Convert to percentage
                slopes.append(slope)
            except Exception:
                # Skip if point is outside the interpolation bounds
                continue

        return max(slopes) if slopes else 0

    def _score_slope(self, slope):
        # Find appropriate score from thresholds
        for threshold, score in sorted(self.slope_scores.items()):
            if slope <= threshold:
                return score

        # If slope exceeds all thresholds
        return 0

    def calculate(self, grid_gdf, city_name=None):
        print("Calculating Topography metric...")
        start_time = time.time()

        # Make a copy of the grid to avoid modifying the original
        grid_gdf = grid_gdf.copy()

        # Ensure we have centroids for calculations
        if 'centroid' not in grid_gdf.columns:
            grid_gdf['centroid'] = grid_gdf.geometry.centroid

        # Get bounds of the entire region
        bounds = grid_gdf.total_bounds

        # Generate a sampling grid covering the entire region
        x_coords, y_coords, sampling_points = self._generate_sampling_grid(bounds, self.resolution)
        print(f"Generated regular grid with {len(sampling_points)} points ({len(x_coords)}x{len(y_coords)})")

        # Convert sampling points to WGS84 for API call
        from pyproj import Transformer
        transformer = Transformer.from_crs(grid_gdf.crs, "EPSG:4326", always_xy=True)

        wgs84_points = []
        xy_to_wgs84 = {} # Mapping from (x,y) to (lat,lon)

        for x, y in sampling_points:
            lon, lat = transformer.transform(x, y)
            rounded_lat, rounded_lon = round(lat, 4), round(lon, 4)
            wgs84_points.append((rounded_lat, rounded_lon))
            xy_to_wgs84[(x, y)] = (rounded_lat, rounded_lon)

        # Remove duplicates to minimize API calls
        unique_wgs84_points = list(set(wgs84_points))
        print(f"Reduced to {len(unique_wgs84_points)} unique points after rounding")

        # Fetch elevations in a single batch
        elevation_map = self._fetch_elevations_batch(unique_wgs84_points, city_name)
        print(f"Fetched elevations for {len(elevation_map)} points")

        # Create elevation grid and bilinear interpolator
        elevation_grid, interpolator = self._create_elevation_grid(
            sampling_points, elevation_map, transformer, x_coords, y_coords)

        # Initialize score columns
        grid_gdf[self.name] = 0.0
        grid_gdf[f"{self.name}_slope"] = 0.0
        grid_gdf[f"{self.name}_score"] = 0.0

        # Process hexagons in batches
        total_hexagons = len(grid_gdf)

        for batch_start in range(0, total_hexagons, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total_hexagons)
            batch = grid_gdf.iloc[batch_start:batch_end]

            for idx, hexagon in batch.iterrows():
                # Get hexagon centroid coordinates
                centroid = hexagon.centroid
                center_point = (centroid.x, centroid.y)

                # Calculate maximum slope
                max_slope = self._calculate_slope(center_point, interpolator, self.resolution)

                # Score based on slope
                topo_score = self._score_slope(max_slope)

                # Store results
                grid_gdf.at[idx, f"{self.name}_slope"] = max_slope
                grid_gdf.at[idx, self.name] = topo_score
                grid_gdf.at[idx, f"{self.name}_score"] = topo_score

        print(f"Topography calculation complete. Total time: {time.time() - start_time:.2f} seconds")
        return grid_gdf