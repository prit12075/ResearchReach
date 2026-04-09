"""
professor_finder.py — Core orchestrator tying all modules together.
"""

import re
import logging
from .database import db
from .web_scraper import WebScraper
from .email_system import email_system
from .matcher import matcher
from .profile_builder import build_profile

logger = logging.getLogger(__name__)


class ProfessorFinderSystem:
    def __init__(self):
        self.db = db
        self.scraper = WebScraper()
        self.email_system = email_system
        self.matcher = matcher

    def run_search(self, student_profile: dict, max_results: int = 40) -> list:
        """
        Full pipeline: scrape → match → save → return ranked professors.

        Args:
            student_profile: Structured dict from profile_builder.build_profile()
            max_results: Maximum professors to return.

        Returns:
            List of professor dicts enriched with match_score and matched_topics.
        """
        interests = student_profile.get("research_interests", [])
        institution = student_profile.get("target_institution", "")

        # Build search queries: one combined + one per top individual interest
        combined_area = " ".join(interests[:4])
        search_queries = [combined_area] if combined_area else []
        for interest in interests[:3]:
            if interest and interest not in search_queries:
                search_queries.append(interest)
        if not search_queries:
            search_queries = ["computer science research"]

        logger.info(f"Starting search: queries={search_queries}, institution='{institution}'")

        # Step 1: Save profile
        self.db.save_profile(student_profile)

        # Step 2: Scrape professors across all queries
        all_professors = []
        seen_names = set()
        per_query_limit = max(max_results // len(search_queries), 15)

        for query in search_queries:
            results = self.scraper.find_professors(
                research_area=query,
                institution=institution,
                max_results=per_query_limit,
            )
            for p in results:
                key = re.sub(r"[^a-z]", "", p.get("name", "").lower())
                if key and key not in seen_names:
                    seen_names.add(key)
                    all_professors.append(p)

        professors = all_professors
        logger.info(f"Scraped {len(professors)} professors")

        if not professors:
            logger.warning("No professors found from scraping")
            return []

        # Step 3: Semantic matching
        professors = self.matcher.compute_match_scores(student_profile, professors)
        logger.info("Matching scores computed")

        # Step 4: Save to database
        db.clear_professors()   # Fresh results per search
        for prof in professors:
            pid = db.upsert_professor(prof)
            prof["id"] = pid

        self.db.log_scraping("combined", combined_area, len(professors))

        logger.info(f"Search complete: {len(professors)} matched professors saved")
        return professors

    def generate_email_for_professor(self, professor_id: int, student_profile: dict) -> dict:
        """Generate a personalized email for a specific professor."""
        professor = self.db.get_professor_by_id(professor_id)
        if not professor:
            return {"error": "Professor not found"}

        email_data = self.email_system.generate_email(professor, student_profile)
        return email_data

    def send_email_to_professor(
        self, professor_id: int, subject: str, body: str, schedule_followup: bool = True
    ) -> dict:
        """Send email to professor and optionally schedule a follow-up."""
        from .config import config
        from .scheduler import schedule_follow_up

        professor = self.db.get_professor_by_id(professor_id)
        if not professor:
            return {"success": False, "message": "Professor not found"}

        # Rate limit check
        sent_today = self.db.count_sent_today()
        if sent_today >= config.MAX_EMAILS_PER_DAY:
            return {
                "success": False,
                "message": f"Daily email limit reached ({config.MAX_EMAILS_PER_DAY}/day). Try again tomorrow.",
            }

        to_email = professor.get("email", "")
        if not to_email:
            return {"success": False, "message": "Professor email address not available"}

        result = self.email_system.send_email(to_email, subject, body)

        if result["success"]:
            # Log sent email
            email_id = self.db.log_email({
                "professor_id": professor_id,
                "professor_name": professor.get("name", ""),
                "professor_email": to_email,
                "subject": subject,
                "body": body,
                "email_type": "initial",
                "status": "sent",
                "sent_at": __import__("datetime").datetime.now(),
            })

            # Update professor status
            self.db.conn.execute(
                "UPDATE professors SET status='contacted', last_contact=DATE('now') WHERE id=?",
                (professor_id,)
            )
            self.db.conn.commit()

            # Schedule follow-up
            if schedule_followup:
                schedule_follow_up(self.db, email_id, professor_id)
                result["followup_scheduled"] = True

        return result

    def get_dashboard_data(self) -> dict:
        """Return all data needed for the tracking dashboard."""
        return {
            "stats": self.db.get_stats(),
            "professors": self.db.get_all_professors(limit=50),
            "email_log": self.db.get_email_log(limit=100),
        }


# Singleton
system = ProfessorFinderSystem()
