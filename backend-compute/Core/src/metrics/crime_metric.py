import os
import pandas as pd
import numpy as np
import time
from src.metrics.base_metric import BaseMetric
from src.data_processing.plz_kreis_mapper import PLZKreisMapper


class CrimeMetric(BaseMetric):
    """
    Metric that calculates crime safety based on burglary data and existing safety scores.

    The crime score is a weighted combination of:
    - Burglary-based safety (50%): Inversely proportional to burglary rates per 100,000 residents
    - Existing safety metric (50%): Uses the already calculated walking_safety score
    """

    def __init__(self, weight=1.0, data_manager=None,
                 burglary_filepath="data/input/crime_data_with_population.csv",
                 plz_kreis_filepath="data/input/plz_kreis_data.csv"):
        super().__init__("crime", weight)
        self.data_manager = data_manager
        self.burglary_filepath = burglary_filepath
        self.plz_kreis_filepath = plz_kreis_filepath

        # Component weights
        self.burglary_weight = 0.5 # 50% burglary data
        self.safety_weight = 0.5 # 50% existing safety score

    def _load_burglary_data(self, city_name=None):
        # Uses caching through data manager if available
        if self.data_manager:
            cache_path = self.data_manager._get_cache_path("processed", "", f"burglary_data_{city_name}")

            if self.data_manager._is_cache_valid(cache_path):
                return self.data_manager._load_from_cache(cache_path)

        print("Loading burglary data from CSV...")
        start_time = time.time()

        # Verify file exists
        if not os.path.exists(self.burglary_filepath):
            print(f"Warning: Crime data file not found: {self.burglary_filepath}")
            return pd.DataFrame()

        # Load CSV data
        df = pd.read_csv(self.burglary_filepath)

        # Ensure columns exist
        required_columns = ['Name', 'Type', 'Burglary', 'Population']
        if not all(col in df.columns for col in required_columns):
            print(f"Warning: Burglary data missing required columns. Required: {required_columns}, Found: {df.columns}")
            return pd.DataFrame()

        # Calculate burglary safety score (inverse of burglary rate)
        if len(df) > 0:
            # Calculate burglary rate per 100,000 residents
            df['Burglary_Rate'] = (df['Burglary'] / df['Population']) * 100000

            # Calculate score based on burglary rate per 100,000 residents
            # 300+ burglaries per 100k = 10 points
            # 15 or fewer burglaries per 100k = 100 points
            # Linear scale in between

            def calculate_burglary_score(rate):
                if rate <= 10:
                    return 100
                elif rate >= 300:
                    return 10
                else:
                    # Linear interpolation between 15 and 300
                    return 100 - ((rate - 15) / (300 - 15)) * (100 - 10)

            df['burglary_safety_score'] = df['Burglary_Rate'].apply(calculate_burglary_score)
        else:
            # Empty dataframe
            df['burglary_safety_score'] = 0.0

        print(f"Processed burglary data for {len(df)} regions in {time.time() - start_time:.2f} seconds")

        # Cache if data manager is available
        if self.data_manager:
            self.data_manager._save_to_cache(df, cache_path)

        return df

    def _get_region_for_hexagon(self, hexagon_id, city_name, city_plz=None):
        # Determine the appropriate region (Kreis, City, etc.) for a hexagon
        # This method is identical to the one in walking_safety.py to ensure compatibility

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
            return city_name, "City"

    def calculate(self, grid_gdf, burglary_data=None, city_name=None):
        print("Calculating Crime metric (burglaries + existing safety)...")
        start_time = time.time()

        grid_gdf = grid_gdf.copy()

        if 'walking_safety_score' not in grid_gdf.columns:
            print("Error: walking_safety_score not found in grid data. Run the SafetyMetric first.")
            # Create empty columns to avoid errors
            grid_gdf[self.name] = 50  # Default value
            grid_gdf[f"{self.name}_score"] = 50
            grid_gdf['burglary_safety_score'] = 50
            return grid_gdf

        # Get city name from TEST_CITY if not provided
        if not city_name:
            from config.settings import TEST_CITY
            city_name = TEST_CITY.split(',')[0].strip() # Extract just the city name part

        # Try to get PLZ from settings
        try:
            from config.settings import TEST_CITY_PLZ
            city_plz = TEST_CITY_PLZ
        except ImportError:
            city_plz = None

        # Initialize crime metric columns
        grid_gdf[self.name] = 0
        grid_gdf['burglary_safety_score'] = 0
        grid_gdf['region_name_crime'] = ""
        grid_gdf['region_type_crime'] = ""

        # Load burglary data if not provided
        if burglary_data is None:
            burglary_data = self._load_burglary_data(city_name)

        if not burglary_data.empty:
            # Determine region (Kreis, City, etc.) for this city
            region_name, region_type = self._get_region_for_hexagon(None, city_name, city_plz)

            # Find the most specific data available for this region
            region_data = None

            # Try to find the most specific data available
            # Priority: Neighborhood > Bezirk > City > Kreis
            for type_priority in ['Neighborhood', 'Bezirk', 'City', 'Kreis']:
                filtered = burglary_data[(burglary_data['Name'] == region_name) &
                                         (burglary_data['Type'] == type_priority)]
                if not filtered.empty:
                    region_data = filtered.iloc[0]
                    region_type = type_priority
                    break

            # If no exact match found, try partial match for Kreis
            if region_data is None:
                for index, row in burglary_data[burglary_data['Type'] == 'Kreis'].iterrows():
                    if region_name in row['Name'] or row['Name'] in region_name:
                        region_data = row
                        region_type = 'Kreis'
                        break

            # Assign burglary safety score to all hexagons
            if region_data is not None:
                grid_gdf['burglary_safety_score'] = region_data['burglary_safety_score']
                grid_gdf['region_name_crime'] = region_data['Name']
                grid_gdf['region_type_crime'] = region_type
            else:
                # No matching region found
                print(f"Warning: No burglary data found for region: {region_name} ({region_type})")
                grid_gdf['burglary_safety_score'] = 50  # Default value if no data available
                grid_gdf['region_name_crime'] = region_name
                grid_gdf['region_type_crime'] = region_type
        else:
            # No burglary data available
            print("No burglary data available. Using default burglary safety score.")
            grid_gdf['burglary_safety_score'] = 50  # Moderate default value
            grid_gdf['region_name_crime'] = city_name
            grid_gdf['region_type_crime'] = "Unknown"

        # Calculate Combined Crime Score
        # Weighted average of burglary safety (50%) and existing safety (50%)
        # walking_safety_score is already on a 0-100 scale, so we can combine directly
        grid_gdf[self.name] = (
                self.burglary_weight * grid_gdf['burglary_safety_score'] +
                self.safety_weight * grid_gdf['crime_safety_score']
        )

        grid_gdf[f"{self.name}_score"] = grid_gdf[self.name].round().astype(int)

        print(f"Crime calculation complete. Total time: {time.time() - start_time:.2f} seconds")

        return grid_gdf
