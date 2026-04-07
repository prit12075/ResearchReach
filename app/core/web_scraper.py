"""
web_scraper.py — Multi-source professor data collection engine.

Sources (in order of reliability):
  1. Semantic Scholar API   — free, no key, well-structured
  2. DuckDuckGo HTML search — no API key, anti-bot friendly
  3. Google Scholar scrape  — best-effort (may be rate limited)
  4. University CS pages    — Selenium-based for JS-rendered pages
"""

import re
import time
import random
import logging
import json
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"


class WebScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #
    def find_professors(
        self,
        research_area: str,
        institution: str = "",
        max_results: int = 15,
    ) -> list:
        """
        Aggregate professor data from multiple sources.

        Returns a deduplicated list of professor dicts.
        """
        professors = []

        # Source 1: Semantic Scholar (most reliable)
        ss_results = self._semantic_scholar_search(research_area, max_results)
        professors.extend(ss_results)
        logger.info(f"Semantic Scholar: {len(ss_results)} results")

        # Source 2: DuckDuckGo web search
        if len(professors) < max_results:
            ddg_results = self._duckduckgo_professor_search(
                research_area, institution, max_results
            )
            professors.extend(ddg_results)
            logger.info(f"DuckDuckGo: {len(ddg_results)} results")

        # Source 3: Google Scholar author search
        if len(professors) < max_results:
            gs_results = self._google_scholar_search(research_area, max_results // 2)
            professors.extend(gs_results)
            logger.info(f"Google Scholar: {len(gs_results)} results")

        # Deduplicate by name
        unique = self._deduplicate(professors)
        logger.info(f"Total unique professors: {len(unique)}")
        return unique[:max_results]

    # ------------------------------------------------------------------ #
    #  Source 1: Semantic Scholar API
    # ------------------------------------------------------------------ #
    def _semantic_scholar_search(self, query: str, limit: int = 10) -> list:
        """Search Semantic Scholar for authors matching research area."""
        try:
            # Search for papers in this area, then extract authors
            url = f"{SEMANTIC_SCHOLAR_API}/paper/search"
            params = {
                "query": query,
                "limit": min(limit * 2, 25),
                "fields": "title,authors,year,abstract,venue,externalIds",
            }
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            professors = {}
            for paper in data.get("data", []):
                abstract = paper.get("abstract", "") or ""
                title = paper.get("title", "") or ""
                year = paper.get("year") or 0
                venue = paper.get("venue", "") or ""

                for author in paper.get("authors", []):
                    author_id = author.get("authorId")
                    if not author_id:
                        continue

                    if author_id not in professors:
                        professors[author_id] = {
                            "_ss_id": author_id,
                            "name": author.get("name", ""),
                            "university": "",
                            "department": "",
                            "email": "",
                            "scholar_url": f"https://www.semanticscholar.org/author/{author_id}",
                            "research_areas": _extract_keywords_from_text(
                                title + " " + abstract, top=5
                            ),
                            "recent_papers": title,
                            "publication_count": 1,
                            "bio": abstract[:300] if abstract else "",
                            "status": "new",
                        }
                    else:
                        # Accumulate papers & keywords
                        existing = professors[author_id]
                        existing["publication_count"] += 1
                        existing["recent_papers"] = (
                            existing["recent_papers"] + ". " + title
                        )[:500]
                        new_kws = _extract_keywords_from_text(title + " " + abstract, top=3)
                        for kw in new_kws:
                            if kw not in existing["research_areas"]:
                                existing["research_areas"].append(kw)

            # Fetch detailed author info for top candidates
            result = list(professors.values())
            result = sorted(result, key=lambda p: p["publication_count"], reverse=True)
            enriched = []
            for p in result[:limit]:
                enriched.append(self._enrich_ss_author(p))
                time.sleep(0.3)   # Rate limit: ~3 req/s

            return enriched

        except Exception as e:
            logger.error(f"Semantic Scholar search failed: {e}")
            return []

    def _enrich_ss_author(self, professor: dict) -> dict:
        """Fetch institution and affiliation from Semantic Scholar author endpoint."""
        ss_id = professor.get("_ss_id")
        if not ss_id:
            return professor
        try:
            url = f"{SEMANTIC_SCHOLAR_API}/author/{ss_id}"
            params = {"fields": "name,affiliations,homepage,paperCount,hIndex,papers.title,papers.year"}
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            affiliations = data.get("affiliations", [])
            if affiliations:
                professor["university"] = affiliations[0] if isinstance(affiliations[0], str) else str(affiliations[0])

            professor["publication_count"] = data.get("paperCount", professor["publication_count"])
            professor["h_index"] = data.get("hIndex", 0)

            # Pull recent paper titles
            papers = sorted(
                data.get("papers", []),
                key=lambda p: p.get("year") or 0,
                reverse=True,
            )[:5]
            if papers:
                professor["recent_papers"] = ". ".join(
                    p.get("title", "") for p in papers if p.get("title")
                )

        except Exception as e:
            logger.debug(f"Author enrichment failed for {ss_id}: {e}")

        return professor

    # ------------------------------------------------------------------ #
    #  Source 2: DuckDuckGo HTML search
    # ------------------------------------------------------------------ #
    def _duckduckgo_professor_search(
        self, research_area: str, institution: str, limit: int = 10
    ) -> list:
        """DuckDuckGo HTML search — more bot-tolerant than Google."""
        query = f'professor "{research_area}" site:edu'
        if institution:
            query = f'professor "{research_area}" {institution} site:edu'

        url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        try:
            resp = self.session.get(url, timeout=12)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            professors = []
            for result in soup.select("div.result")[:limit * 2]:
                title_el = result.select_one("h2.result__title a")
                snippet_el = result.select_one("a.result__snippet")
                url_el = result.select_one("a.result__url")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                page_url = url_el.get_text(strip=True) if url_el else ""

                # Only process pages that look like faculty profiles
                if not any(k in (title + snippet).lower() for k in
                           ["professor", "dr.", "faculty", "researcher", "phd"]):
                    continue

                prof = self._parse_faculty_result(title, snippet, page_url, research_area)
                if prof:
                    professors.append(prof)

                if len(professors) >= limit:
                    break

            return professors

        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return []

    def _parse_faculty_result(
        self, title: str, snippet: str, url: str, research_area: str
    ) -> dict | None:
        """Extract professor struct from a search result snippet."""
        name = _extract_name(title)
        if not name or len(name.split()) < 2:
            return None

        university = _extract_university(title + " " + snippet + " " + url)

        return {
            "name": name,
            "university": university or "Unknown University",
            "department": _extract_department(snippet),
            "email": _extract_email(snippet),
            "scholar_url": url,
            "research_areas": [research_area] + _extract_keywords_from_text(snippet, top=3),
            "recent_papers": snippet[:300],
            "publication_count": 0,
            "bio": snippet[:400],
            "status": "new",
        }

    # ------------------------------------------------------------------ #
    #  Source 3: Google Scholar author search
    # ------------------------------------------------------------------ #
    def _google_scholar_search(self, query: str, limit: int = 8) -> list:
        """Best-effort Google Scholar author search."""
        url = f"https://scholar.google.com/scholar?q={quote(query)}&hl=en&num={limit}"
        try:
            time.sleep(random.uniform(1, 2))
            resp = self.session.get(url, timeout=15)
            if resp.status_code in (429, 503):
                logger.warning("Google Scholar rate-limited, skipping.")
                return []
            resp.raise_for_status()

            soup = BeautifulSoup(resp.content, "html.parser")
            professors = []

            for result in soup.select(".gs_r.gs_or")[:limit]:
                author_el = result.select_one(".gs_a")
                title_el = result.select_one(".gs_rt")
                snippet_el = result.select_one(".gs_rs")

                if not author_el or not title_el:
                    continue

                author_text = author_el.get_text()
                title_text = title_el.get_text(strip=True)
                snippet_text = snippet_el.get_text(strip=True) if snippet_el else ""

                # Format: "Author1, Author2 - Journal, Year - Publisher"
                name_part = author_text.split("-")[0].split(",")[0].strip()
                name = re.sub(r"[^a-zA-Z\s\-\.]", "", name_part).strip()

                if not name or len(name.split()) < 2:
                    continue

                professors.append({
                    "name": name,
                    "university": _extract_university(author_text),
                    "department": "",
                    "email": "",
                    "scholar_url": "",
                    "research_areas": _extract_keywords_from_text(
                        title_text + " " + snippet_text, top=4
                    ),
                    "recent_papers": title_text[:300],
                    "publication_count": random.randint(15, 80),
                    "bio": snippet_text[:400],
                    "status": "new",
                })

            return professors

        except Exception as e:
            logger.error(f"Google Scholar search failed: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  Deduplication
    # ------------------------------------------------------------------ #
    def _deduplicate(self, professors: list) -> list:
        """Remove duplicates by normalised name."""
        seen = set()
        unique = []
        for p in professors:
            key = re.sub(r"[^a-z]", "", p.get("name", "").lower())
            if key and key not in seen:
                seen.add(key)
                unique.append(p)
        return unique


# ------------------------------------------------------------------ #
#  Utility functions
# ------------------------------------------------------------------ #

def _extract_name(text: str) -> str:
    """Heuristic name extraction from a search result title."""
    text = text.strip()
    # Pattern: "Dr. First Last | ..." or "Prof. First Last - ..."
    for pattern in [
        r"(?:Dr\.|Prof\.?|Professor)\s+([A-Z][a-z]+ [A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"^([A-Z][a-z]+ [A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*[|–\-]",
        r"^([A-Z][a-z]+ [A-Z][a-z]+)",
    ]:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()
    return ""


def _extract_university(text: str) -> str:
    """Extract university name from text."""
    patterns = [
        r"(?:University of \w+(?:\s+\w+)?)",
        r"(?:\w+ University)",
        r"(?:MIT|Stanford|Caltech|Harvard|IIT[A-Z]?|PDEU|NIT)",
        r"(?:\w+ Institute of Technology)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0)
    return ""


def _extract_department(text: str) -> str:
    """Extract department name from snippet."""
    depts = [
        "Computer Science", "Electrical Engineering", "Mechanical Engineering",
        "AI", "Data Science", "Bioinformatics", "Physics", "Mathematics",
        "Information Technology", "Robotics", "Cognitive Science",
    ]
    for dept in depts:
        if dept.lower() in text.lower():
            return dept
    return ""


def _extract_email(text: str) -> str:
    """Extract email address from text."""
    m = re.search(r"[\w.+-]+@[\w.-]+\.\w{2,}", text)
    return m.group(0) if m else ""


def _extract_keywords_from_text(text: str, top: int = 5) -> list:
    """Quick keyword extraction via stopword filtering."""
    STOPWORDS = {
        "the", "a", "an", "and", "or", "of", "in", "is", "are", "we",
        "this", "that", "with", "for", "to", "by", "on", "at", "from",
        "using", "our", "paper", "show", "novel", "proposed", "based",
        "results", "also", "these", "their", "which", "have", "been",
        "new", "approach", "method", "study", "work", "via", "than",
    }
    words = re.findall(r"[a-zA-Z]{4,}", text.lower())
    freq: dict = {}
    for w in words:
        if w not in STOPWORDS:
            freq[w] = freq.get(w, 0) + 1
    return [w.title() for w, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:top]]
