import os
from config.settings import TEST_CITY, INTERSECTION_CONSOLIDATION_TOLERANCE, WEIGHTS, POI_MAX_DISTANCE, POI_ACCESS_MAX_DISTANCE, GENERATE_MAPS
from src.data_processing.data_manager import DataManager
from src.metrics.intersection_density import IntersectionDensity
from src.scoring.score_calculator import calculate_walkscore, calculate_climate_score
from src.visualization.map_generator import plot_walkscore_map
from src.metrics.poi_accessibility import POIAccessibility
from src.metrics.green_space import GreenSpace
from src.metrics.infrastructure_safety import InfrastructureSafety
from src.metrics.walking_safety import SafetyMetric
from src.metrics.pollution import PollutionMetric
from src.metrics.noise_model import NoiseMetric
from src.metrics.topography import TopographyMetric
from src.metrics.poi_access_score import POIAccessScore
from src.metrics.crime_metric import CrimeMetric
from src.metrics.healthcare_metric import HealthcareMetric
from src.metrics.forest_fire_risk import ForestFireRiskMetric
from src.metrics.extreme_heat_risk import ExtremeHeatRiskMetric
from src.metrics.drought_resistance import DroughtResistanceMetric
from src.metrics.flood_resistance import FloodResistanceMetric
from src.utils.api_tracker import APITracker
import time


def clean_extra_geometry_columns(df):
    # Get all columns with geometry dtype
    geometry_columns = []
    for col in df.columns:
        if col != 'geometry' and hasattr(df[col], 'dtype') and str(df[col].dtype) == 'geometry':
            geometry_columns.append(col)

    # Handle centroids (appearing as extra geometry columns)
    if 'centroid' in df.columns:
        if hasattr(df['centroid'], 'dtype') and str(df['centroid'].dtype) == 'geometry':
            # Convert to WKT
            df['centroid_wkt'] = df['centroid'].apply(lambda x: x.wkt if x else None)
            geometry_columns.append('centroid')

    # Drop any geometry columns that actually exist in the DataFrame
    if geometry_columns:
        print(f"Removing extra geometry columns: {geometry_columns}")
        # Verify the columns exist before dropping them
        existing_columns = [col for col in geometry_columns if col in df.columns]
        if existing_columns:
            df = df.drop(columns=existing_columns)

    return df


