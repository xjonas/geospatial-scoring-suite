"""
Implementation of the Noise metric based on road characteristics and land use.
Uses scientific models for noise propagation without requiring additional API calls.
"""
import time
import numpy as np
import pandas as pd
import geopandas as gpd
from src.metrics.base_metric import BaseMetric
from shapely.geometry import LineString
from config.settings import CHUNK_SIZE


class NoiseMetric(BaseMetric):
    """
    Metric that calculates noise levels based on road characteristics and land use.

    The implementation is based on a simplified version of the EU's Common Noise
    Assessment Methods (CNOSSOS-EU) and the German RLS-19 (Richtlinien für den
    Lärmschutz an Straßen) standards.

    The noise score reflects the inverse of noise pollution - higher scores mean
    quieter areas which are better for walking.
    """

    def __init__(self, weight=1.0, data_manager=None):
        """
        Initialize noise metric.

        Parameters:
        -----------
        weight : float
            Weight of the metric in the final score
        data_manager : DataManager, optional
            Data manager instance for efficient data access
        """
        super().__init__("noise_model", weight)
        self.data_manager = data_manager

        # Constants based on scientific literature for road noise emission
        # Base emission levels per road type (dB at 10m reference distance)
        self.road_noise_levels = {
            'motorway': 80,
            'motorway_link': 75,
            'trunk': 75,
            'trunk_link': 70,
            'primary': 70,
            'primary_link': 65,
            'secondary': 65,
            'secondary_link': 60,
            'tertiary': 60,
            'tertiary_link': 55,
            'residential': 50,
            'living_street': 45,
            'service': 45,
            'unclassified': 50,
            'pedestrian': 35,
            'footway': 30,
            'path': 30,
            'cycleway': 35,
            'track': 40,
            # Default for unknown road types
            'unknown': 50
        }

        # Speed adjustment factors (based on RLS-19 model)
        # Defines how much noise increases with speed compared to reference (50 km/h)
        self.speed_coefficient = 10.0  # dB per doubling of speed
        self.reference_speed = 50.0    # km/h

        # Distance attenuation coefficients
        # Based on simplified EU noise models (ISO 9613-2)
        self.distance_coefficient = 20.0  # Spherical spreading: -20 dB per 10× distance
        self.reference_distance = 10.0    # meters

        # Traffic volume estimation based on road type (vehicles/hour)
        # Rough estimates for average daytime traffic
        self.traffic_volume = {
            'motorway': 4000,
            'motorway_link': 2000,
            'trunk': 2000,
            'trunk_link': 1500,
            'primary': 1000,
            'primary_link': 800,
            'secondary': 500,
            'secondary_link': 400,
            'tertiary': 250,
            'tertiary_link': 200,
            'residential': 80,
            'living_street': 30,
            'service': 20,
            'unclassified': 100,
            # Negligible traffic for pedestrian paths
            'pedestrian': 0,
            'footway': 0,
            'path': 0,
            'cycleway': 0,
            'track': 10,
            # Default
            'unknown': 100
        }

        # Land use noise factors (ambient noise levels in dB)
        self.land_use_noise = {
            'industrial': 65,
            'commercial': 60,
            'retail': 55,
            'residential': 45,
            'park': 40,
            'forest': 35,
            'meadow': 35,
            'grass': 35,
            'garden': 40,
            'recreation_ground': 45,
            'nature_reserve': 35,
            'water': 40,
            # Default
            'unknown': 50
        }

        # Maximum distances to consider
        self.max_road_distance = 300.0  # meters (roads beyond this have negligible impact)

        # Heavy/light vehicle ratio estimation by road type (fraction of heavy vehicles)
        self.heavy_vehicle_ratio = {
            'motorway': 0.15,
            'trunk': 0.12,
            'primary': 0.10,
            'secondary': 0.08,
            'tertiary': 0.05,
            'residential': 0.02,
            'unclassified': 0.03,
            # Default
            'unknown': 0.05
        }

        # Surface correction (dB)
        self.surface_correction = {
            'asphalt': 0,
            'concrete': 1,
            'paved': 0,
            'sett': 3,
            'cobblestone': 4,
            'unpaved': -2,
            'gravel': -1,
            'ground': -3,
            # Default
            'unknown': 0
        }

    def _extract_speed_limit(self, speed_tag):
        """
        Extract numerical speed limit from OSM maxspeed tag.

        Parameters:
        -----------
        speed_tag : str, list, or None
            OSM maxspeed tag value

        Returns:
        --------
        float:
            Speed limit in km/h or self.reference_speed if unknown
        """
        # Handle case where speed_tag is a list
        if isinstance(speed_tag, list):
            if not speed_tag:  # Empty list
                return self.reference_speed
            speed_tag = speed_tag[0]  # Take the first value

        if pd.isna(speed_tag) or speed_tag is None:
            return self.reference_speed

        try:
            # Try direct conversion to int
            return float(speed_tag)
        except ValueError:
            # Handle common formats like "50 km/h"
            try:
                return float(speed_tag.split()[0])
            except (ValueError, IndexError):
                # Handle special values
                if speed_tag == 'walk' or speed_tag == 'walking':
                    return 7.0  # Walking speed in km/h
                elif speed_tag == 'none' or speed_tag == 'unlimited':
                    # German default speed limits if not specified
                    return 50.0  # Urban default
                return self.reference_speed

    def _calculate_road_noise(self, road_type, speed_limit, distance, surface=None):
        """
        Calculate estimated noise level from a road at a specific distance.

        Implements a simplified version of the CNOSSOS-EU and RLS-19 models.

        Parameters:
        -----------
        road_type : str
            Type of road (highway tag from OSM)
        speed_limit : float
            Speed limit in km/h
        distance : float
            Distance from the road in meters
        surface : str, optional
            Road surface type

        Returns:
        --------
        float:
            Estimated noise level in dB
        """
        # Get base noise level for this road type
        base_level = self.road_noise_levels.get(road_type, self.road_noise_levels['unknown'])

        # Traffic volume adjustment
        traffic = self.traffic_volume.get(road_type, self.traffic_volume['unknown'])
        # 10 * log10(traffic/100) - normalized to 100 vehicles/hour
        traffic_adjustment = 10 * np.log10(max(traffic, 1) / 100)

        # Speed adjustment (based on speed coefficient)
        speed_ratio = speed_limit / self.reference_speed
        speed_adjustment = self.speed_coefficient * np.log10(max(speed_ratio, 0.1))

        # Heavy vehicle adjustment
        heavy_ratio = self.heavy_vehicle_ratio.get(road_type, self.heavy_vehicle_ratio['unknown'])
        # Each heavy vehicle is equivalent to about 10 light vehicles in noise impact
        heavy_adjustment = 10 * np.log10(1 + 9 * heavy_ratio)

        # Surface correction
        surface_adj = 0
        if surface:
            surface_adj = self.surface_correction.get(surface, 0)

        # Distance attenuation (simplified model)
        # Standard formula from acoustics: SPL drops by distance_coefficient * log10(distance/reference)
        if distance < self.reference_distance:
            distance_attenuation = 0
        else:
            distance_attenuation = -self.distance_coefficient * np.log10(distance / self.reference_distance)

        # Combine all factors
        noise_level = (base_level +
                       traffic_adjustment +
                       speed_adjustment +
                       heavy_adjustment +
                       surface_adj +
                       distance_attenuation)

        return noise_level

    def _combine_noise_sources(self, noise_levels):
        """
        Combine multiple noise sources using logarithmic addition.

        Parameters:
        -----------
        noise_levels : list
            List of noise levels in dB

        Returns:
        --------
        float:
            Combined noise level in dB
        """
        if not noise_levels:
            return 0

        # Convert to linear scale, sum, then back to dB
        linear_sum = sum(10 ** (level / 10) for level in noise_levels)
        return 10 * np.log10(linear_sum)

    def _noise_to_score(self, noise_level):
        """
        Convert noise level to a 0-100 score.

        Higher scores mean quieter areas (better for walking).

        Parameters:
        -----------
        noise_level : float
            Noise level in dB

        Returns:
        --------
        float:
            Score between 0-100
        """
        # Define thresholds based on WHO guidelines and German standards
        # <40dB: Excellent (100)
        # 40-45dB: Very Good (90-100)
        # 45-50dB: Good (80-90)
        # 50-55dB: Moderate (70-80)
        # 55-60dB: Acceptable (60-70)
        # 60-65dB: Noisy (50-60)
        # 65-70dB: Very Noisy (40-50)
        # 70-75dB: Loud (30-40)
        # 75-80dB: Very Loud (20-30)
        # >80dB: Extremely Loud (0-20)

        if noise_level < 40:
            return 100
        elif noise_level < 45:
            return 90 + (45 - noise_level) * 2
        elif noise_level < 50:
            return 80 + (50 - noise_level) * 2
        elif noise_level < 55:
            return 70 + (55 - noise_level) * 2
        elif noise_level < 60:
            return 60 + (60 - noise_level) * 2
        elif noise_level < 65:
            return 50 + (65 - noise_level) * 2
        elif noise_level < 70:
            return 40 + (70 - noise_level) * 2
        elif noise_level < 75:
            return 30 + (75 - noise_level) * 2
        elif noise_level < 80:
            return 20 + (80 - noise_level) * 2
        else:
            return max(0, 20 - (noise_level - 80))

    def calculate(self, grid_gdf, graph=None, city_name=None, city_population=None):
        """
        Calculate noise score for each hexagon in the grid.

        Parameters:
        -----------
        grid_gdf : GeoDataFrame
            Hexagon grid
        graph : networkx.MultiDiGraph, optional
            OSM graph containing road attributes
        city_name : str, optional
            Name of the city for data retrieval

        Returns:
        --------
        grid_gdf : GeoDataFrame
            Grid with added noise score columns
        """
        print("Calculating Noise metric...")
        start_time = time.time()

        # Make a copy of the grid to avoid modifying the original
        grid_gdf = grid_gdf.copy()

        # Ensure we have a data manager
        if self.data_manager is None:
            from src.data_processing.data_manager import DataManager
            self.data_manager = DataManager()

        # Get road network data if not provided
        if graph is None and city_name:
            graph = self.data_manager.get_network(city_name, network_type="walk")

        # Convert graph to GeoDataFrame
        if hasattr(graph, 'edges'):
            _, edges_gdf = self.data_manager.graph_to_gdfs(graph)
        else:
            # Assume it's already an edges GeoDataFrame
            edges_gdf = graph

        # Get land use data - using green spaces as a proxy for quiet areas
        try:
            green_spaces_gdf = None
            if city_name:
                # Define tags for land use
                land_use_tags = {
                    'leisure': ['park', 'garden', 'nature_reserve', 'playground'],
                    'landuse': ['forest', 'meadow', 'grass', 'recreation_ground', 'allotments'],
                    'natural': ['wood', 'grassland', 'heath', 'scrub']
                }
                green_spaces_gdf = self.data_manager.get_green_spaces(city_name, land_use_tags)
        except Exception as e:
            print(f"Warning: Could not load land use data: {e}")
            green_spaces_gdf = None

        # Ensure same CRS
        edges_gdf = edges_gdf.to_crs(grid_gdf.crs)
        if green_spaces_gdf is not None:
            green_spaces_gdf = green_spaces_gdf.to_crs(grid_gdf.crs)

        # Initialize noise columns
        grid_gdf[self.name] = 0.0
        grid_gdf[f"{self.name}_level"] = 0.0  # Raw dB level
        grid_gdf[f"{self.name}_road"] = 0.0   # Road noise component
        grid_gdf[f"{self.name}_land"] = 0.0   # Land use noise component

        # Create spatial indices for efficient calculations
        edges_sindex = self.data_manager.get_spatial_index(edges_gdf, "edges_noise") if self.data_manager else edges_gdf.sindex
        green_sindex = None
        if green_spaces_gdf is not None and not green_spaces_gdf.empty:
            green_sindex = self.data_manager.get_spatial_index(green_spaces_gdf, "green_noise") if self.data_manager else green_spaces_gdf.sindex

        # Process in chunks for better memory management
        chunk_size = CHUNK_SIZE
        total_hexagons = len(grid_gdf)

        print(f"Processing {total_hexagons} hexagons in chunks of {chunk_size}...")

        for chunk_start in range(0, total_hexagons, chunk_size):
            chunk_end = min(chunk_start + chunk_size, total_hexagons)
            chunk = grid_gdf.iloc[chunk_start:chunk_end]

            # Process each hexagon in the chunk
            for idx, hexagon in chunk.iterrows():
                # Calculate centroid for noise level estimation
                if 'centroid' in hexagon:
                    centroid = hexagon.centroid
                else:
                    centroid = hexagon.geometry.centroid

                # Create a buffer around centroid for road search
                buffer = centroid.buffer(self.max_road_distance)

                # Find roads near this hexagon using spatial index
                possible_road_indices = list(edges_sindex.intersection(buffer.bounds))
                nearby_roads = edges_gdf.iloc[possible_road_indices]

                # Further filter to roads that actually intersect the buffer
                nearby_roads = nearby_roads[nearby_roads.geometry.intersects(buffer)]

                # Calculate noise from each road
                road_noise_levels = []

                if not nearby_roads.empty:
                    for _, road in nearby_roads.iterrows():
                        # Get road type
                        if 'highway' in road:
                            road_type = road['highway']
                            # Handle list values
                            if isinstance(road_type, list):
                                road_type = road_type[0] if road_type else 'unknown'
                        else:
                            road_type = 'unknown'

                        # Get speed limit
                        speed_limit = self.reference_speed
                        if 'maxspeed' in road:
                            speed_limit = self._extract_speed_limit(road['maxspeed'])

                        # Get surface
                        surface = 'unknown'
                        if 'surface' in road:
                            if isinstance(road['surface'], list):
                                surface = road['surface'][0] if road['surface'] else 'unknown'
                            else:
                                surface = road['surface']

                        # Calculate distance from centroid to road
                        distance = centroid.distance(road.geometry)
                        # Minimum 5m distance to avoid extreme values
                        distance = max(5.0, distance)

                        # Calculate noise from this road
                        noise = self._calculate_road_noise(road_type, speed_limit, distance, surface)
                        road_noise_levels.append(noise)

                # Combine road noise sources
                combined_road_noise = self._combine_noise_sources(road_noise_levels)

                # Land use noise (ambient)
                land_use_noise = 45  # Default ambient noise level

                # Check if hexagon overlaps with green spaces
                if green_sindex is not None:
                    possible_green_indices = list(green_sindex.intersection(hexagon.geometry.bounds))
                    if possible_green_indices:
                        intersecting_green = green_spaces_gdf.iloc[possible_green_indices]
                        intersecting_green = intersecting_green[intersecting_green.geometry.intersects(hexagon.geometry)]

                        if not intersecting_green.empty:
                            # Calculate area of intersection for each green space
                            total_area = 0
                            weighted_noise = 0

                            for _, green in intersecting_green.iterrows():
                                # Extract green space type
                                green_type = 'unknown'
                                if 'green_type' in green:
                                    green_type = green['green_type']
                                    if '_' in green_type:
                                        # Extract the value part from "key_value" format
                                        green_type = green_type.split('_', 1)[1]

                                # Get area of intersection
                                intersection = hexagon.geometry.intersection(green.geometry)
                                area = intersection.area

                                # Get noise level for this land use
                                noise_level = self.land_use_noise.get(green_type, self.land_use_noise['unknown'])

                                # Add to weighted average
                                weighted_noise += noise_level * area
                                total_area += area

                            # If green spaces cover significant portion (>30%), use weighted average
                            if total_area > 0.3 * hexagon.geometry.area:
                                land_use_noise = weighted_noise / total_area

                # Calculate final noise level by combining road and ambient noise
                final_noise = self._combine_noise_sources([combined_road_noise, land_use_noise])

                # Convert to score (higher = better = quieter)
                noise_score = self._noise_to_score(final_noise)

                # Store results
                grid_gdf.at[idx, f"{self.name}_level"] = final_noise
                grid_gdf.at[idx, f"{self.name}_road"] = combined_road_noise
                grid_gdf.at[idx, f"{self.name}_land"] = land_use_noise
                grid_gdf.at[idx, self.name] = noise_score # for compatibility with other metrics
                grid_gdf.at[idx, f"{self.name}_score"] = noise_score

        # Apply population-based scaling if population data is available
        if city_population is not None:
            print(f"Applying noise population scaling (population: {city_population})")
            # Define population tiers and their scaling factors
            # For small towns, reduce noise (increase score) due to less traffic
            population_tiers = {
                1000: 2,        # Tiny towns (+50% score)
                5000: 1.7,      # Very small towns (+30% score)
                15000: 1.3,     # Small towns (+20% score)
                50000: 1.05,     # Medium towns (+10% score)
                100000: 1.0,    # Small cities (baseline)
                500000: 0.95,   # Medium cities (-5% score)
                1000000: 0.92,   # Large cities (-10% score)
                float('inf'): 0.92  # Mega cities (-15% score)
            }

            # Find appropriate scaling factor
            scaling_factor = 1.0
            for pop_threshold, factor in sorted(population_tiers.items()):
                if city_population <= pop_threshold:
                    scaling_factor = factor
                    break

            print(f"Noise scaling factor: {scaling_factor}")

            # Scale the noise scores (higher for lower population)
            # We apply scaling to both raw values and score columns
            grid_gdf[self.name] = (grid_gdf[self.name] * scaling_factor).clip(0, 100)
            grid_gdf[f"{self.name}_score"] = (grid_gdf[f"{self.name}_score"] * scaling_factor).clip(0, 100)

        print(f"Noise metric calculation complete. Total time: {time.time() - start_time:.2f} seconds")
        print("-----DEBUG INFO-----")
        print("Noise level score ranges:")
        print(f"  Min: {grid_gdf[f"{self.name}_score"].min():.2f}, Max: {grid_gdf[f"{self.name}_score"].max():.2f}")
        print("-----END DEBUG INFO-----")

        return grid_gdf