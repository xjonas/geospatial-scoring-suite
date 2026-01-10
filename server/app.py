import os
import time
import h3
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Request, Header, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional, Any, Union
import logging
from supabase import create_client, Client
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Configuration class
class Config:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    H3_RESOLUTION = int(os.getenv("H3_RESOLUTION", "9"))
    API_KEYS_TABLE = "api_keys"
    API_USAGE_TABLE = "api_usage"
    HEXAGONS_TABLE = "hexagons"
    MAX_BULK_HEXAGONS = 100

    @classmethod
    def validate(cls):
        if not cls.SUPABASE_URL or not cls.SUPABASE_KEY:
            raise ValueError("Missing required Supabase configuration")

# Validate config on startup
Config.validate()

# Security scheme
security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    logger.info("Starting Neighborhood Scoring API")
    try:
        supabase = get_supabase_client()
        response = supabase.table(Config.API_KEYS_TABLE).select("count", count='exact').limit(0).execute()
        logger.info("Successfully connected to Supabase")
    except Exception as e:
        logger.error(f"CRITICAL: Failed to connect to Supabase: {e}")
        raise

    yield
    logger.info("Shutting down Neighborhood Scoring API")

# Initialize FastAPI app
app = FastAPI(
    title="Neighborhood Scoring API",
    description="Secure API for retrieving neighborhood scores",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Pydantic Models
class ScoreResponse(BaseModel):
    latitude: float
    longitude: float
    city_name: str
    country: str
    scores: Dict[str, Any]
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

class BulkScoreRequest(BaseModel):
    hexagons: List[str] = Field(..., max_items=Config.MAX_BULK_HEXAGONS)
    metrics: Optional[List[str]] = None

    @field_validator('hexagons')
    @classmethod
    def validate_hexagons(cls, v):
        if not v:
            raise ValueError("At least one hexagon ID is required")
        return v

class BulkScoreResponse(BaseModel):
    results: List[Dict[str, Union[str, float, int, None]]]
    metadata: Dict[str, Any]

# Supabase client
_supabase_client = None

def get_supabase_client() -> Client:
    global _supabase_client
    if _supabase_client is None:
        try:
            _supabase_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
            logger.info("Supabase client initialized")
        except Exception as e:
            logger.error("Failed to initialize Supabase client")
            raise RuntimeError(f"Could not initialize Supabase client: {e}")
    return _supabase_client

# API key validation
async def validate_api_key(
        request: Request,
        authorization: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """Validate API key from Authorization header."""
    api_key = authorization.credentials

    logger.info(f"API key validation attempt from {request.client.host if request.client else 'unknown'}")

    supabase = get_supabase_client()

    try:
        # Validate API key
        key_response = supabase.table(Config.API_KEYS_TABLE) \
            .select("id") \
            .eq("key", api_key) \
            .limit(1) \
            .execute()

        if not key_response.data:
            logger.warning("Invalid API key attempted")
            raise HTTPException(
                status_code=401,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"}
            )

        api_key_id = str(key_response.data[0]["id"])

        rpc_response = supabase.rpc(
            'handle_api_usage_and_check_limits',
            {'key_id': api_key_id}
        ).execute()

        result = rpc_response.data

        request.state.rate_limit_info = result

        if not result.get('success', False):
            logger.warning(f"Rate limit exceeded for key ID: {api_key_id}")
            raise HTTPException(
                status_code=429,
                detail=result.get('error', 'Rate limit exceeded'),
                headers={
                    "X-Rate-Limit-Daily-Remaining": str(max(0, (result.get('daily_limit') or 0) - (result.get('daily_count') or 0))),
                    "X-Rate-Limit-Monthly-Remaining": str(max(0, (result.get('monthly_limit') or 0) - (result.get('monthly_count') or 0))),
                    "X-Rate-Limit-Reset": (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()
                }
            )

        logger.info(f"API key validated successfully")
        return api_key_id

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during API key validation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def get_h3_index(lat: float, lon: float) -> str:
    """Convert coordinates to H3 index with validation."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(
            status_code=400,
            detail="Invalid coordinates: latitude must be [-90,90], longitude [-180,180]"
        )

    try:
        return h3.latlng_to_cell(lat, lon, Config.H3_RESOLUTION)
    except Exception as e:
        logger.error(f"Error generating H3 index: {e}")
        raise HTTPException(status_code=500, detail="Error processing coordinates")

async def get_hexagon_scores(h3_index: str, metrics: Optional[List[str]] = None) -> Dict[str, Any]:
    """Retrieve scores for a hexagon."""
    supabase = get_supabase_client()

    required_fields = ["h3_index", "city_name", "country"]
    select_query = ",".join(set(required_fields + (metrics or []))) if metrics else "*"

    try:
        response = supabase.table(Config.HEXAGONS_TABLE) \
            .select(select_query) \
            .eq("h3_index", h3_index) \
            .limit(1) \
            .execute()

        if not response.data:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for location"
            )

        hexagon_data = response.data[0]
        non_score_fields = {"h3_index", "city_name", "country", "created_at", "updated_at", "id"}

        scores = {
            k: v for k, v in hexagon_data.items()
            if k not in non_score_fields and v is not None
        }

        return {
            "scores": scores,
            "city_name": hexagon_data.get("city_name", "Unknown"),
            "country": hexagon_data.get("country", "Unknown")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    """Log requests and add rate limit headers."""
    start_time = time.time()

    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.4f}"

        if hasattr(request.state, 'rate_limit_info'):
            result = request.state.rate_limit_info
            daily_limit = result.get('daily_limit')
            monthly_limit = result.get('monthly_limit')
            daily_count = result.get('daily_count', 0)
            monthly_count = result.get('monthly_count', 0)

            # Calculate remaining
            daily_remaining = max(0, (daily_limit or 0) - daily_count) if daily_limit is not None else "unlimited"
            monthly_remaining = max(0, (monthly_limit or 0) - monthly_count) if monthly_limit is not None else "unlimited"

            response.headers["X-Rate-Limit-Daily-Remaining"] = str(daily_remaining)
            response.headers["X-Rate-Limit-Monthly-Remaining"] = str(monthly_remaining)
            response.headers["X-Rate-Limit-Daily-Limit"] = str(daily_limit) if daily_limit is not None else "unlimited"
            response.headers["X-Rate-Limit-Monthly-Limit"] = str(monthly_limit) if monthly_limit is not None else "unlimited"
            response.headers["X-Rate-Limit-Reset"] = (
                    datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) +
                    timedelta(days=1)
            ).isoformat()

        client_host = request.client.host if request.client else "unknown"
        logger.info(
            f"{client_host} - {request.method} {request.url.path} - "
            f"{response.status_code} - {process_time:.4f}s"
        )

        return response

    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"Request failed: {request.method} {request.url.path} - {process_time:.4f}s")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error"}
        )

# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    }

@app.get("/scores", response_model=ScoreResponse)
async def get_scores(
        request: Request,
        lat: float = Query(..., description="Latitude", ge=-90.0, le=90.0),
        lon: float = Query(..., description="Longitude", ge=-180.0, le=180.0),
        metrics: Optional[str] = Query(None, description="Comma-separated metrics"),
        api_key_id: str = Depends(validate_api_key)
):
    """Get neighborhood scores for coordinates."""
    metrics_list = [m.strip() for m in metrics.split(',')] if metrics else None

    h3_index = get_h3_index(lat, lon)
    scores_result = await get_hexagon_scores(h3_index, metrics_list)

    return ScoreResponse(
        latitude=lat,
        longitude=lon,
        city_name=scores_result["city_name"],
        country=scores_result["country"],
        scores=scores_result["scores"]
    )

@app.get("/available-metrics")
async def get_available_metrics(api_key_id: str = Depends(validate_api_key)):
    """Get available metrics from database."""
    supabase = get_supabase_client()

    try:
        # Fetch one row to inspect columns
        response = supabase.table(Config.HEXAGONS_TABLE) \
            .select("*") \
            .limit(1) \
            .execute()

        if not response.data:
            logger.warning("Hexagons table is empty")
            return {"available_metrics": []}

        # Extract column names
        all_columns = response.data[0].keys()

        # Filter out non-metric fields
        non_metric_fields = {
            "id", "h3_index", "city_name", "country",
            "created_at", "updated_at", "geometry"
        }

        available_metrics = sorted([
            col for col in all_columns
            if col not in non_metric_fields
        ])

        return {"available_metrics": available_metrics}

    except Exception as e:
        logger.error(f"Error fetching available metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail="Database error while fetching available metrics"
        )


@app.post("/scores/bulk", response_model=BulkScoreResponse)
async def get_bulk_scores(
        request: BulkScoreRequest,
        api_key_id: str = Depends(validate_api_key)
):
    """Get scores for multiple hexagons."""
    start_time = time.time()
    results = []
    successful = 0
    failed = 0

    for hexagon_id in request.hexagons:
        try:
            # Calculate coordinates from hexagon ID
            lat, lng = h3.cell_to_latlng(hexagon_id)

            # Get scores for this hexagon
            score_data = await get_hexagon_scores(hexagon_id, request.metrics)

            # Create flat result structure
            result = {
                "hexagon_id": hexagon_id,
                "lat": lat,
                "lng": lng,
                "city_name": score_data["city_name"],
                "country": score_data["country"],
                "status": "success"
            }

            # Add scores at top level
            result.update(score_data["scores"])

            results.append(result)
            successful += 1

        except HTTPException as e:
            if e.status_code == 404:
                # Not found case
                lat, lng = h3.cell_to_latlng(hexagon_id)
                results.append({
                    "hexagon_id": hexagon_id,
                    "lat": lat,
                    "lng": lng,
                    "city_name": None,
                    "country": None,
                    "status": "not_found"
                })
            else:
                # Other HTTP error
                results.append({
                    "hexagon_id": hexagon_id,
                    "lat": 0.0,
                    "lng": 0.0,
                    "city_name": None,
                    "country": None,
                    "status": "error"
                })
            failed += 1

        except Exception as e:
            # Error calculating coordinates or processing
            logger.warning(f"Error processing hexagon {hexagon_id}: {e}")
            results.append({
                "hexagon_id": hexagon_id,
                "lat": 0.0,
                "lng": 0.0,
                "city_name": None,
                "country": None,
                "status": "error"
            })
            failed += 1

    processing_time = time.time() - start_time

    # Return response
    return BulkScoreResponse(
        results=results,
        metadata={
            "total_requested": len(request.hexagons),
            "successful": successful,
            "failed": failed,
            "processing_time": round(processing_time, 4)
        }
    )


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
        headers=getattr(exc, 'headers', {})
    )

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