def main():
    # Start timer for total execution time
    total_start_time = time.time()

    # Create data directories if they don't exist
    os.makedirs("data/results", exist_ok=True)
    os.makedirs("data/cache", exist_ok=True)

    # Initialize tracker before any API calls
    api_tracker = APITracker()

    # Initialize the data manager (singleton)
    data_manager = DataManager()

    # Step 1: Get simplified intersections via the data manager
    nodes_gdf, edges_gdf = data_manager.get_simplified_intersections(
        TEST_CITY,
        tolerance=INTERSECTION_CONSOLIDATION_TOLERANCE
    )

    # Step 2: Create hexagon grid
    try:
        from config.settings import USE_H3, H3_RESOLUTION
        use_h3 = USE_H3
        h3_resolution = H3_RESOLUTION
    except ImportError:
        # Default values if settings not found
        use_h3 = False
        h3_resolution = 9
        print("Warning: H3 grid settings not found in config. Using defaults.")

    if use_h3:
        print(f"Creating H3-based hexagon grid (resolution {h3_resolution})...")
        grid_gdf = data_manager.get_hexagon_grid(TEST_CITY, use_h3=True, h3_resolution=h3_resolution)
        print(f"Created H3 grid with {len(grid_gdf)} hexagons")
        if 'h3_index' in grid_gdf.columns:
            print(f"Sample H3 index: {grid_gdf['h3_index'].iloc[0]}")
    else:
        print("Creating traditional hexagon grid...")
        grid_gdf = data_manager.get_hexagon_grid(TEST_CITY, use_h3=False)
        print(f"Created traditional grid with {len(grid_gdf)} hexagons")

    # Step 3: Get the network graph (only once)
    graph = data_manager.get_network(TEST_CITY, network_type="walk")

    # Step 4: Calculate Metrics
    metrics = []

    # Get population data from OSM
    city_population = data_manager.get_city_population(TEST_CITY)

    # Intersection density metric
    intersection_density = IntersectionDensity(weight=WEIGHTS["intersection_density"], data_manager=data_manager)
    grid_gdf = intersection_density.calculate(grid_gdf, nodes_gdf)
    metrics.append(intersection_density)

    # POI accessibility metric
    poi_accessibility = POIAccessibility(
        weight=WEIGHTS["poi_accessibility"],
        max_distance=POI_MAX_DISTANCE,
        data_manager=data_manager
    )
    grid_gdf = poi_accessibility.calculate(grid_gdf, TEST_CITY)
    metrics.append(poi_accessibility)

    # Green space metric
    green_space = GreenSpace(
        weight=WEIGHTS["green_space"],
        data_manager=data_manager
    )
    grid_gdf = green_space.calculate(grid_gdf, TEST_CITY)
    metrics.append(green_space)

    # Infrastructure safety metric
    infrastructure_safety = InfrastructureSafety(
        weight=WEIGHTS["infrastructure_safety"],
        data_manager=data_manager
    )
    grid_gdf = infrastructure_safety.calculate(grid_gdf, graph)
    metrics.append(infrastructure_safety)

    # Safety metric
    walking_safety = SafetyMetric(
        weight=WEIGHTS["walking_safety"],
        data_manager=data_manager
    )
    grid_gdf = walking_safety.calculate(grid_gdf)
    metrics.append(walking_safety)

    # Pollution metric
    pollution = PollutionMetric(
        weight=WEIGHTS["pollution"],
        data_manager=data_manager
    )
    grid_gdf = pollution.calculate(grid_gdf, TEST_CITY)
    metrics.append(pollution)

    # Noise metric
    noise_model = NoiseMetric(
        weight=WEIGHTS["noise_model"],
        data_manager=data_manager
    )
    grid_gdf = noise_model.calculate(grid_gdf, graph, TEST_CITY, city_population)
    metrics.append(noise_model)

    # Topography metric
    topography = TopographyMetric(
        weight=WEIGHTS["topography"],
        data_manager=data_manager
    )
    grid_gdf = topography.calculate(grid_gdf, TEST_CITY)
    metrics.append(topography)

    # Step 5: Calculate walkscore with population adjustment
    grid_gdf = calculate_walkscore(grid_gdf, metrics, city_population=city_population)

    # Step 4b: Calculate additional metrics (not included in Walkability)
    print("Calculating additional metrics (not included in walkability score)...")

    # POI access score for everyday amenities (with car/mixed transportation)
    poi_access_score = POIAccessScore(
        weight=1.0, # Weight doesn't affect walkability
        max_distance=POI_ACCESS_MAX_DISTANCE, # 5km radius for car accessibility
        data_manager=data_manager
    )
    grid_gdf = poi_access_score.calculate(grid_gdf, TEST_CITY)

    # Crime metric based on burglary data and existing safety score
    crime_metric = CrimeMetric(
        weight=1.0, # Weight doesn't affect walkability
        data_manager=data_manager
    )
    grid_gdf = crime_metric.calculate(grid_gdf, city_name=TEST_CITY)

    # Healthcare metric based on healthcare facilities
    healthcare_metric = HealthcareMetric(
        weight=1.0, # Weight doesn't affect walkability
        data_manager=data_manager
    )
    grid_gdf = healthcare_metric.calculate(grid_gdf, city_name=TEST_CITY)

    # Forest fire risk metric (not part of walkability)
    forest_fire_risk = ForestFireRiskMetric(
        weight=1.0, # Weight doesn't affect walkability unless added to WEIGHTS
        data_manager=data_manager
    )
    grid_gdf = forest_fire_risk.calculate(grid_gdf, city_name=TEST_CITY)

    # Extreme heat risk metric (not part of walkability)
    extreme_heat_risk = ExtremeHeatRiskMetric(
        weight=1.0, # Weight doesn't affect walkability unless added to WEIGHTS
        data_manager=data_manager
    )
    grid_gdf = extreme_heat_risk.calculate(grid_gdf, city_name=TEST_CITY)

    # Drought resistance metric (not part of walkability)
    drought_resistance = DroughtResistanceMetric(
        weight=1.0, # Weight doesn't affect walkability unless added to WEIGHTS
        data_manager=data_manager
    )
    grid_gdf = drought_resistance.calculate(grid_gdf, city_name=TEST_CITY)

    # Flood resistance metric (not part of walkability)
    flood_resistance = FloodResistanceMetric(
        weight=1.0, # Weight doesn't affect walkability unless added to WEIGHTS
        data_manager=data_manager
    )
    grid_gdf = flood_resistance.calculate(grid_gdf, city_name=TEST_CITY)

    # After calculating all climate-related metrics (drought, flood, fire, heat)
    grid_gdf = calculate_climate_score(grid_gdf, city_name=TEST_CITY)

    # Step 5: Calculate walkscore with population adjustment (unchanged)
    grid_gdf = calculate_walkscore(grid_gdf, metrics, city_population=city_population)

    # Clean any extra geometry columns before saving to file
    grid_gdf = clean_extra_geometry_columns(grid_gdf)

    # Save results
    grid_gdf.to_file("data/results/walkscore.gpkg", driver="GPKG")


    # Step 6: Generate and save maps
    if GENERATE_MAPS:
        print("Generating maps...")
        time_map_generation = time.time()

        plot_walkscore_map(
            grid_gdf,
            TEST_CITY,
            "walkscore",
            save_path=f"data/results/walkscore_map_{TEST_CITY}.png"
        )

        # Generate maps for individual metrics
        for metric in metrics:
            plot_walkscore_map(
                grid_gdf,
                TEST_CITY,
                f"{metric.name}_score",
                save_path=f"data/results/{metric.name}_score_map_{TEST_CITY}.png"
            )

        # For POI accessibility, also generate category-specific maps
        # Reenable if needed
        '''if hasattr(poi_accessibility, 'category_group_weights'):
            plot_category_maps(
                grid_gdf,
                TEST_CITY,
                poi_accessibility.category_group_weights.keys(),
                base_column="poi_accessibility",
                save_dir="data/results"
            )'''

        # Generate maps for POI access categories
        poi_categories = ['grocery', 'nightlife', 'pharmacy', 'overall']
        for category in poi_categories:
            plot_walkscore_map(
                grid_gdf,
                TEST_CITY,
                f"poi_access_{category}_score",
                save_path=f"data/results/poi_access_{category}_map_{TEST_CITY}.png"
            )

        # Generate maps for crime metric
        plot_walkscore_map(
            grid_gdf,
            TEST_CITY,
            "crime_score",
            save_path=f"data/results/crime_score_map_{TEST_CITY}.png"
        )

        # Generate maps for healthcare metric
        plot_walkscore_map(
            grid_gdf,
            TEST_CITY,
            "healthcare_score",
            save_path=f"data/results/healthcare_score_map_{TEST_CITY}.png"
        )

        # Generate map for burglary safety score
        # Reenable if needed
        '''plot_walkscore_map(
            grid_gdf,
            TEST_CITY,
            "burglary_safety_score",
            save_path=f"data/results/burglary_safety_score_map_{TEST_CITY}.png"
        )'''

        # Generate map for forest fire risk
        plot_walkscore_map(
        grid_gdf,
        TEST_CITY,
        "forest_fire_resistance_score",
        save_path=f"data/results/forest_fire_resistance_map_{TEST_CITY}.png"
        )

        # Generate map for extreme heat risk
        plot_walkscore_map(
            grid_gdf,
            TEST_CITY,
            "extreme_heat_resistance_score",
            save_path=f"data/results/extreme_heat_resistance_map_{TEST_CITY}.png"
        )

        # Generate map for drought resistance
        plot_walkscore_map(
            grid_gdf,
            TEST_CITY,
            "drought_resistance_score",
            save_path=f"data/results/drought_resistance_map_{TEST_CITY}.png"
        )

        # Generate map for flood resistance
        plot_walkscore_map(
            grid_gdf,
            TEST_CITY,
            "flood_resistance_score",
            save_path=f"data/results/flood_resistance_map_{TEST_CITY}.png"
        )

        # Generate map for climate score
        plot_walkscore_map(
        grid_gdf,
        TEST_CITY,
        "climate_score",
        save_path=f"data/results/climate_score_map_{TEST_CITY}.png"
        )

        # Print map generation time
        print(f"Map generation time: {time.time() - time_map_generation:.2f} seconds")

    api_tracker.print_summary()

    # Print total execution time
    total_execution_time = time.time() - total_start_time
    print(f"\nSummary")
    print(f"Total execution time: {total_execution_time:.2f} seconds ({total_execution_time/60:.2f} minutes)")


    upload_time = time.time()
    # Upload to Supabase if enabled

    from config.settings import SAVE_TO_SUPABASE
    if SAVE_TO_SUPABASE:
        print("Saving results to database...")
        from src.utils.supabase_uploader import upload_to_supabase
        upload_to_supabase(grid_gdf, processing_time=total_execution_time)
    print(f"Upload time: {time.time() - upload_time:.2f} seconds")

if __name__ == "__main__":
    main()

