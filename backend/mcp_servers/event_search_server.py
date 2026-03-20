"""
Event Search MCP Server

Wraps the Ticketmaster Discovery API and exposes search/detail tools
so the Leisure Search Agent can find external events (concerts, sports,
shows) without directly depending on the HTTP layer.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastmcp import FastMCP

from config import settings

logger = logging.getLogger(__name__)

mcp = FastMCP("EventSearch")

TICKETMASTER_BASE_URL = "https://app.ticketmaster.com/discovery/v2"

# Estimated durations (minutes) when the API only provides a start time
CATEGORY_DURATION: dict[str, int] = {
    "music": 180,
    "sports": 150,
    "arts": 120,
    "theatre": 120,
    "film": 120,
    "family": 120,
    "miscellaneous": 120,
}

# Map Ticketmaster segment names to our normalized categories
SEGMENT_MAP: dict[str, str] = {
    "Music": "music",
    "Sports": "sports",
    "Arts & Theatre": "arts",
    "Film": "film",
    "Miscellaneous": "miscellaneous",
    "Undefined": "miscellaneous",
}


async def _ticketmaster_request(endpoint: str, params: dict) -> dict | None:
    """Make a request to the Ticketmaster Discovery API."""
    api_key = settings.TICKETMASTER_API_KEY
    if not api_key:
        logger.warning("TICKETMASTER_API_KEY not set — returning empty results")
        return None

    params["apikey"] = api_key

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{TICKETMASTER_BASE_URL}{endpoint}", params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        logger.error("Ticketmaster API request timed out")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"Ticketmaster API error: {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Ticketmaster API unexpected error: {e}")
        return None


def _normalize_event(raw: dict) -> dict:
    """Normalize a Ticketmaster event into our standard schema."""
    # Category
    segment_name = ""
    classifications = raw.get("classifications", [])
    if classifications:
        segment_name = classifications[0].get("segment", {}).get("name", "")
    category = SEGMENT_MAP.get(segment_name, "miscellaneous")

    # Dates
    dates = raw.get("dates", {})
    start_obj = dates.get("start", {})
    start_date = start_obj.get("dateTime") or start_obj.get("localDate")

    end_date = None
    end_obj = dates.get("end", {})
    if end_obj:
        end_date = end_obj.get("dateTime") or end_obj.get("localDate")

    duration = CATEGORY_DURATION.get(category, 120)

    if start_date and not end_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            end_dt = start_dt + timedelta(minutes=duration)
            end_date = end_dt.isoformat()
        except (ValueError, TypeError):
            pass

    # Venue
    venues = raw.get("_embedded", {}).get("venues", [])
    venue_name = ""
    venue_address = ""
    city = ""
    if venues:
        v = venues[0]
        venue_name = v.get("name", "")
        addr = v.get("address", {})
        venue_address = addr.get("line1", "")
        city_obj = v.get("city", {})
        city = city_obj.get("name", "")

    # Price
    price_ranges = raw.get("priceRanges", [])
    price_range = ""
    if price_ranges:
        pr = price_ranges[0]
        lo = pr.get("min")
        hi = pr.get("max")
        currency = pr.get("currency", "USD")
        if lo is not None and hi is not None:
            price_range = f"${lo:.0f} - ${hi:.0f}" if currency == "USD" else f"{lo:.0f} - {hi:.0f} {currency}"
        elif lo is not None:
            price_range = f"From ${lo:.0f}" if currency == "USD" else f"From {lo:.0f} {currency}"

    # Image
    images = raw.get("images", [])
    image_url = images[0].get("url", "") if images else ""

    return {
        "external_id": raw.get("id", ""),
        "title": raw.get("name", ""),
        "description": raw.get("info", raw.get("pleaseNote", "")),
        "start_date": start_date,
        "end_date": end_date,
        "duration": duration,
        "venue_name": venue_name,
        "venue_address": venue_address,
        "city": city,
        "category": category,
        "price_range": price_range,
        "url": raw.get("url", ""),
        "image_url": image_url,
    }


@mcp.tool()
async def search_events(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    location: Optional[str] = None,
    category: Optional[str] = None,
    radius: Optional[int] = None,
    size: int = 10,
) -> list[dict]:
    """Search for external events (concerts, sports, shows) via Ticketmaster."""
    params: dict = {"keyword": query, "size": min(size, 50)}

    if start_date:
        params["startDateTime"] = start_date.replace("+", "") + "Z" if "T" in start_date else start_date + "T00:00:00Z"
    if end_date:
        params["endDateTime"] = end_date.replace("+", "") + "Z" if "T" in end_date else end_date + "T23:59:59Z"
    if location:
        params["city"] = location
    if category:
        # Map our category back to Ticketmaster segment
        segment_id_map = {
            "music": "KZFzniwnSyZfZ7v7nJ",
            "sports": "KZFzniwnSyZfZ7v7nE",
            "arts": "KZFzniwnSyZfZ7v7na",
            "film": "KZFzniwnSyZfZ7v7nn",
            "family": "KZFzniwnSyZfZ7v7n1",
        }
        seg_id = segment_id_map.get(category.lower())
        if seg_id:
            params["segmentId"] = seg_id
    if radius:
        params["radius"] = radius
        params["unit"] = "miles"

    data = await _ticketmaster_request("/events.json", params)
    if not data:
        return []

    embedded = data.get("_embedded", {})
    events = embedded.get("events", [])
    return [_normalize_event(ev) for ev in events]


@mcp.tool()
async def get_event_details(event_id: str) -> dict | None:
    """Get detailed information about a specific Ticketmaster event."""
    data = await _ticketmaster_request(f"/events/{event_id}.json", {})
    if not data:
        return None
    return _normalize_event(data)
