"""
MoltbookClient — API client for Moltbook publishing and engagement tracking.

Handles creating posts, fetching stats, and managing published content
on the Moltbook platform.
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class MoltbookClient:
    """Client for the Moltbook API."""

    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key or os.environ.get("MOLTBOOK_API_KEY", "")
        self.base_url = (base_url or os.environ.get("MOLTBOOK_BASE_URL", "")).rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    def is_configured(self) -> bool:
        """Check if the client has API key and base URL configured."""
        return bool(self.api_key and self.base_url)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def create_post(self, body: str, tags: list[str] = None, title: str = "") -> dict:
        """Publish a post to Moltbook.

        Args:
            body: Post content (max 2000 chars).
            tags: Optional list of tags.
            title: Optional post title.

        Returns:
            Dict with post_id, url, and status.
        """
        if not self.is_configured():
            return {"error": "Moltbook not configured. Set MOLTBOOK_API_KEY and MOLTBOOK_BASE_URL."}

        client = self._get_client()
        payload = {"body": body[:2000]}
        if tags:
            payload["tags"] = tags
        if title:
            payload["title"] = title

        try:
            resp = await client.post(f"{self.base_url}/api/posts", json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info("[Moltbook] Post created: %s", data.get("id", "unknown"))
            return {
                "post_id": data.get("id", ""),
                "url": data.get("url", ""),
                "status": "published",
            }
        except httpx.HTTPStatusError as e:
            logger.error("[Moltbook] API error %d: %s", e.response.status_code, e.response.text[:200])
            return {"error": f"Moltbook API error: {e.response.status_code}"}
        except httpx.ConnectError:
            logger.error("[Moltbook] Cannot connect to %s", self.base_url)
            return {"error": f"Cannot connect to Moltbook at {self.base_url}"}
        except Exception as e:
            logger.error("[Moltbook] Error: %s", e)
            return {"error": str(e)}

    async def get_post_stats(self, post_id: str) -> dict:
        """Get engagement stats for a published post.

        Args:
            post_id: The Moltbook post ID.

        Returns:
            Dict with views, likes, replies, shares.
        """
        if not self.is_configured():
            return {}

        client = self._get_client()
        try:
            resp = await client.get(f"{self.base_url}/api/posts/{post_id}/stats")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("[Moltbook] Stats error for %s: %s", post_id, e)
            return {}

    async def get_recent_posts(self, limit: int = 10) -> list[dict]:
        """Fetch recent posts for performance tracking.

        Args:
            limit: Maximum number of posts to return.

        Returns:
            List of post dicts with id, title, body, stats.
        """
        if not self.is_configured():
            return []

        client = self._get_client()
        try:
            resp = await client.get(
                f"{self.base_url}/api/posts",
                params={"limit": limit, "sort": "recent"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("posts", data) if isinstance(data, dict) else data
        except Exception as e:
            logger.warning("[Moltbook] Recent posts error: %s", e)
            return []

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Module-level singleton
_client: Optional[MoltbookClient] = None


def get_moltbook_client() -> MoltbookClient:
    """Get or create the Moltbook client singleton."""
    global _client
    if _client is None:
        _client = MoltbookClient()
    return _client
