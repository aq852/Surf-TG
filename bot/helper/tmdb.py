"""Small, optional TMDB client used only by the administrator Poster Studio."""

from aiohttp import ClientSession, ClientTimeout

from bot import LOGGER
from bot.config import Telegram


TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"


async def search_posters(query: str, limit: int = 12):
    """Return safe poster choices, or an empty list when TMDB is unavailable."""
    token = Telegram.TMDB_READ_ACCESS_TOKEN
    query = " ".join(str(query or "").split())[:180]
    if not token or not query:
        return []
    try:
        headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}
        params = {"query": query, "include_adult": "false", "language": "en-US"}
        timeout = ClientTimeout(total=8)
        async with ClientSession(timeout=timeout) as session:
            async with session.get(TMDB_SEARCH_URL, params=params, headers=headers) as response:
                if response.status != 200:
                    LOGGER.warning("TMDB poster search returned HTTP %s", response.status)
                    return []
                payload = await response.json()
    except Exception as exc:
        LOGGER.warning("TMDB poster search failed: %s", exc)
        return []

    choices = []
    for item in payload.get("results", []):
        if item.get("media_type") not in {"movie", "tv"} or not item.get("poster_path"):
            continue
        title = item.get("title") or item.get("name") or "Untitled"
        date = item.get("release_date") or item.get("first_air_date") or ""
        choices.append({
            "title": str(title),
            "year": str(date)[:4],
            "kind": "Series" if item.get("media_type") == "tv" else "Movie",
            "poster_url": f"{TMDB_IMAGE_URL}{item['poster_path']}",
        })
        if len(choices) >= limit:
            break
    return choices
