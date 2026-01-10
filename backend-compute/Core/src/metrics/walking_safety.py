"""
Implementation of the Safety metric based on pedestrian accident data and crime rates.
Analyzes accident density and crime statistics per hexagon to determine pedestrian safety scores.
"""
import os
import pandas as pd
import geopandas as gpd
import numpy as np
import time
from shapely.geometry import Point
from src.metrics.base_metric import BaseMetric
from src.data_processing.plz_kreis_mapper import PLZKreisMapper

class SafetyMetric(BaseMetric):
    """
    Metric that calculates pedestrian safety based on accident data and crime rates.

    The safety score is a weighted combination of:
    - Accident-based safety (60%): Inversely proportional to the number of accidents within each hexagon
    - Crime-based safety (40%): Based on crime rates in the region
    """

    def __init__(self, weight=1.0, data_manager=None,
                 accident_filepath="data/input/PedestrianAccidents_2019_2023.csv",
                 crime_filepath="data/input/crime_data_with_population.csv",
                 plz_kreis_filepath="data/input/plz_kreis_data.csv"):
        """
        Initialize safety metric.

        Parameters:
        -----------
        weight : float
            Weight of the metric in the final score
        data_manager : DataManager
            Data manager instance for efficient data access
        accident_filepath : str
            Path to the pedestrian accident CSV data
        crime_filepath : str
            Path to the crime statistics CSV data
        plz_kreis_filepath : str
            Path to the PLZ to Kreis mapping data
        """
        super().__init__("walking_safety", weight)
        self.data_manager = data_manager
        self.accident_filepath = accident_filepath
        self.crime_filepath = crime_filepath
        self.plz_kreis_filepath = plz_kreis_filepath

        # Component weights
        self.accident_weight = 0.6  # 60% accidents
        self.crime_weight = 0.4     # 40% crime rate

    def _load_accident_data(self, city_name=None):
        """
        Load and process accident data from CSV.
        Uses caching through data manager if available.

        Returns:
        --------
        GeoDataFrame:
            Processed accident data with geometries
        """
        # Try to get from cache if data manager is available
        if self.data_manager:
            cache_path = self.data_manager._get_cache_path("processed", "", f"accident_data_{city_name}")

            if self.data_manager._is_cache_valid(cache_path):
                return self.data_manager._load_from_cache(cache_path)

        print("Loading accident data from CSV...")
        start_time = time.time()

        # Verify file exists
        if not os.path.exists(self.accident_filepath):
            print(f"Warning: Accident data file not found: {self.accident_filepath}")
            return gpd.GeoDataFrame([], geometry=[], crs="EPSG:4326")

        # Load CSV data
        df = pd.read_csv(self.accident_filepath)

        # Handle decimal comma format (German locale) by replacing commas with dots
        df['XGCSWGS84'] = df['XGCSWGS84'].str.replace(',', '.')
        df['YGCSWGS84'] = df['YGCSWGS84'].str.replace(',', '.')

        # Convert to GeoDataFrame with coordinates in WGS84
        geometry = [Point(float(x), float(y)) for x, y in zip(df['XGCSWGS84'], df['YGCSWGS84'])]
        accidents_gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

        # Convert to the CRS used in the application
        if self.data_manager:
            # Use the same CRS as the grid data
            first_city = next(iter(self.data_manager.city_geometry)) if self.data_manager.city_geometry else None
            if first_city:
                target_crs = self.data_manager.city_geometry[first_city].crs
                accidents_gdf = accidents_gdf.to_crs(target_crs)
            else:
                # Fallback to Germany CRS from settings
                from config.settings import GERMANY_CRS
                accidents_gdf = accidents_gdf.to_crs(GERMANY_CRS)
        else:
            # Fallback to Germany CRS from settings
            from config.settings import GERMANY_CRS
            accidents_gdf = accidents_gdf.to_crs(GERMANY_CRS)

        print(f"Loaded {len(accidents_gdf)} accident records in {time.time() - start_time:.2f} seconds")

        # Cache if data manager is available
        if self.data_manager:
            self.data_manager._save_to_cache(accidents_gdf, cache_path)

        return accidents_gdf

    def _load_crime_data(self, city_name=None):
        """
        Load and process crime data from CSV.
        Uses caching through data manager if available.

        Returns:
        --------
        DataFrame:
            Processed crime data with normalized scores
        """
        # Try to get from cache if data manager is available
        if self.data_manager:
            cache_path = self.data_manager._get_cache_path("processed", "", f"crime_data_{city_name}")

            if self.data_manager._is_cache_valid(cache_path):
                return self.data_manager._load_from_cache(cache_path)

        print("Loading crime data from CSV...")
        start_time = time.time()

        # Verify file exists
        if not os.path.exists(self.crime_filepath):
            print(f"Warning: Crime data file not found: {self.crime_filepath}")
            return pd.DataFrame()

        # Load CSV data
        df = pd.read_csv(self.crime_filepath)

        # Ensure 'Name' and 'Type' columns exist
        required_columns = ['Name', 'Type', 'Total_Crime_Rate']
        if not all(col in df.columns for col in required_columns):
            print(f"Warning: Crime data missing required columns. Required: {required_columns}, Found: {df.columns}")
            return pd.DataFrame()

        # Calculate crime safety score (inverse of crime rate)
        if len(df) > 0:
            # Find min and max crime rates (per capita)
            min_crime_rate = df['Total_Crime_Rate'].min()
            max_crime_rate = df['Total_Crime_Rate'].max()

            # Calculate score: 100 for lowest crime rate, 20 for highest
            # Use min-max scaling with range [20, 100]
            if max_crime_rate > min_crime_rate:
                df['crime_safety_score'] = 100 - ((df['Total_Crime_Rate'] - min_crime_rate) /
                                                  (max_crime_rate - min_crime_rate)) * 80
            else:
                print("Warning: All regions have the same crime rate. Assigning default score of 70.")
                df['crime_safety_score'] = 70  # If all regions have same crime rate
        else:
            # Empty dataframe
            df['crime_safety_score'] = 0

        print(f"Processed crime data for {len(df)} regions in {time.time() - start_time:.2f} seconds")

        # Cache if data manager is available
        if self.data_manager:
            self.data_manager._save_to_cache(df, cache_path)

        return df

    def _get_region_for_hexagon(self, hexagon_id, city_name, city_plz=None):
        """
        Determine the appropriate region (Kreis, City, etc.) for a hexagon.

        Parameters:
        -----------
        hexagon_id : str
            ID of the hexagon
        city_name : str
            Name of the city
        city_plz : str, optional
            Postal code of the city

        Returns:
        --------
        tuple:
            (region_name, region_type) for the hexagon
        """
        # If no city_plz provided, try to get it from settings
        if not city_plz:
            try:
                from config.settings import TEST_CITY_PLZ
                city_plz = TEST_CITY_PLZ
            except ImportError:
                # If not available in settings, default to None
                city_plz = None

        if not city_plz:
            # Without a PLZ, we can only use city name as is
            return city_name, "City"

        # Initialize PLZKreisMapper if needed
        if not hasattr(self, 'plz_mapper') or self.plz_mapper is None:
            try:
                self.plz_mapper = PLZKreisMapper(self.plz_kreis_filepath)
            except Exception as e:
                print(f"Warning: Could not initialize PLZ-Kreis mapper: {e}")
                return city_name, "City"

        # Get Kreis name from PLZ
        kreis_name = self.plz_mapper.get_kreis(city_plz)

        if kreis_name:
            return kreis_name, "Kreis"
        else:
            # If mapping fails, fall back to city name
            return city_name, "City"

    def calculate(self, grid_gdf, accident_data=None, crime_data=None, city_name=None):
        """
        Calculate safety score for each hexagon based on accident density and crime rates.

        Parameters:
        -----------
        grid_gdf : GeoDataFrame
            Hexagon grid
        accident_data : GeoDataFrame, optional
            Pre-loaded accident data (if not provided, will be loaded from file)
        crime_data : DataFrame, optional
            Pre-loaded crime data (if not provided, will be loaded from file)
        city_name : str, optional
            Name of the city for region determination

        Returns:
        --------
        grid_gdf : GeoDataFrame
            Grid with added safety metric column
        """
        print("Calculating Walkabiilty Safety metric (accidents + crime rates)...")
        start_time = time.time()

        # Make a copy of the grid to avoid modifying the original
        grid_gdf = grid_gdf.copy()

        # Get city name from TEST_CITY if not provided
        if not city_name:
            from config.settings import TEST_CITY
            city_name = TEST_CITY.split(',')[0].strip()  # Extract just the city name part

        # Try to get PLZ from settings
        try:
            from config.settings import TEST_CITY_PLZ
            city_plz = TEST_CITY_PLZ
        except ImportError:
            city_plz = None

        # Initialize safety metric columns
        grid_gdf[self.name] = 0
        grid_gdf['accident_count'] = 0
        grid_gdf['accident_safety_score'] = 0
        grid_gdf['crime_safety_score'] = 0
        grid_gdf['region_name'] = ""
        grid_gdf['region_type'] = ""

        # 1. Calculate Accident-based Safety Score (60%)
        # --------------------------------------------
        # Load accident data if not provided
        if accident_data is None:
            accident_data = self._load_accident_data(city_name)

        if not accident_data.empty:
            # Ensure same CRS
            if grid_gdf.crs != accident_data.crs:
                accident_data = accident_data.to_crs(grid_gdf.crs)

            print("Performing spatial join between accidents and hexagons...")

            # Use spatial join to efficiently count accidents in each hexagon
            joined = gpd.sjoin(accident_data, grid_gdf, how="left", predicate="within")

            # Count accidents per hexagon
            if not joined.empty:
                accident_counts = joined.groupby('id').size()
                # Add counts to grid
                grid_gdf['accident_count'] = grid_gdf['id'].map(accident_counts).fillna(0)

            # Calculate accident safety score (inverse relationship with accident count)
            # Maximum score is 90 (for 0 accidents)
            # Minimum score depends on threshold (we'll use 7+ accidents = minimum score)
            grid_gdf['accident_safety_score'] = np.maximum(0, 90 - grid_gdf['accident_count'] * 15)
            grid_gdf['accident_safety_score'] = grid_gdf['accident_safety_score'].clip(0, 90)
        else:
            # No accident data available, use default value
            print("No accident data available. Using default accident safety score.")
            grid_gdf['accident_safety_score'] = 75  # Moderate default value

        # 2. Calculate Crime-based Safety Score (40%)
        # ------------------------------------------
        # Load crime data if not provided
        if crime_data is None:
            crime_data = self._load_crime_data(city_name)

        if not crime_data.empty:
            # Determine region (Kreis, City, etc.) for each hexagon
            # For simplicity, we're assigning the same region to all hexagons in this implementation
            region_name, region_type = self._get_region_for_hexagon(None, city_name, city_plz)

            # Find the most specific data available for this region
            region_data = None

            # Try to find the most specific data available
            # Priority: Neighborhood > Bezirk > City > Kreis
            for type_priority in ['Neighborhood', 'Bezirk', 'City', 'Kreis']:
                filtered = crime_data[(crime_data['Name'] == region_name) &
                                      (crime_data['Type'] == type_priority)]
                if not filtered.empty:
                    region_data = filtered.iloc[0]
                    region_type = type_priority
                    break

            # If no exact match found, try partial match for Kreis
            if region_data is None:
                for index, row in crime_data[crime_data['Type'] == 'Kreis'].iterrows():
                    if region_name in row['Name'] or row['Name'] in region_name:
                        region_data = row
                        region_type = 'Kreis'
                        break

            # Assign crime safety score to all hexagons
            if region_data is not None:
                grid_gdf['crime_safety_score'] = region_data['crime_safety_score']
                grid_gdf['region_name'] = region_data['Name']
                grid_gdf['region_type'] = region_type
            else:
                # No matching region found
                print(f"Warning: No crime data found for region: {region_name} ({region_type})")
                grid_gdf['crime_safety_score'] = 70  # Default value if no data available
                grid_gdf['region_name'] = region_name
                grid_gdf['region_type'] = region_type
        else:
            # No crime data available
            print("No crime data available. Using default crime safety score.")
            grid_gdf['crime_safety_score'] = 70  # Moderate default value
            grid_gdf['region_name'] = city_name
            grid_gdf['region_type'] = "Unknown"

        # 3. Calculate Combined Safety Score
        # ---------------------------------
        # Weighted average of accident safety (60%) and crime safety (40%)
        grid_gdf[self.name] = (
                self.accident_weight * grid_gdf['accident_safety_score'] +
                self.crime_weight * grid_gdf['crime_safety_score']
        )

        # Add integer-rounded score column
        grid_gdf[f"{self.name}_score"] = grid_gdf[self.name].round().astype(int)

        print(f"Safety calculation complete. Total time: {time.time() - start_time:.2f} seconds")
        # Debug prints for verification
        #print(f"\nSafety Metric Debug Information:")
        #print(f"Region: {grid_gdf['region_name'].iloc[0]} ({grid_gdf['region_type'].iloc[0]})")
        #print(f"Accident-based safety score range: {grid_gdf['accident_safety_score'].min():.1f} - {grid_gdf['accident_safety_score'].max():.1f}")
        #print(f"Crime-based safety score: {grid_gdf['crime_safety_score'].iloc[0]:.1f}")
        #print(f"Combined safety score range: {grid_gdf[self.name].min():.1f} - {grid_gdf[self.name].max():.1f}")

        return grid_gdf