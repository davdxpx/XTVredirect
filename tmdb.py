import httpx
from config import Config
from utils.logger import setup_logger

logger = setup_logger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"
# Using w780 for high quality but reasonable size.
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w780"

class TMDBClient:
    def __init__(self):
        self.api_key = Config.TMDB_API_KEY

    async def _request(self, endpoint, params=None):
        if params is None:
            params = {}

        # Add API Key authentication
        params['api_key'] = self.api_key
        params['language'] = 'en-US'

        url = f"{TMDB_BASE_URL}/{endpoint}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"TMDb API Error on {endpoint}: {e}")
                return None

    async def search(self, query):
        """
        Search for TV shows and Movies.
        Returns a list of simplified results (max 5).
        """
        data = await self._request("search/multi", {"query": query})

        if not data or 'results' not in data:
            return []

        results = []
        for item in data['results']:
            media_type = item.get('media_type')
            if media_type not in ['tv', 'movie']:
                continue

            # Extract basic info
            if media_type == 'tv':
                title = item.get('name')
                date = item.get('first_air_date', '')
            else:
                title = item.get('title')
                date = item.get('release_date', '')

            year = date[:4] if date else "N/A"
            overview = item.get('overview', '')

            results.append({
                "id": item['id'],
                "media_type": media_type,
                "title": title,
                "year": year,
                "overview": overview
            })

            if len(results) >= 5:
                break

        return results

    async def get_details(self, media_type, tmdb_id):
        """
        Get detailed info for a movie or TV show.
        """
        data = await self._request(f"{media_type}/{tmdb_id}")

        if not data:
            return None

        # Genres
        genres = [g['name'] for g in data.get('genres', [])][:3] # Limit to 3 genres

        # Title/Year
        if media_type == 'tv':
            title = data.get('name')
            date = data.get('first_air_date', '')
            runtime = data.get('episode_run_time', [0])[0] if data.get('episode_run_time') else 0
        else:
            title = data.get('title')
            date = data.get('release_date', '')
            runtime = data.get('runtime', 0)

        year = date[:4] if date else "N/A"

        # Poster
        poster_path = data.get('poster_path')
        poster_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else None

        return {
            "title": title,
            "year": year,
            "rating": round(data.get('vote_average', 0), 1),
            "genres": ", ".join(genres),
            "overview": data.get('overview', 'No description available.'),
            "poster_url": poster_url,
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "runtime": runtime
        }

# Global instance
tmdb = TMDBClient()
