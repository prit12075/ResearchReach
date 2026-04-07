"""
matcher.py — Semantic research interest matching engine.

Uses TF-IDF vectorization + cosine similarity to score how well a
student's profile aligns with each professor's research.
"""

import re
import logging
from typing import List, Dict, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

# Academic stop-words to exclude from keyword extraction
ACADEMIC_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "this", "that",
    "these", "those", "we", "our", "their", "its", "also", "such", "using",
    "based", "via", "et", "al", "new", "novel", "approach", "method",
    "paper", "work", "study", "results", "show", "propose", "present",
    "university", "department", "professor", "research", "journal",
    "conference", "proceedings", "ieee", "acm", "arxiv", "preprint",
}


class SemanticMatcher:
    """
    TF-IDF + cosine similarity matcher for student ↔ professor research alignment.
    """

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),          # Unigrams + bigrams for phrases
            max_features=5000,
            stop_words="english",
            min_df=1,
            sublinear_tf=True,           # Log-scale TF for better balance
        )
        self._fitted = False

    def compute_match_scores(
        self, student_profile: dict, professors: List[dict]
    ) -> List[dict]:
        """
        Score and rank professors against the student profile.

        Args:
            student_profile: Structured profile from profile_builder.
            professors: List of professor dicts with 'full_text' field.

        Returns:
            professors list enriched with 'match_score' and 'matched_topics'.
        """
        if not professors:
            return []

        student_text = student_profile.get("full_text", "")
        professor_texts = [_build_professor_text(p) for p in professors]

        # Fit vectorizer on all documents combined
        all_docs = [student_text] + professor_texts
        try:
            tfidf_matrix = self.vectorizer.fit_transform(all_docs)
            self._fitted = True
        except Exception as e:
            logger.error(f"TF-IDF fitting failed: {e}")
            return _assign_fallback_scores(professors, student_profile)

        student_vec = tfidf_matrix[0]         # First row = student
        professor_vecs = tfidf_matrix[1:]     # Rest = professors

        # Cosine similarities (0–1)
        scores = cosine_similarity(student_vec, professor_vecs)[0]

        # Enrich each professor with score + matched topics
        for i, prof in enumerate(professors):
            raw_score = float(scores[i])
            prof["match_score"] = round(raw_score * 100, 1)    # 0–100
            prof["matched_topics"] = self._extract_matched_topics(
                student_text, _build_professor_text(prof), top_k=5
            )
            prof["match_grade"] = _score_to_grade(prof["match_score"])

        # Sort by score descending
        professors.sort(key=lambda p: p["match_score"], reverse=True)
        return professors

    def _extract_matched_topics(
        self, student_text: str, prof_text: str, top_k: int = 5
    ) -> List[str]:
        """Return the top shared meaningful n-grams between two texts."""
        if not self._fitted:
            return []

        try:
            vecs = self.vectorizer.transform([student_text, prof_text])
            feature_names = self.vectorizer.get_feature_names_out()

            student_arr = vecs[0].toarray()[0]
            prof_arr = vecs[1].toarray()[0]

            # Product of both TF-IDF weights = importance to BOTH
            combined = student_arr * prof_arr
            top_indices = np.argsort(combined)[::-1][:top_k * 2]

            topics = []
            for idx in top_indices:
                term = feature_names[idx]
                if combined[idx] > 0 and not _is_junk_term(term):
                    topics.append(term.title())
                if len(topics) >= top_k:
                    break

            return topics
        except Exception:
            return []


def extract_keywords(text: str, top_k: int = 10) -> List[str]:
    """
    Extract the most meaningful single-pass keywords from a text blob.
    Used for profile summarization and display.
    """
    text = text.lower()
    # Remove punctuation except hyphens
    text = re.sub(r"[^\w\s\-]", " ", text)
    words = text.split()

    # Filter stop words and short tokens
    words = [w for w in words if w not in ACADEMIC_STOPWORDS and len(w) > 3]

    # Frequency count
    freq: Dict[str, int] = {}
    for word in words:
        freq[word] = freq.get(word, 0) + 1

    # Sort by frequency
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w for w, _ in sorted_words[:top_k]]


def _build_professor_text(prof: dict) -> str:
    """Concatenate all professor text fields for vectorization."""
    parts = [
        prof.get("name", ""),
        " ".join(prof.get("research_areas", [])),
        prof.get("department", ""),
        prof.get("bio", ""),
        prof.get("recent_papers", ""),
        prof.get("university", ""),
    ]
    return " ".join(filter(None, parts))


def _score_to_grade(score: float) -> str:
    """Convert 0–100 score to a human-readable grade."""
    if score >= 70:
        return "Excellent Match"
    elif score >= 45:
        return "Good Match"
    elif score >= 25:
        return "Moderate Match"
    else:
        return "Low Match"


def _is_junk_term(term: str) -> bool:
    """Filter out irrelevant short terms."""
    return len(term) < 4 or term.lower() in ACADEMIC_STOPWORDS


def _assign_fallback_scores(professors: List[dict], student_profile: dict) -> List[dict]:
    """Keyword overlap fallback if TF-IDF fails."""
    student_interests = set(
        w.lower() for w in student_profile.get("research_interests", [])
    )
    for prof in professors:
        prof_areas = set(
            w.lower() for area in prof.get("research_areas", []) for w in area.split()
        )
        overlap = len(student_interests & prof_areas)
        prof["match_score"] = min(round(overlap * 15, 1), 95.0)
        prof["matched_topics"] = list(student_interests & prof_areas)[:5]
        prof["match_grade"] = _score_to_grade(prof["match_score"])
    professors.sort(key=lambda p: p["match_score"], reverse=True)
    return professors


# Singleton
matcher = SemanticMatcher()
