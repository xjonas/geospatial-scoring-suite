# Geospatial Scoring Suite

A modular geospatial analysis platform that calculates location-based scores across Germany using hexagonal grid tessellation. This is repository contains an earlier development version of the propietary [Neivo](https://neivo.de) data solution. The output and includes comprehensive climate and livability data scores that can be used in real-estate, insurance, or other sectors that rely on detailed location risk data.

![Example Infrastructure Safety Score Map for Karlsruhe, Germany](<backend-compute/Core/data/results/infrastructure_safety_score_map_Karlsruhe, Germany.png>)

## Background

Traditional geospatial analysis often relies on administrative boundaries (districts, postal codes), which creates artificial discontinuities in data. This project takes a different approach: it overlays a continuous hexagonal grid across the target area and computes metrics per hexagon. The result is a more granular and spatially consistent representation of location quality.

The scoring engine aggregates data from multiple sources — OpenStreetMap, environmental agencies, satellite imagery, and official statistics — and distills it into normalized 0–100 scores for walkability, climate resilience, livability, and related dimensions.

## Architecture
![Architecture](<architecture.png>)

| Component | Description |
|-----------|-------------|
| **Backend Compute** | Python engine using [H3](https://github.com/uber/h3) for hexagonal indexing |
| **Server** | Handles coordinate-to-hexagon conversion and score retrieval, as well as auth |
| **Frontend** | Simple example React app for visualization (live at [standortscore.de](https://www.standortscore.de/)) |

![Website](<website.png>)

## Data Pipeline

The compute engine processes a target city through the following stages:

1. **Grid Generation** — Tessellates the target area into hexagonal cells using H3. Resolution is configurable based on desired granularity.

2. **Metric Calculation** — Computes individual metrics per hexagon (e.g., intersection density is derived from analyzing the road network graph within each cell and its neighbors).

3. **Composite Scoring** — Normalizes metrics to 0–100 and aggregates them with configurable weights. For example:
   - *Walkability Score* = f(safety, infrastructure, amenity access, ...)
   - *Climate Score* = f(flood risk, heat risk, drought risk)

4. **Storage** — Exports results to GeoPackage (`.gpkg`) and optionally to Postgres

**Data flow details:**
- **Input**: Custom preprocessed datasets in `backend-compute/Core/data/input/`
- **Output**: Visualizations in `backend-compute/Core/data/results/`, raw data to database
- **Caching**: Local caching via `DataManager` to reduce API calls
- **External APIs**: [OpenStreetMap](https://www.openstreetmap.org/), [Open-Meteo](https://open-meteo.com/)

> **Note**: The codebase includes both H3 and a custom hexagon grid implementation. The custom grid was used during development for flexibility; H3 is recommended for production. Both are interoperable for database storage.

## Metrics Reference

| API Key | Name | Description | Range |
|---------|------|-------------|-------|
| `walkability` | Walkscore | Combined accessibility, safety, and infrastructure rating | 0–100 |
| `poi_accessibility_walking` | POI Accessibility | Walking access to shops, amenities, and services | 0–100 |
| `green_space_access` | Green Space Access | Proximity to parks and green areas | 0–100 |
| `infrastructure_safety_walking` | Infrastructure Safety | Quality of sidewalks, crosswalks, and walking paths | 0–100 |
| `intersection_density` | Intersection Density | Street intersection density (higher = more pedestrian-friendly) | 0–100 |
| `walking_safety_crime_accidents` | Walking Safety | Pedestrian safety based on crime and accident data | 0–100 |
| `air_quality` | Air Quality | Pollutant levels (higher = cleaner air) | 0–100 |
| `topography` | Topography | Terrain walkability (higher = flatter) | 0–100 |
| `noise_pollution` | Noise Level | Ambient noise (higher = quieter) | 0–100 |
| `climate_change_resilience` | Climate Resilience | Combined heat, drought, flood, and fire resistance | 0–100 |
| `extreme_heat_resistance` | Heat Resistance | Tolerance to extreme heat events | 0–100 |
| `drought_resistance` | Drought Resistance | Based on historical data and climate projections | 0–100 |
| `flood_resistance` | Flood Resistance | Based on elevation, drainage, and infrastructure | 0–100 |
| `forest_fire_resistance` | Fire Resistance | Based on vegetation and fire management | 0–100 |
| `healthcare_access` | Healthcare Access | Proximity to healthcare facilities | 0–100 |
| `crime_safety_living` | Crime Safety | Residential safety based on crime statistics | 0–100 |
| `poi_access_overall` | POI Access (Overall) | General amenity access by any transport mode | 0–100 |
| `poi_accessibility_amenity_walking` | Amenity Access | Walking access to public services | 0–100 |
| `poi_accessibility_shop_walking` | Shop Access | Walking access to retail | 0–100 |
| `poi_accessibility_leisure_walking` | Leisure Access | Walking access to leisure facilities | 0–100 |
| `poi_access_grocery` | Grocery Access | Access to grocery stores | 0–100 |
| `poi_access_cafe` | Café Access | Access to cafés and restaurants | 0–100 |
| `poi_access_shopping` | Shopping Access | Access to shopping facilities | 0–100 |
| `poi_access_nightlife` | Nightlife Access | Access to bars and clubs | 0–100 |
| `poi_access_pharmacy` | Pharmacy Access | Access to pharmacies | 0–100 |
| `poi_access_fitness` | Fitness Access | Access to gyms and fitness facilities | 0–100 |
| `accident_safety_pedestrian` | Pedestrian Accident Safety | Based on historical traffic accident data | 0–100 |
| `crime_rate_safety` | Crime Rate Safety | Based on regional crime data (excl. burglary) | 0–100 |
| `burglary_safety` | Burglary Safety | Based on burglary statistics | 10–100 |
| `noise_level_db` | Noise (dB) | Raw noise level | dB |
| `air_pollutants_health_impact` | Pollutant Health Impact | Health impact from PM2.5, NO2, etc. | 0–100 |
| `topography_slope_perc` | Slope | Terrain slope percentage | % |
| `green_area_perc` | Green Coverage | Percentage of hexagon covered by green space | 0–100% |
| `accident_count_5y_int` | Accident Count | Traffic accidents in past 5 years | Integer |
| `distance_to_water_m` | Distance to Water | Distance to nearest water body | Meters |
| `green_area_m2` | Green Area | Green space area within hexagon | m² |

## Getting Started

Each component (backend, API server, frontend) can run independently.

**Quick start (compute only):**
```bash
# 1. Set target city
# Edit backend-compute/Core/config/settings.py

# 2. Run compute engine
python backend-compute/Core/main.py
```

**Full stack setup:**
1. Set target city in `backend-compute/Core/config/settings.py`
2. Run `python backend-compute/Core/main.py` (set `SAVE_TO_SUPABASE=True` for database upload)
3. Create Postgres database with schema from `backend-compute/Core/src/utils/supabase_upload.py`
4. Configure `.env` files in `backend-compute/` and `server/` with database credentials
5. Generate an API key and add it to `server/.env`
6. Deploy `server/` (e.g., Vercel, AWS)
7. Deploy `frontend-website/`

## Resources

- **API Reference**: [Notion Documentation](https://electric-fight-544.notion.site/API-Reference-1ce08bb8e5cc80fe8532ef8bc63c21e3?pvs=4)
- **Frontend Demo**: See `frontend-website/` directory
