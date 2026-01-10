# Geospatial Scoring Engine for Germany

## Summary
This project implements a comprehensive geospatial scoring engine designed to calculate granular location scores for the entire territory of Germany. Instead of relying on traditional administrative boundaries it utilizes a hexagonal grid structure to provide continuous, high-resolution geospatial analysis. 

The system aggregates data from varied sources (OpenStreetMap, environmental agencies, satellite data, official statistics), maps it to these hexagons, and computes complex composite scores for Walkability, Climate Resilience, General Livability, and more. These scores are then served via a custom API server to incorporate into user applications. This repository contains the backend compute engine, the API server, and an example frontend. It is based on the earlier version of the [Neivo](https://neivo.de) platform which uses more comprehensive data sources, more advanced metrics and more tailored algorithms.

![Example Infrastructure Safety Score Map for Karlsruhe, Germany](<backend-compute/Core/data/results/infrastructure_safety_score_map_Karlsruhe, Germany.png>)

## Architecture
The system is composed of four main pillars:

**Backend Compute**: Asynchronous Python-based engine using h3 lib writing to a Postgres database.
**Database**: Postgres database storing hexagon H3 id and respective scores.
**API Server Middleman**: A lightweight service connecting the database to any client. Converts coordinates to hexagon id, security checks and returns the scores.
**Frontend**: A simple React application (see [standortscore.de](https://www.standortscore.de/)) that visualizes the scores on a dashboard and an interactive map.

![Architecture](<architecture.png>)

![Website](<website.png>)

## Data Processing Pipeline
The compute engine transforms and calculates the scores for a given city in Germany through a pipeline with functionality like caching.

- Input: Find custom sources in `backend-compute/Core/data/input/`. The csv files were preprocessed in previous projects and cleaned from the original sources and are free to use.
- Output: Visualized results are stored in `backend-compute/Core/data/results/` (see exxample pictures for Karlsruhe, Germany) and the raw data is pushed to a Postgres database.
- Caching: The compute engine caches the results in a local directory to limit the number of API calls and reduce the load on the database. The caching is handled by the DataManager class. 
- External API usage: The engine uses external APIs to fetch data from [OpenStreetMap](https://www.openstreetmap.org/) and [Open-Meteo](https://open-meteo.com/).
- Api counter: The engine counts the number of API calls to limit the number of calls and ensure compliance with the external API usage policy.


1. Grid Generation: 
   - The target area is tesselated into hexagonal cells. The backbone is the usage of H3, a Hexagonal Hierarchical Spatial Indexing System (https://github.com/uber/h3). The number of hexagons is dependent on the city size and adjustable resolution. **NOTE:** This version contains both the H3 hexagonal grid as well as a custom hexagon grid. The custom was used for development purposes and is more flexible but slower; However H3 is more efficient and recommended for production use. For intercomopatability, the metrics are calculated for both grids and then converted/combinded into single H3 output for database storage.
   
2. Data Ingestion & Mapping:
   - Infrastructure: Road networks, areas, and point of interest (POIs) are fetched via OpenStreetMap (OSMNX).
   - Points of Interest: Shops, healthcare, and amenities are mapped to nearest hexagons.
   - Environmental Data: Noise levels, pollution sensors, and topographical data are overlaid onto the grid. The data is fetched from various sources and processed to be used in the metrics.

3. Metric Calculation:
   - For every single hexagon, individual metrics are calculated in parallel.
   - Example: The "Intersection Density" for a hexagon is computed by analyzing the simplified road network graph within that specific cell and its neighbors.

4. Composite Scoring:
   - Individual metrics are normalized (0-100) and weighted based on importance. Some metrics are aggregated to a composite score. For example:
   - Walkability Score: Aggregates safety, infrastructure, and amenities.
   - Climate Score: Aggregates flood, heat, and drought risks.

5. Storage:
   - Final scores are exported to a Postgres database, storing hexagon H3 id and respective scores.

## Metrics Overview
The engine currently computes the following metrics:

<!-- PASTE TABLE HERE -->

| API Metric Key | Metric Name | Description | Range |
| --- | --- | --- | --- |
| `walkability` | Walkscore | Overall walkability of the area, combining accessibility, safety, and infrastructure factors. | 0–100 |
| `poi_accessibility_walking` | POI Accessibility Score | Access to points of interest (e.g., shops, amenities) within walking distance. | 0–100 |
| `green_space_access` | Green Space Score | Proximity and availability of parks and green spaces within walking distance. | 0–100 |
| `infrastructure_safety_walking` | Infrastructure Safety Score | Quality and safety of walking infrastructure, such as sidewalks and crosswalks. | 0–100 |
| `intersection_density` | Intersection Density Score | Density of street intersections, indicating pedestrian-friendly urban design. | 0–100 |
| `walking_safety_crime_accidents` | Walking Safety Score | Safety for pedestrians based on crime rates and traffic accident data. | 0–100 |
| `air_quality` | Pollution Score | Air quality based on pollutant levels, with higher scores indicating cleaner air. | 0–100 |
| `topography` | Topography Score | Terrain walkability, with higher scores indicating flatter, easier-to-walk areas. | 0–100 |
| `noise_pollution` | Noise Model Score | Noise levels, with higher scores indicating quieter areas. | 0–100 |
| `climate_change_resilience` | Climate Score | Overall resilience to climate change impacts, combining heat, drought, flood, and fire resistance. | 0–100 |
| `extreme_heat_resistance` | Extreme Heat Resistance Score | Ability to withstand extreme heat events, based on urban design and vegetation. | 0–100 |
| `drought_resistance` | Drought Resistance Score | Resistance to drought conditions, based on historic data, climate model predictions and land usage. | 0–100 |
| `flood_resistance` | Flood Resistance Score | Resistance to flooding, based on elevation, drainage, and infrastructure. | 0–100 |
| `forest_fire_resistance` | Forest Fire Resistance Score | Resistance to forest fires, based on vegetation and fire management practices. | 0–100 |
| `healthcare_access` | Healthcare Score | Proximity and availability of healthcare facilities. | 0–100 |
| `crime_safety_living` | Crime Score | General safety for residents, based on crime and burglary statistics. | 0–100 |
| `poi_access_overall` | POI Access Overall Score | General access to amenities, including by car or walking. | 0–100 |
| `poi_accessibility_amenity_walking` | POI Accessibility Amenity Score | Access to general amenities (e.g., public services) within walking distance. | 0–100 |
| `poi_accessibility_shop_walking` | POI Accessibility Shop Score | Access to retail shops within walking distance. | 0–100 |
| `poi_accessibility_leisure_walking` | POI Accessibility Leisure Score | Access to leisure facilities (e.g., parks, theaters) within walking distance. | 0–100 |
| `poi_access_grocery` | POI Access Grocery Score | Access to grocery stores, including by car or other transportation. | 0–100 |
| `poi_access_cafe` | POI Access Cafe Score | Access to cafes and restaurants, including by car or other transportation. | 0–100 |
| `poi_access_shopping` | POI Access Shopping Score | Access to shopping facilities, including by car or other transportation. | 0–100 |
| `poi_access_nightlife` | POI Access Nightlife Score | Access to nightlife venues (e.g., bars, clubs), including by car or other transportation. | 0–100 |
| `poi_access_pharmacy` | POI Access Pharmacy Score | Access to pharmacies, including by car or other transportation. | 0–100 |
| `poi_access_fitness` | POI Access Fitness Score | Access to fitness facilities (e.g., gyms), including by car or other transportation. | 0–100 |
| `accident_safety_pedestrian` | Accident Safety Score | Safety for pedestrians based on historical traffic accident data. | 0–100 |
| `crime_rate_safety` | Crime Safety Score | Safety based on regional crime data, excluding burglary. | 0–100 |
| `burglary_safety` | Burglary Safety Score | Safety based on burglary statistics. | 10–100 |
| `noise_level_db` | Noise Model Level | Raw noise level in decibels, with lower values indicating quieter areas. | Raw dB |
| `air_pollutants_health_impact` | Pollution Health Impact | Health impact from air pollutants (e.g., PM2.5, NO2), with higher scores indicating lower impact, preprocessed data to main air_quality metric . | 0–100 |
| `topography_slope_perc` | Topography Slope | Actual slope percentage of the terrain, with lower values indicating flatter areas. | % |
| `green_area_perc` | Green Percentage | Percentage of the hexagon covered by green spaces. | 0–100% |
| `accident_count_5y_int` | Accident Count | Number of traffic accidents in the hexagon over the past 5 years. | Integer |
| `distance_to_water_m` | Distance to Water | Distance to the nearest water body, in meters. | Meters |
| `green_area_m2` | Green Area | Total area of green space within the hexagon, in square meters. | m² |


## Documentation and How to Use
- Backend compute, api server and frontened can be used separately.
- To be able to use the full stack, you need to have a Postgres database hosted (eg. Supabase) and put the credentials in the .env files of `backend-compute/` and `server/`. You also need to host the API server, which can be done with any server (eg. Vercel, AWS, etc. - in this case Vercel was used). In the .env file of the frontend, you need to put the API server URL and the API key that you created for your application and can be for example created manually in put in your database, or the built-in auth system of your database provider.

1. Change settings and city in `backend-compute/Core/config/settings.py`
2. Run in `backend-compute/Core/main.py` 

- **API Reference**: [Click here for Notion Docs](https://electric-fight-544.notion.site/API-Reference-1ce08bb8e5cc80fe8532ef8bc63c21e3?pvs=4)
- **Frontend Demo**: See `frontend-website/` directory.
