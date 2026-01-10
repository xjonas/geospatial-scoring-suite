"""
A centralized data manager to handle efficient data loading, caching, and preprocessing.
This module reduces redundant API calls and improves overall performance.
"""

import os
import pickle
from datetime import datetime, timedelta
import geopandas as gpd
import pandas as pd
import numpy as np
import osmnx as ox
from shapely.geometry import Point
from config.settings import GERMANY_CRS, CACHE_EXPIRY_DAYS, CACHE_ENABLED

class DataManager:
    # Singleton class to manage all data loading and caching operations.
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DataManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        # Initialize the data manager.
        # Set up cache directories
        self.cache_dir = "data/cache"
        self.osm_cache_dir = os.path.join(self.cache_dir, "osm")
        self.processed_cache_dir = os.path.join(self.cache_dir, "processed")

        os.makedirs(self.osm_cache_dir, exist_ok=True)
        os.makedirs(self.processed_cache_dir, exist_ok=True)

        # Initialize data containers
        self.city_geometry = {}
        self.osm_networks = {}
        self.poi_data = {}
        self.green_space_data = {}
        self.hexagon_grids = {}

        # Spatial indices
        self.spatial_indices = {}

    def _get_cache_path(self, cache_type, city_name, item_type=""):
        # Get the file path for a cached item
        # Clean up city name for file path
        if city_name:
            safe_city_name = city_name.replace(", ", "_").replace(" ", "_").lower()
            filename = f"{safe_city_name}_{item_type}.pkl"
        else:
            # Handle case where no city name is provided
            filename = f"{item_type}.pkl"

        if cache_type == "osm":
            cache_dir = self.osm_cache_dir
        else:
            cache_dir = self.processed_cache_dir

        return os.path.join(cache_dir, filename)

    def _is_cache_valid(self, cache_path, expiry_days=None):
        # Check if cached data is still valid so not expired
        # Check if caching is enabled globally
        try:
            if not CACHE_ENABLED:
                return False
        except ImportError:
            pass

        if expiry_days is None:
            expiry_days = CACHE_EXPIRY_DAYS if 'CACHE_EXPIRY_DAYS' in globals() else 30

        if not os.path.exists(cache_path):
            return False

        # Check if cache has expired
        file_modified_time = datetime.fromtimestamp(os.path.getmtime(cache_path))
        expiry_time = datetime.now() - timedelta(days=expiry_days)

        return file_modified_time > expiry_time

    def _save_to_cache(self, data, cache_path):
        # Save data to cache
        print(f"Saving data to cache: {cache_path}")
        with open(cache_path, 'wb') as f:
            pickle.dump(data, f)

    def _load_from_cache(self, cache_path):
        # Load data from cache
        print(f"Loading data from cache: {cache_path}")
        with open(cache_path, 'rb') as f:
            return pickle.load(f)

    def get_city_geometry(self, city_name):
        # Get city geometry from OSM, with caching
        if city_name in self.city_geometry:
            return self.city_geometry[city_name]

        cache_path = self._get_cache_path("osm", city_name, "geometry")

        if self._is_cache_valid(cache_path):
            self.city_geometry[city_name] = self._load_from_cache(cache_path)
            return self.city_geometry[city_name]

        # Cache miss so load from API
        print(f"Loading geometry for {city_name} from OSM...")
        city_gdf = ox.geocode_to_gdf(city_name)

        # Project to specified CRS
        city_gdf = city_gdf.to_crs(GERMANY_CRS)

        # Cache result
        self.city_geometry[city_name] = city_gdf
        self._save_to_cache(city_gdf, cache_path)

        return city_gdf

    def get_network(self, city_name, network_type="walk"):
        # Get OSM network for a city, with caching
        network_key = f"{city_name}_{network_type}"

        if network_key in self.osm_networks:
            return self.osm_networks[network_key]

        cache_path = self._get_cache_path("osm", city_name, f"network_{network_type}")

        if self._is_cache_valid(cache_path):
            self.osm_networks[network_key] = self._load_from_cache(cache_path)
            return self.osm_networks[network_key]

        # Cache miss - load from API
        print(f"Loading {network_type} network for {city_name} from OSM...")

        graph = ox.graph_from_place(city_name, network_type=network_type)

        # Project graph to the specified CRS
        graph = ox.projection.project_graph(graph, to_crs=GERMANY_CRS)

        # Cache result
        self.osm_networks[network_key] = graph
        self._save_to_cache(graph, cache_path)

        return graph

    def get_pois(self, city_name, category_key, tag_values):
        # Get POIs for a specific category, with caching
        poi_key = f"{city_name}_{category_key}_{'_'.join(tag_values)}"

        if poi_key in self.poi_data:
            return self.poi_data[poi_key]

        cache_path = self._get_cache_path("osm", city_name, f"pois_{category_key}")

        if self._is_cache_valid(cache_path):
            try:
                cached_data = self._load_from_cache(cache_path)

                # Filter for requested tag values based on cache format
                if isinstance(cached_data, list):
                    # Handle case where cache contains list of GeoDataFrames
                    if all(isinstance(item, gpd.GeoDataFrame) for item in cached_data):
                        matching_pois = []
                        for gdf in cached_data:
                            if 'category' in gdf.columns and any(tag in tag_values for tag in gdf['category'].unique()):
                                matching_pois.append(gdf)

                        if matching_pois:
                            result = pd.concat(matching_pois)
                            self.poi_data[poi_key] = result
                            return result

                    # Handle case where cache contains list of dictionaries with 'data' and 'category'
                    elif all(isinstance(item, dict) and 'data' in item and 'category' in item for item in cached_data):
                        matching_pois = []
                        for item in cached_data:
                            if item['category'] in tag_values:
                                matching_pois.append(item['data'])

                        if matching_pois:
                            result = pd.concat(matching_pois)
                            self.poi_data[poi_key] = result
                            return result

            except Exception as e:
                print(f"Error loading POIs from cache: {e}")
                # Continue to fetch from API if cache can't be used

        # Cache miss or not all requested tags are in cache - load from API
        print(f"Loading POIs for {category_key} in {city_name} from OSM...")

        pois_list = []

        for tag_value in tag_values:
            try:
                tags = {category_key: tag_value}
                pois = ox.features_from_place(city_name, tags=tags)

                if not pois.empty:
                    # Add category and specific tag
                    pois['category_group'] = category_key
                    pois['category'] = tag_value
                    pois_list.append(pois)
                    print(f"Found {len(pois)} POIs for {category_key}={tag_value}")
            except Exception as e:
                print(f"Error fetching {category_key}={tag_value} POIs: {e}")

        if not pois_list:
            # Create empty GeoDataFrame with proper CRS
            try:
                city_crs = self.get_city_geometry(city_name).crs
            except:
                city_crs = GERMANY_CRS

            empty_gdf = gpd.GeoDataFrame([], geometry=[], crs=city_crs)
            self.poi_data[poi_key] = empty_gdf
            return empty_gdf

        try:
            # Combine all POIs
            result = pd.concat(pois_list)

            # Cache result by category - store the entire list of GeoDataFrames
            self._save_to_cache(pois_list, cache_path)

            self.poi_data[poi_key] = result
            return result

        except Exception as e:
            print(f"Error combining POIs: {e}")

            # Create empty GeoDataFrame with proper CRS if concatenation fails
            try:
                city_crs = self.get_city_geometry(city_name).crs
            except:
                city_crs = GERMANY_CRS

            empty_gdf = gpd.GeoDataFrame([], geometry=[], crs=city_crs)
            self.poi_data[poi_key] = empty_gdf
            return empty_gdf

    def get_green_spaces(self, city_name, tag_dict):
        # Get green spaces for a city, with caching
        tag_key = "_".join(f"{k}_{len(v)}" for k, v in tag_dict.items())
        cache_key = f"{city_name}_green_{tag_key}"

        if cache_key in self.green_space_data:
            return self.green_space_data[cache_key]

        cache_path = self._get_cache_path("osm", city_name, "green_spaces")

        if self._is_cache_valid(cache_path):
            self.green_space_data[cache_key] = self._load_from_cache(cache_path)
            return self.green_space_data[cache_key]

        # Cache miss - load from API
        print(f"Loading green spaces for {city_name} from OSM...")

        all_green_spaces = []

        # Fetch green spaces by tag category
        for tag_key, tag_values in tag_dict.items():
            for tag_value in tag_values:
                try:
                    tags = {tag_key: tag_value}
                    green_spaces = ox.features_from_place(city_name, tags=tags)

                    # Add tag information
                    if not green_spaces.empty:
                        green_spaces['green_type'] = f"{tag_key}_{tag_value}"
                        all_green_spaces.append(green_spaces)
                        print(f"Found {len(green_spaces)} green spaces for {tag_key}={tag_value}")
                except Exception as e:
                    print(f"Error fetching {tag_key}={tag_value} spaces: {e}")

        if not all_green_spaces:
            empty_gdf = gpd.GeoDataFrame([], geometry=[], crs=GERMANY_CRS)
            self.green_space_data[cache_key] = empty_gdf
            return empty_gdf

        # Combine all green spaces
        green_spaces_gdf = gpd.GeoDataFrame(pd.concat(all_green_spaces))

        # Keep only polygon or multipolygon geometries
        mask = green_spaces_gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])
        green_spaces_gdf = green_spaces_gdf[mask]

        # Ensure proper CRS
        green_spaces_gdf = green_spaces_gdf.to_crs(GERMANY_CRS)

        # Cache result
        self._save_to_cache(green_spaces_gdf, cache_path)
        self.green_space_data[cache_key] = green_spaces_gdf

        return green_spaces_gdf

    def get_simplified_intersections(self, city_name, tolerance, network_type="walk", dead_ends=False):
        if city_name:
            # If city name is provided, use it for caching
            cache_key = f"{city_name}_{network_type}_intersections_{tolerance}_{dead_ends}"
            cache_path = self._get_cache_path("processed", city_name, f"intersections_{tolerance}")

            if self._is_cache_valid(cache_path):
                return self._load_from_cache(cache_path)

            # Cache miss - compute intersections
            graph = self.get_network(city_name, network_type)
        else:
            # If no city name, we use the network we already have
            # No caching in this case
            if not self.osm_networks:
                return None, None

            # Get the first network from the dictionary
            first_key = next(iter(self.osm_networks))
            graph = self.osm_networks[first_key]

        print(f"Computing simplified intersections for {'the provided graph' if not city_name else city_name}...")

        # Simplify graph to get real intersections only
        graph_simplified = ox.simplification.consolidate_intersections(
            graph,
            tolerance=tolerance,
            rebuild_graph=True,
            dead_ends=dead_ends,
            reconnect_edges=True
        )

        # Convert to GeoDataFrames
        nodes_gdf, edges_gdf = ox.graph_to_gdfs(graph_simplified)

        # Cache result if we have a city name
        if city_name:
            self._save_to_cache((nodes_gdf, edges_gdf), cache_path)

        return nodes_gdf, edges_gdf

    def graph_to_gdfs(self, graph):

        # Convert graph to GeoDataFrames, with caching.

        # Direct conversion - no caching since this is a fast operation
        return ox.graph_to_gdfs(graph)

    def get_hexagon_grid(self, city_name, use_h3=True, h3_resolution=None):
        # Get or create a hexagon grid for a city, with caching.
        # Supports both traditional and H3-based hexagons.
        # Get configuration from settings
        from config.settings import HEXAGON_SIZE

        if use_h3:
            # Get H3 resolution from settings if not provided
            if h3_resolution is None:
                try:
                    from config.settings import H3_RESOLUTION
                    h3_resolution = H3_RESOLUTION
                except ImportError:
                    # Default to resolution 9 if not in settings
                    h3_resolution = 9

            grid_key = f"{city_name}_h3_{h3_resolution}"
            cache_path = self._get_cache_path("processed", city_name, f"hexgrid_h3_{h3_resolution}")
        else:
            # Traditional hexagons
            grid_key = f"{city_name}_{HEXAGON_SIZE}"
            cache_path = self._get_cache_path("processed", city_name, f"hexgrid_{HEXAGON_SIZE}")

        # Check memory cache
        if grid_key in self.hexagon_grids:
            return self.hexagon_grids[grid_key]

        # Check disk cache
        if self._is_cache_valid(cache_path):
            self.hexagon_grids[grid_key] = self._load_from_cache(cache_path)
            return self.hexagon_grids[grid_key]

        # Cache miss - create grid
        if use_h3:
            from src.data_processing.h3_grid_generator import create_h3_grid_from_city
            grid_gdf = create_h3_grid_from_city(city_name, h3_resolution)
        else:
            from src.data_processing.grid_generator import create_grid_from_city
            grid_gdf = create_grid_from_city(city_name)

        # Calculate and store centroids
        if 'centroid' not in grid_gdf.columns:
            grid_gdf['centroid'] = grid_gdf.geometry.centroid

        if 'centroid_x' not in grid_gdf.columns or 'centroid_y' not in grid_gdf.columns:
            grid_gdf['centroid_x'] = grid_gdf.centroid.x
            grid_gdf['centroid_y'] = grid_gdf.centroid.y

        # Cache result
        self._save_to_cache(grid_gdf, cache_path)
        self.hexagon_grids[grid_key] = grid_gdf

        return grid_gdf

    def get_spatial_index(self, gdf, name=None):
        # Get or create a spatial index for a GeoDataFrame.
        if name and name in self.spatial_indices:
            return self.spatial_indices[name]

        # Create index
        sindex = gdf.sindex

        # Store in memory cache if name provided
        if name:
            self.spatial_indices[name] = sindex

        return sindex

    def vectorized_buffer_query(self, points_gdf, points_column, target_gdf, buffer_distance, predicate='within'):
        # Create buffers once
        points_gdf['buffer'] = points_gdf[points_column].buffer(buffer_distance)

        # Get spatial index
        target_sindex = self.get_spatial_index(target_gdf)

        # Use sjoin with the buffer geometries
        return gpd.sjoin(
            points_gdf,
            target_gdf,
            how='inner',
            predicate=predicate
        )

    def get_city_population(self, city_name):
        # Get population data for a city from OSM.

        # Check cache first
        cache_key = f"{city_name}_population"
        cache_path = self._get_cache_path("processed", city_name, "population")

        if self._is_cache_valid(cache_path):
            return self._load_from_cache(cache_path)

        print(f"Fetching population data for {city_name}...")
        try:
            # Get place data which sometimes contains population
            gdf = ox.geocode_to_gdf(city_name)

            # Check if population is in the data
            if 'population' in gdf.columns and not gdf['population'].isna().all():
                population = gdf['population'].iloc[0]

                # Convert to integer if it's a string
                if isinstance(population, str):
                    try:
                        population = int(population)
                    except ValueError:
                        population = None
            else:
                # Try to get population from relation tags
                tags = {"place": ["city", "town", "village"]}
                places = ox.features_from_place(city_name, tags=tags)

                population = None
                if not places.empty and 'population' in places.columns:
                    # Filter out null values and convert to integers
                    pop_values = places['population'].dropna()
                    if not pop_values.empty:
                        # Convert strings to integers
                        pop_values = pop_values.apply(lambda x: int(x) if isinstance(x, str) and x.isdigit() else x)
                        # Filter only numeric values
                        pop_values = pop_values[pop_values.apply(lambda x: isinstance(x, (int, float)))]
                        if not pop_values.empty:
                            population = int(pop_values.iloc[0])

            # Cache the result
            self._save_to_cache(population, cache_path)
            return population

        except Exception as e:
            print(f"Error fetching population data: {e}")
            return None