
import os
from dotenv import load_dotenv
from supabase import create_client
from config.settings import TEST_CITY, METRICS_TO_SAVE
import numpy as np
from datetime import datetime

# Set to True to enable testing mode (limited hexagon upload)
TESTING_MODE = False
# Number of hexagons to upload in testing mode
TEST_HEXAGON_COUNT = 1

def upload_to_supabase(grid_gdf, processing_time = None):
    # Limit number of hexagons if in testing mode
    if TESTING_MODE:
        original_count = len(grid_gdf)
        grid_gdf = grid_gdf.head(TEST_HEXAGON_COUNT)
        print(f"TESTING MODE: Limited upload to {TEST_HEXAGON_COUNT} hexagons (out of {original_count})")

    # Load environment variables
    load_dotenv()

    # Get Supabase credentials
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        print("Missing Supabase credentials. Please check your .env file.")
        return

    # Initialize Supabase client
    supabase = create_client(supabase_url, supabase_key)

    print(f"Uploading {len(grid_gdf)} hexagons to Supabase...")

    # Extract city and country
    city_parts = TEST_CITY.split(',')
    city_name = city_parts[0].strip()
    country = city_parts[-1].strip() if len(city_parts) > 1 else "Unknown"

    # Update city record
    city_data = {
        "name": city_name,
        "country": country,
        "processed": True,
        "hexagon_count": len(grid_gdf),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Simple timestamp format
    }

    # Add processing time if provided
    if processing_time is not None:
        city_data["processing_time_seconds"] = int(round(processing_time))

    # Insert or update city record
    supabase.table("cities").upsert(city_data).execute()

    # Prepare hexagon records in batches
    batch_size = 100
    total_batches = (len(grid_gdf) // batch_size) + (1 if len(grid_gdf) % batch_size > 0 else 0)

    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min((batch_num + 1) * batch_size, len(grid_gdf))
        batch = grid_gdf.iloc[start_idx:end_idx]

        records = []

        for idx, hexagon in batch.iterrows():
            # Get H3 index
            h3_index = hexagon["h3_index"]

            # Create base record
            record = {
                "h3_index": h3_index,
                "city_name": city_name,
                "country": country,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Simple timestamp format

            }

            # Add metrics based on METRICS_TO_SAVE mapping
            for db_column, df_column in METRICS_TO_SAVE.items():
                if df_column in hexagon:
                    # Handle special cases for specific columns
                    if db_column != "h3_index":
                        value = hexagon[df_column]
                        # Handle special float values (infinity, NaN)
                        if isinstance(value, float) and (not np.isfinite(value) or np.isnan(value)):
                            record[db_column] = None  # Use NULL in database for these cases
                        else:
                            try:
                                record[db_column] = int(round(value))
                            except (ValueError, OverflowError):
                                # Fallback for any other conversion errors
                                record[db_column] = None
                    else:
                        record[db_column] = hexagon[df_column]

            records.append(record)

        # Upload batch
        supabase.table("hexagons").upsert(records).execute()
        print(f"Uploaded batch {batch_num+1}/{total_batches}")

    print(f"Upload complete: {len(grid_gdf)} hexagons for {city_name}, {country}")