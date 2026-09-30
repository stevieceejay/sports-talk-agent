"""Simple public web-search wrapper using DuckDuckGo’s instant-answer API."""

from __future__ import annotations

import json
from typing import Any
from urllib import parse, request


USER_AGENT = "sports-talk-agent/1.0"


def _fetch_json(url: str, timeout: int = 20) -> Any:
    try:
        req = request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read()
        return json.loads(body.decode("utf-8"))
    except Exception as exc:  # pragma: no cover - network guardrail
        return {"status": "error", "error": str(exc)}


def search_web(query: str, max_results: int = 3) -> dict[str, Any]:
    """Search the web using a public no-key endpoint and return a small structured result set."""
    query = (query or "").strip()
    if not query:
        raise ValueError("query must not be empty")

    url = "https://api.duckduckgo.com/?" + parse.urlencode(
        {
            "q": query,
            "format": "json",
            "no_redirect": "1",
            "no_html": "1",
            "skip_disambig": "1",
        }
    )
    payload = _fetch_json(url)
    if isinstance(payload, dict) and payload.get("status") == "error":
        return {"query": query, "source": "DuckDuckGo", "status": "error", "results": [], "error": payload.get("error")}

    results: list[dict[str, Any]] = []
    abstract = payload.get("AbstractText")
    if abstract:
        results.append(
            {
                "title": payload.get("Heading") or "Search result",
                "snippet": abstract,
                "url": payload.get("AbstractURL") or None,
            }
        )

    for topic in payload.get("RelatedTopics", [])[: max(0, int(max_results))]:
        if isinstance(topic, dict):
            text = topic.get("Text")
            url_value = topic.get("FirstURL")
            if text:
                results.append({"title": topic.get("Name") or "Search result", "snippet": text, "url": url_value})
        elif isinstance(topic, str):
            results.append({"title": "Search result", "snippet": topic, "url": None})

    unique = []
    seen = set()
    for item in results:
        key = (item.get("title"), item.get("url"), item.get("snippet"))
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return {
        "query": query,
        "source": "DuckDuckGo",
        "status": "ok" if unique else "empty",
        "results": unique[: max(1, int(max_results))],
    }
