"""Web Search Provider abstraction — supports DuckDuckGo (free) and Tavily.

Switch via env SEARCH_PROVIDER=duckduckgo|tavily. Default: duckduckgo.
"""

from __future__ import annotations

import logging
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger("chatbot")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    score: float = 0.0
    source_type: str = "external"


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        ...


DUCKDUCKGO_IPS = ["104.18.32.47", "104.18.33.47", "104.16.0.0"]
_original_getaddrinfo = socket.getaddrinfo


def _patch_ddg_dns():
    """Override DNS for duckduckgo.com to bypass ISP DNS spoofing."""
    def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if host in ("duckduckgo.com", "www.duckduckgo.com", "html.duckduckgo.com", "lite.duckduckgo.com"):
            for ip in DUCKDUCKGO_IPS:
                try:
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
                except Exception:
                    continue
        return _original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = patched_getaddrinfo


def _unpatch_ddg_dns():
    socket.getaddrinfo = _original_getaddrinfo


class DuckDuckGoProvider(SearchProvider):
    """Free web search via duckduckgo-search library. No API key required."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                logger.error("ddgs package not installed")
                return []

        results: list[SearchResult] = []
        try:
            _patch_ddg_dns()
            with DDGS(timeout=self.timeout) as ddgs:
                hits = list(ddgs.text(query, max_results=max_results))
            _unpatch_ddg_dns()

            for i, hit in enumerate(hits):
                results.append(
                    SearchResult(
                        title=hit.get("title", ""),
                        url=hit.get("href", ""),
                        snippet=hit.get("body", ""),
                        score=1.0 - (i * 0.1),
                        source_type="external",
                    )
                )
            logger.info("DuckDuckGo: %d results for '%s'", len(results), query[:60])
        except Exception as e:
            _unpatch_ddg_dns()
            logger.warning("DuckDuckGo search failed: %s", str(e)[:120])

        return results


class TavilyProvider(SearchProvider):
    """Web search via Tavily API. Designed for AI/LLM use cases."""

    def __init__(self, api_key: str, timeout: int = 10):
        self.api_key = api_key
        self.timeout = timeout

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not self.api_key:
            logger.error("TAVILY_API_KEY not configured")
            return []

        try:
            from tavily import TavilyClient
        except ImportError:
            logger.error("tavily-python package not installed")
            return []

        results: list[SearchResult] = []
        try:
            client = TavilyClient(api_key=self.api_key)
            response = client.search(query, max_results=max_results)

            for i, hit in enumerate(response.get("results", [])):
                results.append(
                    SearchResult(
                        title=hit.get("title", ""),
                        url=hit.get("url", ""),
                        snippet=hit.get("content", ""),
                        score=hit.get("score", 1.0 - (i * 0.1)),
                        source_type="external",
                    )
                )
            logger.info("Tavily: %d results for '%s'", len(results), query[:60])
        except Exception as e:
            logger.warning("Tavily search failed: %s", str(e)[:120])

        return results


_provider: SearchProvider | None = None


def get_search_provider() -> SearchProvider:
    """Return singleton search provider based on SEARCH_PROVIDER env var."""
    global _provider
    if _provider is not None:
        return _provider

    from app.config import SEARCH_PROVIDER, SEARCH_TIMEOUT, TAVILY_API_KEY

    name = SEARCH_PROVIDER.lower()
    if name == "tavily":
        if not TAVILY_API_KEY:
            logger.warning("SEARCH_PROVIDER=tavily but TAVILY_API_KEY empty — falling back to DuckDuckGo")
            _provider = DuckDuckGoProvider(timeout=SEARCH_TIMEOUT)
        else:
            _provider = TavilyProvider(api_key=TAVILY_API_KEY, timeout=SEARCH_TIMEOUT)
            logger.info("Search provider: Tavily")
    else:
        _provider = DuckDuckGoProvider(timeout=SEARCH_TIMEOUT)
        logger.info("Search provider: DuckDuckGo (free, no API key)")

    return _provider


def search_web(query: str, max_results: int = 5) -> list[SearchResult]:
    """Convenience function: search web using configured provider."""
    from app.config import ENABLE_WEB_SEARCH, SEARCH_MAX_RESULTS

    if not ENABLE_WEB_SEARCH:
        return []

    provider = get_search_provider()
    return provider.search(query, max_results=max_results or SEARCH_MAX_RESULTS)
