
def calculate_walkscore(grid_gdf, metrics, city_population=None):
    # Calculate final walkscore from individual metrics, with population adjustment
    print("Calculating Walkscore...")

    # Copy grid to avoid modifying the original
    grid_gdf = grid_gdf.copy()

    # Initialize walkscore column
    grid_gdf['walkscore'] = 0

    # Calculate weighted sum of metric scores
    total_weight = sum(metric.weight for metric in metrics)

    # Track metrics by name for potential adjustment
    metric_contributions = {}

    for metric in metrics:
        score_column = f"{metric.name}_score"
        if score_column in grid_gdf.columns:
            normalized_weight = metric.weight / total_weight
            contribution = grid_gdf[score_column] * normalized_weight
            grid_gdf['walkscore'] += contribution

            # Store contribution for potential adjustment
            metric_contributions[metric.name] = contribution

    # Apply population-based scaling if population data is available
    if city_population is not None:
        # Define population tiers and their scaling factors
        # For small towns, boost POI scores; for large cities, slightly penalize
        population_tiers = {
            5000: {"poi_accessibility": 1.0, "general": 1.5}, # Very small towns
            15000: {"poi_accessibility": 1.0, "general": 1.3}, # Small towns
            50000: {"poi_accessibility": 1.05, "general": 1.15}, # Medium towns
            200000: {"poi_accessibility": 1.1, "general": 1.0}, # Small cities (baseline)
            500000: {"poi_accessibility": 1.1, "general": 1.0}, # Medium cities
            1000000: {"poi_accessibility": 1.2, "general": 1.0}, # Large cities
            float('inf'): {"poi_accessibility": 1.2, "general": 1.0}  # Mega cities
        }

        # Find appropriate scaling factors
        poi_scaling = 1.0
        general_scaling = 1.0

        for pop_threshold, factors in sorted(population_tiers.items()):
            if city_population <= pop_threshold:
                poi_scaling = factors["poi_accessibility"]
                general_scaling = factors["general"]
                break

        print(f"Applying population scaling (population: {city_population})")
        print(f"POI scaling factor: {poi_scaling}, General scaling: {general_scaling}")

        # Adjust the walkscore
        # First, reduce the original walkscore
        grid_gdf['walkscore'] *= general_scaling

        # Then add back the POI component with its specific scaling
        if "poi_accessibility" in metric_contributions:
            # Remove the original contribution and add the scaled version
            poi_contrib = metric_contributions["poi_accessibility"]
            grid_gdf['walkscore'] += poi_contrib * (poi_scaling - general_scaling)

        # Store the original unscaled score for reference
        grid_gdf['walkscore_unscaled'] = grid_gdf['walkscore'] / general_scaling

    # Round to integers
    grid_gdf['walkscore'] = grid_gdf['walkscore'].round().astype(int)

    # Ensure walkscore is between 0 and 100
    grid_gdf['walkscore'] = grid_gdf['walkscore'].clip(0, 100)

    return grid_gdf

def calculate_climate_score(grid_gdf, city_name=None):
    # Calculate climate resilience score based on multiple climate risk metrics.
    print("Calculating Climate Resilience Score...")

    # Copy grid to avoid modifying the original
    grid_gdf = grid_gdf.copy()

    # Verify all required metrics exist
    required_metrics = [
        "drought_resistance_score",
        "flood_resistance_score",
        "forest_fire_resistance_score",
        "extreme_heat_resistance_score"
    ]

    missing_metrics = [metric for metric in required_metrics if metric not in grid_gdf.columns]
    if missing_metrics:
        print(f"Warning: Missing climate metrics: {missing_metrics}")
        print("Using available metrics only")

    # Define weights based on scientific literature on climate change impacts
    # Weights should reflect both global impact severity and regional relevance
    # Default weights based on IPCC AR6 impact assessment for Europe
    weights = {
        "extreme_heat_resistance_score": 0.40, # Heat is primary risk factor in most regions
        "drought_resistance_score": 0.25, 
        "flood_resistance_score": 0.25, 
        "forest_fire_resistance_score": 0.10 
    }

    # Initialize climate score column
    grid_gdf['climate_score'] = 0.0

    # Calculate weighted sum of available metrics
    total_weight = 0.0
    for metric, weight in weights.items():
        if metric in grid_gdf.columns:
            grid_gdf['climate_score'] += grid_gdf[metric] * weight
            total_weight += weight

    # Normalize if not all metrics are available
    if total_weight > 0 and total_weight < 1.0:
        grid_gdf['climate_score'] = grid_gdf['climate_score'] / total_weight * 100

    # Ensure values are within 0-100 range
    grid_gdf['climate_score'] = grid_gdf['climate_score'].clip(0, 100)

    # Round to integers
    grid_gdf['climate_score'] = grid_gdf['climate_score'].round().astype(int)

    print(f"Climate score range: {grid_gdf['climate_score'].min()} - {grid_gdf['climate_score'].max()}")

    return grid_gdf
