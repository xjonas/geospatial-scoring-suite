GENERATE_MAPS = False  # Set to False to disable map generation
SAVE_TO_SUPABASE = True  # Set to True to enable saving to Supabase

# Initial test city
TOWN = ""  # could be a district of the city (NOT NEEDED IN THIS VERSION)
TEST_CITY = "Kiel, Germany" # should be the parent muncipality (administrative unit/boundary)
TEST_CITY_PLZ = ""  # Postal code (ONlY NEEDED IF PART OF "KREIS")
BUNDESLAND = "schleswig-holstein"  #
GKZ = ""  # Gemeindekennziffer (municipality code) (NOT NEEDED IN THIS VERSION)

# CRS (Coordinate Reference System) for Germany
GERMANY_CRS = 3035  

# Hexagon grid settings
HEXAGON_SIZE = 300  # meters (diameter of circumscribed circle)

# Intersection settings: buffer around each node
INTERSECTION_CONSOLIDATION_TOLERANCE = 5  # meters
MAX_INTERSECTION_DENSITY = 50  # Theoretical maximum intersections per hexagon

# Percentage of green space coverage that equals a 100 score (not used for walkability)
MAX_GREEN_PERCENTAGE = 60.0

# POI metric settings
POI_MAX_DISTANCE = 1200  # Meters - maximum distance to consider for POI accessibility
POI_INFLUENCE_RADIUS = 600  # Meters - distance at which POI influence is halved
DISTANCE_DECAY_EXPONENT = 0.003 # Exponent for distance decay function
# Distance decay parameters (different from walkability - slower decay for car travel)
DISTANCE_DECAY_POI_ACCESS = 0.0008 # Exponent for distance decay function for POI access
POI_ACCESS_MAX_DISTANCE = 10000  # Meters - maximum distance to consider for POI accessibility

# Weights for metrics
# For walkability the weights were based on the following main paper:
# Jehle, U., & Pajares, E. (2021). Analyse der Fußwegequalitäten zu Schulen: Entwicklung von Indikatoren auf Basis
# von OpenData. In Flächennutzungsmonitoring XIII: Flächenpolitik - Konzepte - Analysen - Tools (S. 221-231). Berlin:
# Rhombos-Verlag. https://doi.org/10.26084/13dfns-p020
# AND
# Ewing, R., & Cervero, R. (2010). Travel and the Built Environment: A Meta-Analysis. Journal of the American
# Planning Association, 76(3), 265–294. https://doi.org/10.1080/01944361003766766
WEIGHTS = {
    "intersection_density": 0.20,
    "poi_accessibility": 0.28,
    "green_space": 0.15,
    "infrastructure_safety": 0.12,
    "walking_safety": 0.07,
    "pollution": 0.05,
    "topography": 0.08,
    "noise_model": 0.05
}

# Data caching settings
CACHE_ENABLED = True  # Enable/disable data caching
CACHE_EXPIRY_DAYS = 30  # Number of days before cache expires
CACHE_DIR = "data/cache"  # Directory for cache files

# Processing settings
CHUNK_SIZE = 50  # Number of grid cells to process at once 
MULTITHREADING_ENABLED = False  # Enable/disable multithreading (experimental)

# H3 Grid Settings
USE_H3 = True
H3_RESOLUTION = 9  # Resolution level 9 ≈ 174m hexagons
# Resolution level 8 ≈ 461m hexagons
# Resolution level 7 ≈ 1.22km hexagons

# Database settings
# Metrics to save to database
# Dictionary mapping database column names to DataFrame column names
# Format: 'database_column_name': 'dataframe_column_name'

METRICS_TO_SAVE = {
    # Main Walkability Score
    'walkability': 'walkscore',  # 0-100, Overall walkability of the area

    # Primary Walkability Component Metrics
    'poi_accessibility_walking': 'poi_accessibility_score',  # 0-100, Access to points of interest
    'green_space_access': 'green_space_score',  # 0-100, Access to green spaces
    'infrastructure_safety_walking': 'infrastructure_safety_score',  # 0-100, Quality and safety of walking infrastructure
    'intersection_density': 'intersection_density_score',  # 0-100, Density of street intersections
    'walking_safety_crime_accidents': 'walking_safety_score',  # 0-100, Safety for pedestrians based on accidents and crime
    'air_quality': 'pollution_score',  # 0-100, Air quality (higher = better)
    'topography': 'topography_score',  # 0-100, Terrain walkability (higher = flatter/easier)
    'noise_pollution': 'noise_model_score',  # 0-100, Noise levels (higher = quieter)

    # Climate Resilience Metrics
    'climate_change_resilience': 'climate_score',  # 0-100, Overall climate change resilience
    'extreme_heat_resistance': 'extreme_heat_resistance_score',  # 0-100, Resistance to heat waves
    'drought_resistance': 'drought_resistance_score',  # 0-100, Resistance to drought conditions
    'flood_resistance': 'flood_resistance_score',  # 0-100, Resistance to flooding
    'forest_fire_resistance': 'forest_fire_resistance_score',  # 0-100, Resistance to forest fires

    # Additional Quality of Life Metrics
    'healthcare_access': 'healthcare_score',  # 0-100, Access to healthcare facilities
    'crime_safety_living': 'crime_score',  # 0-100, Area safety based on crime data, burglary + crime
    'poi_access_overall': 'poi_access_overall_score',  # 0-100, General access to amenities (including by car)

    # POI Accessibility Submetrics (Walking)
    'poi_accessibility_amenity_walking': 'poi_accessibility_amenity_score',  # 0-100, Access to amenities
    'poi_accessibility_shop_walking': 'poi_accessibility_shop_score',  # 0-100, Access to shops
    'poi_accessibility_leisure_walking': 'poi_accessibility_leisure_score',  # 0-100, Access to leisure facilities

    # POI Access Submetrics (Including Car Transportation)
    'poi_access_grocery': 'poi_access_grocery_score',  # 0-100, Access to grocery stores
    'poi_access_cafe': 'poi_access_cafe_score',  # 0-100, Access to cafes and restaurants
    'poi_access_shopping': 'poi_access_shopping_score',  # 0-100, Access to shopping facilities
    'poi_access_nightlife': 'poi_access_nightlife_score',  # 0-100, Access to nightlife venues
    'poi_access_pharmacy': 'poi_access_pharmacy_score',  # 0-100, Access to pharmacies
    'poi_access_fitness': 'poi_access_fitness_score',  # 0-100, Access to fitness facilities

    # Safety Component Metrics
    'accident_safety_pedestrian': 'accident_safety_score',  # 0-90, Safety based on accident data
    'crime_rate_safety': 'crime_safety_score',  # 20-100, Safety based on regional crime data
    'burglary_safety': 'burglary_safety_score',  # 10-100, Safety based on burglary statistics

    # Environmental Detailed Metrics
    'noise_level_db': 'noise_model_level',  # Raw dB, Noise level in decibels
    #'air_pollutants_health_impact': 'pollution_health_impact',  # 0-100, Health impact from pollution PM2.5 and NO2
    'topography_slope_perc': 'topography_slope',  # %, Actual slope percentage

    # Raw Data Values (For Detailed Analysis)
    'green_area_perc': 'green_percentage',  # 0-100%, Percentage of hexagon covered by green space
    'accident_count_5y_int': 'accident_count',  # Integer, Number of accidents in the hexagon
    'distance_to_water_m': 'distance_to_water',  # Meters, Distance to nearest water body
    #'green_area_m2': 'green_area',  # m², Area of green space within hexagon
}