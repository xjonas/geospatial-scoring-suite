import time
import numpy as np
import pandas as pd
import geopandas as gpd
from src.metrics.base_metric import BaseMetric

class ForestFireRiskMetric(BaseMetric):
    """
    Metric that calculates forest fire risk based on:
    - Historical fire data at Bundesland level (50%)
    - Local vegetation density from already loaded data (50%)
    """

    def __init__(self, weight=1.0, data_manager=None):

        super().__init__("forest_fire_resistance", weight)
        self.data_manager = data_manager

        # Historical fire data by bundesland (2019-2023) https://www.ble.de/DE/BZL/Daten-Berichte/Wald/wald_node.html
        self.fire_data = {
            'baden-württemberg': {'avg_fires': 57.4, 'avg_area': 13.84, 'trend': 0.2},
            'bayern': {'avg_fires': 95.4, 'avg_area': 92.72, 'trend': -0.1},
            'berlin': {'avg_fires': 13.4, 'avg_area': 15.68, 'trend': 0.0},
            'brandenburg': {'avg_fires': 334.6, 'avg_area': 748.02, 'trend': 0.1},
            'bremen': {'avg_fires': 0.0, 'avg_area': 0.0, 'trend': 0.0},
            'hamburg': {'avg_fires': 0.4, 'avg_area': 0.08, 'trend': 0.2},
            'hessen': {'avg_fires': 107.2, 'avg_area': 34.22, 'trend': 0.1},
            'mecklenburg-vorpommern': {'avg_fires': 54.8, 'avg_area': 241.96, 'trend': 0.0},
            'niedersachsen': {'avg_fires': 265.8, 'avg_area': 45.36, 'trend': 0.1},
            'nordrhein-westfalen': {'avg_fires': 136.4, 'avg_area': 37.76, 'trend': 0.1},
            'rheinland-pfalz': {'avg_fires': 49.2, 'avg_area': 18.76, 'trend': 0.1},
            'saarland': {'avg_fires': 10.5, 'avg_area': 3.0, 'trend': 0.2},
            'sachsen': {'avg_fires': 126.6, 'avg_area': 57.10, 'trend': 0.1},
            'sachsen-anhalt': {'avg_fires': 85.2, 'avg_area': 34.7, 'trend': 0.0},
            'schleswig-holstein': {'avg_fires': 1.0, 'avg_area': 0.24, 'trend': 0.2},
            'thüringen': {'avg_fires': 41.6, 'avg_area': 12.6, 'trend': 0.0}
        }

        # Component weights
        self.historical_weight = 0.5    
        self.vegetation_weight = 0.5    

        # Vegetation type risk factors (on a scale of 0-1)
        self.vegetation_risk = {
            'forest': 1.0, # Highest risk
            'wood': 0.85,
            'grass': 0.4,
            'scrub': 0.7,
            'heath': 0.8,
            'farmland': 0.4,
            'orchard': 0.65,
            'vineyard': 0.55,
            'wetland': 0.2,
            'water': 0.0
        }

    def _calculate_historical_risk(self, bundesland):
        # Default score if bundesland not found
        if bundesland is None or bundesland not in self.fire_data:
            return 50.0

        # Get data for this bundesland
        data = self.fire_data[bundesland]

        # Calculate score based on average fires (40%)
        # Normalize across all Bundesländer (Brandenburg has highest)
        max_fires = 350.0 # Slightly above Brandenburg's average
        fire_count_score = min(100.0, (data['avg_fires'] / max_fires) * 100)

        # Calculate score based on average area (40%)
        # Normalize across all Bundesländer
        max_area = 800.0 # Slightly above Brandenburg's average
        area_score = min(100.0, (data['avg_area'] / max_area) * 100)

        # Trend factor (20%) - increasing trends increase risk
        trend_score = 50 + (data['trend'] * 100) # Convert -0.2 to +0.2 to 30-70 range

        # Combine scores
        historical_score = (fire_count_score * 0.4) + (area_score * 0.4) + (trend_score * 0.2)

        return historical_score

    def _calculate_vegetation_risk(self, hexagon):
        # Default moderate risk if no vegetation data
        risk_score = 50.0

        # Use green space data if already calculated
        if 'green_percentage' in hexagon:
            green_pct = hexagon['green_percentage']

            # Higher green space percentage = higher fire risk
            # But must be qualified by the type of green space

            if green_pct > 80:
                # Very high vegetation coverage
                risk_score = 90
            elif green_pct > 60:
                # High vegetation coverage
                risk_score = 75
            elif green_pct > 40:
                # Moderate vegetation coverage
                risk_score = 60
            elif green_pct > 20:
                # Low vegetation coverage
                risk_score = 40
            else:
                # Very low vegetation coverage
                risk_score = 20


        return risk_score

    def calculate(self, grid_gdf, city_name=None):
        print("Calculating Forest Fire Risk metric...")
        start_time = time.time()

        grid_gdf = grid_gdf.copy()

        # Get Bundesland from settings
        try:
            from config.settings import BUNDESLAND
            bundesland = BUNDESLAND.lower()
            print(f"Using Bundesland: {bundesland}")
        except ImportError:
            print("BUNDESLAND not defined in settings, using default")
            bundesland = "bayern" # Default if not specified

        # Get historical risk score for this Bundesland
        historical_score = self._calculate_historical_risk(bundesland)
        print(f"Historical fire risk for {bundesland}: {historical_score:.1f}/100")

        # Initialize fire risk columns
        grid_gdf[self.name] = 0.0
        grid_gdf[f"{self.name}_historical"] = historical_score
        grid_gdf[f"{self.name}_vegetation"] = 0.0

        # Calculate risk for each hexagon
        print("Calculating local vegetation factors for each hexagon...")

        # Process hexagons
        for idx, hexagon in grid_gdf.iterrows():
            # Calculate vegetation risk using already loaded data
            veg_risk = self._calculate_vegetation_risk(hexagon)

            # Store component score
            grid_gdf.at[idx, f"{self.name}_vegetation"] = veg_risk

            # Calculate combined risk score
            combined_risk = (
                    (historical_score * self.historical_weight) +
                    (veg_risk * self.vegetation_weight)
            )

            # Normalize to 0-100, Invert to get resistance score (higher = more resistant)
            resistance_score = 100 - combined_risk
            #resistance_score = combined_risk

            # Store final score
            grid_gdf.at[idx, self.name] = resistance_score

        # Scale to 0-100 and create score column
        grid_gdf[f"{self.name}_score"] = grid_gdf[self.name].clip(0, 100).round().astype(int)

        # Debugging
        print(f"Forest fire resistance range: {grid_gdf[self.name].min():.1f} - {grid_gdf[self.name].max():.1f}")

        print(f"Forest fire resistance calculation complete. Total time: {time.time() - start_time:.2f} seconds")
        return grid_gdf