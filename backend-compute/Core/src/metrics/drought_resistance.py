"""
Implementation of the Drought Resistance metric based on historical soil moisture index (SMI) data.
Uses preprocessed SMI data from the UFZ Drought Monitor Germany.
"""
import time
import pandas as pd
import numpy as np
import os
from src.metrics.base_metric import BaseMetric
from scipy.spatial import cKDTree

class DroughtResistanceMetric(BaseMetric):
    """
    Metric that calculates drought resistance based on:
    - Historical soil moisture data (SMI Gesamtboden) (70%)
    - Local vegetation density from already loaded data (30%)

    Higher scores indicate better resistance to drought (0-100 scale).
    """

    def __init__(self, weight=1.0, data_manager=None,
                 drought_data_filepath="data/input/drought_resistance_data.csv"):
        """
        Initialize drought resistance metric.

        Parameters:
        -----------
        weight : float
            Weight of the metric (not used for overall walkability)
        data_manager : DataManager
            Data manager instance for efficient data access
        drought_data_filepath : str
            Path to preprocessed drought data
        """
        super().__init__("drought_resistance", weight)
        self.data_manager = data_manager
        self.drought_data_filepath = drought_data_filepath
        self.spatial_grid_filepath = os.path.splitext(drought_data_filepath)[0] + '_grid.pkl'

        # Component weights
        self.historical_weight = 0.6     # 70% historical SMI data
        self.vegetation_weight = 0.4     # 30% vegetation factors

        # Drought severity weights for calculating combined score
        # More severe drought conditions receive higher penalties
        self.drought_weights = {
            'moderate_drought_pct': 0.8,
            'severe_drought_pct': 1.2,
            'extreme_drought_pct': 1.6,
            'exceptional_drought_pct': 2.0
        }

        # Spatial lookup structure
        self.spatial_tree = None
        self.drought_data = None

    def _load_drought_data(self):
        """
        Load preprocessed drought data and build spatial index if needed.
        First tries to load the optimized spatial grid, falls back to CSV if needed.
        """

        # First try to load the optimized spatial grid
        if os.path.exists(self.spatial_grid_filepath):
            try:
                import pickle
                print(f"Loading spatial grid from {self.spatial_grid_filepath}")
                with open(self.spatial_grid_filepath, 'rb') as f:
                    grid_data = pickle.load(f)
                    self.spatial_tree = grid_data['tree']
                    return grid_data['data']
            except Exception as e:
                print(f"Error loading spatial grid: {e}, falling back to CSV")

        # Fall back to CSV if spatial grid is not available
        if os.path.exists(self.drought_data_filepath):
            try:
                print(f"Loading drought data from {self.drought_data_filepath}")
                df = pd.read_csv(self.drought_data_filepath)

                # Build spatial index if needed
                if self.spatial_tree is None:
                    coords = df[['lat', 'lon']].values
                    self.spatial_tree = cKDTree(coords)

                return df
            except Exception as e:
                print(f"Error loading drought data: {e}")
                return pd.DataFrame()
        else:
            print(f"Drought data file not found: {self.drought_data_filepath}")
            return pd.DataFrame()

    def _find_nearest_drought_data(self, lat, lon, k=4):
        """
        Find the k nearest drought data points and return their weighted average.

        Parameters:
        -----------
        lat : float
            Latitude of the point
        lon : float
            Longitude of the point
        k : int
            Number of nearest neighbors to consider (default: 4)

        Returns:
        --------
        dict:
            Dictionary of drought metrics for this location
        """
        if self.spatial_tree is None or self.drought_data is None:
            # No spatial tree or data available
            return {
                'drought_resistance': 50.0,
                'avg_smi': 0.5,
                'total_drought_pct': 20.0
            }

        # Find k nearest neighbors
        distances, indices = self.spatial_tree.query([lat, lon], k=min(k, len(self.drought_data)))

        if len(indices) == 0:
            return {
                'drought_resistance': 50.0,
                'avg_smi': 0.5,
                'total_drought_pct': 20.0
            }

        # Calculate distance-weighted average for each metric
        total_weight = 0
        weighted_metrics = {}

        # Initialize with zeros
        for col in ['drought_resistance', 'avg_smi', 'total_drought_pct']:
            weighted_metrics[col] = 0.0

        # For additional metrics if available
        drought_categories = ['moderate_drought_pct', 'severe_drought_pct',
                              'extreme_drought_pct', 'exceptional_drought_pct']

        for cat in drought_categories:
            if cat in self.drought_data.columns:
                weighted_metrics[cat] = 0.0

        # Calculate weighted average
        for i, idx in enumerate(indices):
            # Inverse distance weighting
            if distances[i] < 1e-10:  # Almost exact match
                weight = 1.0
                total_weight = 1.0

                # Just use this exact point
                for col in weighted_metrics:
                    if col in self.drought_data.columns:
                        weighted_metrics[col] = self.drought_data.iloc[idx][col]

                break
            else:
                # Inverse distance weight
                weight = 1.0 / (distances[i] ** 2)
                total_weight += weight

                # Add weighted contribution
                for col in weighted_metrics:
                    if col in self.drought_data.columns:
                        weighted_metrics[col] += self.drought_data.iloc[idx][col] * weight

        # Normalize
        if total_weight > 0:
            for col in weighted_metrics:
                weighted_metrics[col] /= total_weight

        return weighted_metrics

    def calculate(self, grid_gdf, city_name=None):
        """
        Calculate drought resistance score for each hexagon.

        Parameters:
        -----------
        grid_gdf : GeoDataFrame
            Hexagon grid
        city_name : str, optional
            Name of the city

        Returns:
        --------
        grid_gdf : GeoDataFrame
            Grid with added drought_resistance column
        """
        print("Calculating Drought Resistance metric...")
        start_time = time.time()

        # Make a copy of the grid to avoid modifying the original
        grid_gdf = grid_gdf.copy()

        # Load preprocessed drought data
        self.drought_data = self._load_drought_data()

        if self.drought_data.empty:
            print("No drought data available. Using default values.")
            grid_gdf[self.name] = 50.0
            grid_gdf[f"{self.name}_score"] = 50
            return grid_gdf

        # Initialize columns
        grid_gdf[self.name] = 0.0
        grid_gdf[f"{self.name}_score"] = 0.0
        grid_gdf[f"{self.name}_historical"] = 0.0
        grid_gdf[f"{self.name}_vegetation"] = 0.0
        grid_gdf[f"{self.name}_smi"] = 0.0
        grid_gdf[f"{self.name}_drought_freq"] = 0.0

        # Get centroids in lat/lon for lookup
        if 'centroid' not in grid_gdf.columns:
            grid_gdf['centroid'] = grid_gdf.geometry.centroid

        # Convert centroids to lat/lon
        from pyproj import Transformer
        transformer = Transformer.from_crs(grid_gdf.crs, "EPSG:4326", always_xy=True)

        print("Processing drought resistance for each hexagon...")

        # Process each hexagon
        for idx, hexagon in grid_gdf.iterrows():
            # Get centroid coords
            centroid = hexagon.centroid
            lon, lat = transformer.transform(centroid.x, centroid.y)

            # Find nearest drought data point(s)
            drought_metrics = self._find_nearest_drought_data(lat, lon)

            # Store the SMI value
            grid_gdf.at[idx, f"{self.name}_smi"] = drought_metrics.get('avg_smi', 0.5)

            # Store drought frequency
            grid_gdf.at[idx, f"{self.name}_drought_freq"] = drought_metrics.get('total_drought_pct', 20.0)

            # Calculate historical drought resistance score using improved method
            avg_smi = drought_metrics.get('avg_smi', 0.5)
            drought_freq = drought_metrics.get('total_drought_pct', 20.0)

            # Better baseline calculation using non-linear SMI scaling
            # SMI of 0.3-0.5 is considered normal, not drought prone
            # Map this range to scores of 50-80
            if avg_smi >= 0.5:
                # Very good moisture levels (80-100)
                smi_score = 80 + (avg_smi - 0.5) * 40  # 0.5->80, 1.0->100
            elif avg_smi >= 0.3:
                # Normal moisture levels (50-80)
                smi_score = 50 + (avg_smi - 0.3) * 150  # 0.3->50, 0.5->80
            else:
                # Low moisture levels (0-50)
                smi_score = avg_smi * 167  # 0.0->0, 0.3->50

            # Modified drought frequency impact
            # More reasonable penalty for drought frequency
            # Reduce impact of drought frequency - many areas
            # experience drought but can still be drought resistant
            freq_impact = drought_freq * 0.5  # Reduced multiplier

            # Cap the penalty to allow higher scores
            freq_impact = min(40.0, freq_impact)  # Maximum 40 point reduction

            # Final historical score calculation
            historical_score = max(0.0, smi_score - freq_impact)

            # Calculate vegetation factor
            vegetation_score = 0.0

            # Check for green space data in different possible formats
            if 'green_percentage' in hexagon:
                green_pct = hexagon['green_percentage']
                # Higher vegetation coverage generally improves drought resistance
                # But need to consider vegetation type (not available in this sample)
                vegetation_score = min(100, green_pct * 1.3)  # 63% coverage = max score
            elif 'green_space' in hexagon:
                vegetation_score = hexagon['green_space']
            else:
                # No vegetation data, rely solely on historical data
                self.historical_weight = 1.0
                self.vegetation_weight = 0.0
                vegetation_score = 50  # Neutral value

            # Calculate final score
            combined_score = (
                    historical_score * self.historical_weight +
                    vegetation_score * self.vegetation_weight
            )

            # Set minimum score to 10
            combined_score = max(10, combined_score)

            # Store results
            grid_gdf.at[idx, f"{self.name}_historical"] = historical_score
            grid_gdf.at[idx, f"{self.name}_vegetation"] = vegetation_score
            grid_gdf.at[idx, self.name] = combined_score
            grid_gdf.at[idx, f"{self.name}_score"] = round(combined_score)

        # If no hexagon has vegetation data, inform the user
        if self.vegetation_weight == 0:
            print("No vegetation data found in hexagons. Using only historical drought data.")

        print(f"Drought resistance calculation complete. Time: {time.time() - start_time:.2f} seconds")

        # Print summary statistics
        print(f"Drought resistance score range: {grid_gdf[self.name].min():.1f} - {grid_gdf[self.name].max():.1f}")
        print(f"Average SMI: {grid_gdf[f'{self.name}_smi'].mean():.3f}")
        print(f"Average drought frequency: {grid_gdf[f'{self.name}_drought_freq'].mean():.1f}%")

        return grid_gdf