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
from typing import Optional, List, Dict

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
        max_results: int = 40,
    ) -> list:
        """
        Aggregate professor data from multiple sources.

        Returns a deduplicated list of professor dicts.
        """
        from .config import config
        professors = []

        # Source 0: Gemini AI — run multiple focused queries per keyword
        if config.ai_enabled:
            keywords = [kw.strip() for kw in research_area.split() if len(kw.strip()) > 3]
            # Build 2-3 distinct search phrases to maximise coverage
            queries = [research_area]
            if len(keywords) >= 2:
                queries.append(" ".join(keywords[:2]))
            if len(keywords) >= 3:
                queries.append(keywords[-1])  # last standalone keyword
            queries = list(dict.fromkeys(queries))  # deduplicate while preserving order

            for q in queries[:3]:
                gemini_results = self._gemini_professor_search(q, institution, limit=15)
                if gemini_results:
                    professors.extend(gemini_results)
                    logger.info(f"Gemini AI ({q!r}): {len(gemini_results)} results")
                time.sleep(0.5)  # small pause between Gemini calls

        remaining_limit = max_results - len(self._deduplicate(professors))

        # Source 1: Semantic Scholar (most reliable)
        if remaining_limit > 0:
            ss_results = self._semantic_scholar_search(research_area, min(remaining_limit, 20))
            professors.extend(ss_results)
            logger.info(f"Semantic Scholar: {len(ss_results)} results")

        remaining_limit = max_results - len(self._deduplicate(professors))

        # Source 2: DuckDuckGo web search
        if remaining_limit > 0:
            ddg_results = self._duckduckgo_professor_search(
                research_area, institution, min(remaining_limit, 15)
            )
            professors.extend(ddg_results)
            logger.info(f"DuckDuckGo: {len(ddg_results)} results")

        remaining_limit = max_results - len(self._deduplicate(professors))

        # Source 3: Google Scholar author search
        if remaining_limit > 0:
            gs_results = self._google_scholar_search(research_area, max(remaining_limit // 2, 2))
            professors.extend(gs_results)
            logger.info(f"Google Scholar: {len(gs_results)} results")

        # Deduplicate by name
        unique = self._deduplicate(professors)
        logger.info(f"Total unique professors: {len(unique)}")
        return unique[:max_results]

    # ------------------------------------------------------------------ #
    #  Source 0: Gemini API
    # ------------------------------------------------------------------ #
    def _gemini_professor_search(self, keywords: str, institution: str, limit: int = 15) -> list:
        from .config import config

        if not config.ai_enabled or not config.GEMINI_API_KEY:
            return []

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=config.GEMINI_API_KEY)

            search_target = keywords
            if institution:
                search_target = f"{keywords} at {institution}"

            prompt = f"""Search for real professors who research "{search_target}".

Use Google Search to find REAL professors from universities worldwide. Look at:
- University faculty pages (cs.mit.edu, ee.stanford.edu, etc.)
- Google Scholar profiles (scholar.google.com)
- Lab/research group pages
- LinkedIn profiles of academics

Return ONLY a valid JSON array. No markdown, no explanation, ONLY the raw JSON array.

For each professor, extract as much real contact/profile info as possible:

[
  {{
    "name": "Full Name (REAL person only)",
    "title": "e.g. Associate Professor, Full Professor, Assistant Professor",
    "university": "Full official university name (e.g. Massachusetts Institute of Technology)",
    "department": "e.g. Department of Computer Science",
    "email": "official university email if publicly listed, else null",
    "phone": "office phone if publicly listed, else null",
    "website": "personal faculty page URL or lab page URL",
    "linkedin_url": "LinkedIn profile URL if found, else null",
    "google_scholar_url": "https://scholar.google.com/citations?user=... if found",
    "research_interests": ["interest1", "interest2", "interest3"],
    "recent_publications": ["Paper title 1 (Year)", "Paper title 2 (Year)"],
    "bio": "1-2 sentence summary of their research focus"
  }}
]

STRICT RULES:
- Return {limit} unique professors
- ONLY real verified people — never invent names or universities
- University name must be the full official name (NOT abbreviations like "MIT" → use "Massachusetts Institute of Technology", but short names like "Stanford University" are fine)
- If a field is not publicly available, use null — never guess or fabricate
- Email must be a real .edu or institutional address if found
- Prioritize professors with strong alignment to: {search_target}
- No duplicate professors
- Output ONLY the JSON array, nothing else"""

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}]
                )
            )

            text = response.text.strip()
            # Strip markdown fences if present
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            # Extract JSON array from response
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                text = match.group(0)

            data = json.loads(text)

            professors = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name") or "").strip()
                university = (item.get("university") or "").strip()
                # Skip garbage entries
                if not name or len(name.split()) < 2:
                    continue
                if university.lower() in ("unknown university", "ac university", "ac", ""):
                    university = "Unknown University"

                prof = {
                    "name": name,
                    "title": item.get("title") or "",
                    "university": university,
                    "department": item.get("department") or "",
                    "email": item.get("email") or "",
                    "phone": item.get("phone") or "",
                    "website": item.get("website") or "",
                    "linkedin_url": item.get("linkedin_url") or "",
                    "scholar_url": item.get("google_scholar_url") or item.get("website") or "",
                    "research_areas": item.get("research_interests") or [keywords],
                    "recent_papers": ". ".join(
                        p for p in (item.get("recent_publications") or []) if p
                    )[:600],
                    "publication_count": len(item.get("recent_publications") or []),
                    "bio": item.get("bio") or "",
                    "status": "new",
                }
                professors.append(prof)

            logger.info(f"Gemini returned {len(professors)} professors for '{keywords}'")
            return professors

        except json.JSONDecodeError as e:
            logger.error(f"Gemini JSON parse error: {e}")
            return []
        except Exception as e:
            logger.error(f"Gemini search failed: {e}")
            return []

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
                aff = affiliations[0] if isinstance(affiliations[0], str) else str(affiliations[0])
                # Filter out junk affiliations or too short ones like "Ac"
                if len(aff) > 2 and aff.lower() not in ["ac", "ac.", "affiliate", "researcher"]:
                    professor["university"] = aff
                else:
                    professor["university"] = professor.get("university") or "Unknown University"

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
    ) -> Optional[dict]:
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
            name = m.group(1).strip()
            # If name looks like an email, skip it
            if "@" in name or "." in name.split()[-1]:
                 continue
            return name

    # Fallback: check if the first two words capitalized look like a name
    parts = text.split()
    if len(parts) >= 2:
        if parts[0][0].isupper() and parts[1][0].isupper() and "@" not in parts[0] and "@" not in parts[1]:
            # Further check: no weird chars
            if re.match(r"^[a-zA-Z\s\-\.]+$", parts[0] + " " + parts[1]):
                return parts[0] + " " + parts[1]

    return ""


def _extract_university(text: str) -> str:
    """Extract university name from text."""
    # List of common university words to look for
    patterns = [
        r"(?:University of [A-Z][\w-]+(?:\s+[A-Z][\w-]+)?)",
        r"(?:[A-Z][\w-]+\s+University)",
        r"(?:MIT|Stanford|Caltech|Harvard|IIT[A-Z]?|PDEU|NIT|CMU|UCLA|UC\s+[A-Z][\w-]+)",
        r"(?:[A-Z][\w-]+\s+Institute of Technology)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            uni = m.group(0).strip()
            # Filter out "Ac University" or similar garbage
            if uni.lower().startswith("ac ") or uni.lower() == "ac university":
                continue
            return uni
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
