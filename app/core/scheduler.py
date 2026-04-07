"""
scheduler.py — Background follow-up email scheduler using APScheduler.
Checks the follow_up_queue every hour and sends due emails.
"""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import config

logger = logging.getLogger(__name__)

_scheduler = None


def start_scheduler(db, email_system):
    """Start the background APScheduler. Call once at Flask startup."""
    global _scheduler

    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        func=lambda: _process_follow_ups(db, email_system),
        trigger=IntervalTrigger(hours=1),
        id="follow_up_job",
        replace_existing=True,
        next_run_time=datetime.now() + timedelta(minutes=5),  # First run after 5 min
    )
    _scheduler.start()
    logger.info("Follow-up scheduler started (checks every hour)")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def _process_follow_ups(db, email_system):
    """Process all due follow-up emails."""
    logger.info("Scheduler: checking follow-up queue...")
    try:
        due = db.get_pending_follow_ups()
        logger.info(f"Scheduler: {len(due)} follow-ups due")

        for fq in due:
            # Get student profile
            student_profile = db.get_latest_profile() or {}

            # Get professor
            professor = db.get_professor_by_id(fq["professor_id"]) or {}

            # Generate follow-up email
            email_data = email_system.generate_followup_email(
                professor, fq.get("original_body", ""), student_profile
            )

            # Send
            to_email = fq.get("professor_email", "")
            if to_email:
                result = email_system.send_email(
                    to_email=to_email,
                    subject=email_data["subject"],
                    body=email_data["body"],
                )

                if result["success"]:
                    db.mark_follow_up_sent(fq["id"])
                    db.log_email({
                        "professor_id": fq["professor_id"],
                        "professor_name": fq.get("professor_name", ""),
                        "professor_email": to_email,
                        "subject": email_data["subject"],
                        "body": email_data["body"],
                        "email_type": "followup",
                        "status": "sent",
                        "sent_at": datetime.now(),
                    })
                    logger.info(f"Follow-up sent to {fq.get('professor_name', 'Unknown')}")
                else:
                    logger.error(f"Follow-up send failed: {result['message']}")
            else:
                logger.warning(f"No email address for professor_id={fq['professor_id']}, skipping")
                db.mark_follow_up_sent(fq["id"])  # Cancel if no email

    except Exception as e:
        logger.error(f"Scheduler error: {e}")


def schedule_follow_up(db, email_log_id: int, professor_id: int, days: int = None):
    """
    Queue a follow-up email for a professor email.

    Args:
        db: ProfessorDatabase instance
        email_log_id: ID of the original sent email in email_log
        professor_id: Professor's database ID
        days: Days until follow-up (default: config.FOLLOWUP_INTERVAL_DAYS)
    """
    days = days or config.FOLLOWUP_INTERVAL_DAYS
    scheduled_for = datetime.now() + timedelta(days=days)
    fq_id = db.add_follow_up(email_log_id, professor_id, scheduled_for)
    logger.info(
        f"Follow-up scheduled for professor_id={professor_id} "
        f"at {scheduled_for.strftime('%Y-%m-%d %H:%M')}"
    )
    return fq_id
