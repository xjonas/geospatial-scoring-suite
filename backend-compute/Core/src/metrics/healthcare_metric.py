"""
Implementation of a Healthcare metric based on pharmacy accessibility and healthcare facilities.
Uses Gemeindeschlüssel (GKZ) for accurate data matching.
"""
import pandas as pd
import numpy as np
import time
import os
import requests
from src.metrics.base_metric import BaseMetric

class HealthcareMetric(BaseMetric):
    """
    Metric that calculates healthcare accessibility based on:
    - Pharmacy accessibility (20%) - from poi_access metric
    - Emergency room accessibility (50%) - from CSV data
    - General practitioner accessibility (30%) - from CSV data

    Data is mapped using Gemeindeschlüssel (GKZ) for accurate matching.
    """

    def __init__(self, weight=1.0, data_manager=None, healthcare_filepath="data/input/healthcareA_data.csv"):
        """
        Initialize healthcare metric.

        Parameters:
        -----------
        weight : float
            Weight of the metric (not used for walkability)
        data_manager : DataManager
            Data manager instance for efficient data access
        healthcare_filepath : str
            Path to healthcare data CSV
        """
        super().__init__("healthcare", weight)
        self.data_manager = data_manager
        self.healthcare_filepath = healthcare_filepath

        # Component weights
        self.pharmacy_weight = 0.2    # 20% pharmacy access
        self.emergency_weight = 0.5   # 50% emergency room access
        self.doctor_weight = 0.3      # 30% general practitioner access

    def _load_healthcare_data(self):
        """
        Load and process healthcare data from CSV.
        No caching - direct load each time.

        Returns:
        --------
        DataFrame:
            Processed healthcare data with normalized scores
        """
        print("Loading healthcare data from CSV...")

        # Check if file exists
        if not os.path.exists(self.healthcare_filepath):
            print(f"ERROR: Healthcare data file not found: {self.healthcare_filepath}")
            return pd.DataFrame()

        # Load CSV data
        try:
            df = pd.read_csv(self.healthcare_filepath)
            print(f"Loaded healthcare data with {len(df)} rows")
        except Exception as e:
            print(f"Error loading healthcare data: {e}")
            return pd.DataFrame()

        # Check required columns
        required_columns = ['GKZ', 'HArzt_access', 'NotfallA_access']
        if not all(col in df.columns for col in required_columns):
            print(f"Healthcare data missing required columns. Required: {required_columns}, Found: {df.columns}")
            return pd.DataFrame()

        # Identify invalid data (marked as -9999.0) and replace with NaN
        df['HArzt_access'] = df['HArzt_access'].replace(-9999.0, np.nan)
        df['NotfallA_access'] = df['NotfallA_access'].replace(-9999.0, np.nan)

        # Create validity flags for simpler processing
        valid_doctor = df['HArzt_access'].notna() & (df['HArzt_access'] > 0)
        valid_emergency = df['NotfallA_access'].notna() & (df['NotfallA_access'] > 0)

        # Get min and max values for normalization (excluding invalid entries)
        if valid_doctor.any():
            min_doctor = df.loc[valid_doctor, 'HArzt_access'].min()
            max_doctor = df.loc[valid_doctor, 'HArzt_access'].max()
            print(f"Doctor access range: {min_doctor:.2f} - {max_doctor:.2f}")
        else:
            min_doctor, max_doctor = 0, 1
            print("No valid doctor data found")

        if valid_emergency.any():
            min_emergency = df.loc[valid_emergency, 'NotfallA_access'].min()
            max_emergency = df.loc[valid_emergency, 'NotfallA_access'].max()
            print(f"Emergency access range: {min_emergency:.2f} - {max_emergency:.2f}")
        else:
            min_emergency, max_emergency = 0, 1
            print("No valid emergency data found")

        # Calculate normalized scores (smaller values are better, so invert the scale)
        # Doctor score
        if max_doctor > min_doctor:
            df['hausarzt_score'] = np.nan
            df.loc[valid_doctor, 'hausarzt_score'] = 100 - ((df.loc[valid_doctor, 'HArzt_access'] - min_doctor) / (max_doctor - min_doctor) * 80)
            df['hausarzt_score'] = df['hausarzt_score'].clip(20, 100)

        # Emergency score
        if max_emergency > min_emergency:
            df['notfall_score'] = np.nan
            df.loc[valid_emergency, 'notfall_score'] = 100 - ((df.loc[valid_emergency, 'NotfallA_access'] - min_emergency) / (max_emergency - min_emergency) * 80)
            df['notfall_score'] = df['notfall_score'].clip(20, 100)

        # Convert GKZ to string type to ensure proper matching
        df['GKZ'] = df['GKZ'].astype(str)

        # Pad 7-digit GKZ with leading zero - this handles the case where database entries omit leading zeros
        df['GKZ'] = df['GKZ'].apply(lambda x: '0' + x if len(x) == 7 else x)

        return df

    def _get_gemeindeschluessel(self, city_name):
        """
        Retrieve the Gemeindeschlüssel (German municipality code) for a given city.

        Parameters:
        -----------
        city_name : str
            Name of the city, e.g., "Hammelburg, Germany"

        Returns:
        --------
        str:
            The Gemeindeschlüssel if found, None otherwise
        """
        # Use data manager for efficient API access
        if not self.data_manager:
            return None

        # Check if GKZ is already in cache
        cache_key = f"gkz_{city_name}"
        cache_path = self.data_manager._get_cache_path("processed", "", cache_key)

        if self.data_manager._is_cache_valid(cache_path):
            return self.data_manager._load_from_cache(cache_path)

        print(f"Getting Gemeindeschlüssel for city: {city_name}")
        try:
            import osmnx as ox
            print("------API CALL OSM------")

            # First, get the bounding box for the city using OSMnx
            gdf = ox.geocode_to_gdf(city_name)
            bbox = gdf.total_bounds
            # Convert to [south, west, north, east] format for Overpass API
            bbox_str = f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}"

            # Extract just the city name without country
            city_name_clean = city_name.split(',')[0].strip()

            # Use Overpass API to find the municipality with the Gemeindeschlüssel tag
            overpass_url = "https://overpass-api.de/api/interpreter"
            overpass_query = f"""
            [out:json];
            (
              node["de:amtlicher_gemeindeschluessel"]["name"~"{city_name_clean}", i]({bbox_str});
              way["de:amtlicher_gemeindeschluessel"]["name"~"{city_name_clean}", i]({bbox_str});
              relation["de:amtlicher_gemeindeschluessel"]["name"~"{city_name_clean}", i]({bbox_str});
            );
            out body;
            """

            response = requests.post(overpass_url, data=overpass_query)
            if response.status_code == 200:
                data = response.json()

                # Look for the Gemeindeschlüssel tag in the results
                for element in data.get("elements", []):
                    if "de:amtlicher_gemeindeschluessel" in element.get("tags", {}):
                        gkz = element["tags"]["de:amtlicher_gemeindeschluessel"]
                        # Cache the result
                        self.data_manager._save_to_cache(gkz, cache_path)
                        return gkz

                # Try for admin boundaries if exact match not found
                overpass_query = f"""
                [out:json];
                (
                  relation["boundary"="administrative"]["admin_level"="8"]({bbox_str});
                );
                out body;
                """

                response = requests.post(overpass_url, data=overpass_query)
                if response.status_code == 200:
                    data = response.json()

                    for element in data.get("elements", []):
                        if "de:amtlicher_gemeindeschluessel" in element.get("tags", {}):
                            gkz = element["tags"]["de:amtlicher_gemeindeschluessel"]
                            # Cache the result
                            self.data_manager._save_to_cache(gkz, cache_path)
                            return gkz

            print(f"Gemeindeschlüssel not found for {city_name}")
            return None

        except Exception as e:
            print(f"Error getting Gemeindeschlüssel data from OSM: {e}")
            return None

    def calculate(self, grid_gdf, city_name=None):
        """
        Calculate healthcare score for each hexagon.

        Parameters:
        -----------
        grid_gdf : GeoDataFrame
            Hexagon grid
        city_name : str, optional
            Name of the city for GKZ determination

        Returns:
        --------
        grid_gdf : GeoDataFrame
            Grid with added healthcare metric column
        """
        print("Calculating Healthcare metric...")
        start_time = time.time()

        # Make a copy of the grid to avoid modifying the original
        grid_gdf = grid_gdf.copy()

        # Verify that the pharmacy score exists
        if 'poi_access_pharmacy_score' not in grid_gdf.columns:
            print("Error: poi_access_pharmacy_score not found in grid data. Run the POIAccessScore first.")
            # Create default column
            grid_gdf[self.name] = 50
            grid_gdf[f"{self.name}_score"] = 50
            return grid_gdf

        # Get city name from TEST_CITY if not provided
        if not city_name:
            from config.settings import TEST_CITY
            city_name = TEST_CITY.split(',')[0].strip()

        # Load healthcare data
        healthcare_data = self._load_healthcare_data()

        if healthcare_data.empty:
            print("No healthcare data available. Using pharmacy score only.")
            grid_gdf[self.name] = grid_gdf['poi_access_pharmacy_score']
            grid_gdf[f"{self.name}_score"] = grid_gdf[self.name]
            return grid_gdf

        # Get Gemeindeschlüssel for this city
        gemeindeschluessel = self._get_gemeindeschluessel(city_name)
        print(f"Identified Gemeindeschlüssel: {gemeindeschluessel}")

        # Initialize healthcare metric columns
        grid_gdf[self.name] = 0
        grid_gdf['gemeindeschluessel'] = gemeindeschluessel
        grid_gdf['hausarzt_score'] = np.nan
        grid_gdf['notfall_score'] = np.nan

        # Find data in healthcare CSV based on GKZ
        matching_data = None

        if gemeindeschluessel:
            # Try to find exact match by GKZ
            matches = healthcare_data[healthcare_data['GKZ'] == gemeindeschluessel]

            if not matches.empty:
                matching_data = matches.iloc[0]
                print(f"Found matching data for GKZ: {gemeindeschluessel}")
            else:
                print(f"No match found for GKZ: {gemeindeschluessel}")
        else:
            print("Could not determine GKZ for this city")

        # Get healthcare scores
        # Default values if no data is found
        doctor_score = 40
        emergency_score = 40

        if matching_data is not None:
            # Check if valid scores exist in matching data
            if pd.notna(matching_data.get('hausarzt_score')):
                doctor_score = matching_data['hausarzt_score']
                print(f"Using doctor score from data: {doctor_score}")
            else:
                print(f"No valid doctor score found for GKZ {gemeindeschluessel}, using default: {doctor_score}")

            if pd.notna(matching_data.get('notfall_score')):
                emergency_score = matching_data['notfall_score']
                print(f"Using emergency score from data: {emergency_score}")
            else:
                print(f"No valid emergency score found for GKZ {gemeindeschluessel}, using default: {emergency_score}")
        else:
            print(f"Using default scores - Doctor: {doctor_score}, Emergency: {emergency_score}")

        # Assign scores to all hexagons in the grid
        grid_gdf['hausarzt_score'] = doctor_score
        grid_gdf['notfall_score'] = emergency_score

        # Calculate final healthcare score
        # Pharmacy score (20%) + Emergency score (50%) + Doctor score (30%)
        pharmacy_scores = grid_gdf['poi_access_pharmacy_score']
        print(f"Pharmacy score range: {pharmacy_scores.min()} - {pharmacy_scores.max()}")

        # Calculate weighted score
        grid_gdf[self.name] = (
                pharmacy_scores * self.pharmacy_weight +
                grid_gdf['notfall_score'] * self.emergency_weight +
                grid_gdf['hausarzt_score'] * self.doctor_weight
        )

        # Round to integers
        grid_gdf[f"{self.name}_score"] = grid_gdf[self.name].round().astype(int)

        # Print final score ranges
        print(f"Final healthcare score range: {grid_gdf[self.name].min()} - {grid_gdf[self.name].max()}")

        print(f"Healthcare calculation complete. Total time: {time.time() - start_time:.2f} seconds")
        return grid_gdf