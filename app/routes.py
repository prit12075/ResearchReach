"""
routes.py — Flask routes for the AI Professor Matcher system.
"""

import logging
import threading
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, session, redirect, current_app

from .core.config import config
from .core.database import db
from .core.professor_finder import system
from .core.profile_builder import build_profile, get_demo_profile
from .core.scheduler import start_scheduler, schedule_follow_up
from .core.email_system import email_system
from .core.gmail_sync import GmailSync
from .core.resume_parser import parse_resume

logger = logging.getLogger(__name__)

# Define Blueprint
main_bp = Blueprint('main', __name__)

# ------------------------------------------------------------------ #
# Custom Filters
# ------------------------------------------------------------------ #
@main_bp.app_template_filter("format_dt")
def format_dt_filter(value):
    if not value: return ""
    try:
        if isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            dt = value
        return dt.strftime("%b %d, %H:%M")
    except:
        return str(value)

# Background state for async search
_search_state = {
    "status": "idle",         # idle | running | done | error
    "progress": 0,
    "message": "",
    "results": [],
    "error": "",
}
_search_lock = threading.Lock()

# Background state for Gmail sync
_sync_state = {
    "status": "idle",         # idle | running | done | error
    "progress": 0,
    "message": "",
    "imported": 0,
    "skipped": 0,
    "total_scanned": 0,
    "error": "",
}
_sync_lock = threading.Lock()


# ------------------------------------------------------------------ #
#  Page Routes
# ------------------------------------------------------------------ #
@main_bp.route("/")
def index():
    """Main dashboard overview."""
    data = system.get_dashboard_data()
    profile = db.get_latest_profile() or {}
    return render_template("index.html", **data, profile=profile, config=config)


@main_bp.route("/profile")
def profile():
    """Resume and profile management."""
    profile = db.get_latest_profile() or {}
    demo = get_demo_profile()
    return render_template("resume.html", profile=profile, demo=demo, config=config)


@main_bp.route("/outreach")
def outreach():
    """Outreach and email tracking."""
    data = system.get_dashboard_data()
    return render_template("outreach.html", **data, config=config)


@main_bp.route("/upgrade")
def upgrade():
    """Pricing / Upgrade page."""
    profile = db.get_latest_profile() or {}
    return render_template("upgrade.html", profile=profile, config=config)


@main_bp.route("/contact")
def contact():
    """Contact / Support page."""
    profile = db.get_latest_profile() or {}
    return render_template("contact.html", profile=profile, config=config)


@main_bp.route("/follow-ups")
def follow_ups():
    """Scheduled follow-ups timeline."""
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT fq.*, el.professor_email, el.professor_name, el.subject
        FROM follow_up_queue fq
        JOIN email_log el ON fq.email_log_id = el.id
        ORDER BY fq.scheduled_for ASC
    """)
    rows = [dict(r) for r in cursor.fetchall()]

    now = datetime.now()
    for row in rows:
        scheduled_raw = row.get("scheduled_for")
        row["derived_status"] = row.get("status", "pending")
        if row["derived_status"] == "pending" and scheduled_raw:
            try:
                scheduled_dt = datetime.fromisoformat(str(scheduled_raw))
                if scheduled_dt < now:
                    row["derived_status"] = "overdue"
            except Exception:
                pass

    return render_template(
        "followups.html",
        followups=rows,
        follow_ups=rows,
        config=config
    )


@main_bp.route("/follow-ups/")
def follow_ups_trailing():
    return redirect("/follow-ups")


@main_bp.route("/followups")
def followups_alias():
    return redirect("/follow-ups")


@main_bp.route("/results")
def results():
    """Professor results + email studio."""
    professors = db.get_all_professors(limit=50)
    profile = db.get_latest_profile() or {}
    return render_template("results.html", professors=professors, profile=profile, config=config)


@main_bp.route("/settings")
def settings():
    """App settings (simulated for now)."""
    return render_template("settings.html", config=config)


@main_bp.route("/dashboard")
def dashboard_redirect():
    """Redirect old dashboard to home."""
    return redirect("/")


# ------------------------------------------------------------------ #
#  API: Search
# ------------------------------------------------------------------ #
@main_bp.route("/api/search", methods=["POST"])
def api_search():
    """Trigger async professor search."""
    global _search_state

    with _search_lock:
        if _search_state["status"] == "running":
            return jsonify({"error": "Search already in progress"}), 409

        form_data = request.json or request.form.to_dict()
        profile = build_profile(form_data)

        _search_state = {
            "status": "running",
            "progress": 5,
            "message": "Building your profile...",
            "results": [],
            "error": "",
        }

    def _run_search():
        global _search_state
        try:
            _update_progress(20, "Searching Semantic Scholar...")
            results = system.run_search(profile)
            _update_progress(100, f"Found {len(results)} professors!")
            with _search_lock:
                _search_state["status"] = "done"
                _search_state["results"] = results
        except Exception as e:
            logger.error(f"Search error: {e}")
            with _search_lock:
                _search_state["status"] = "error"
                _search_state["error"] = str(e)
                _search_state["message"] = "Search failed. See logs for details."

    thread = threading.Thread(target=_run_search, daemon=True)
    thread.start()

    return jsonify({"status": "started", "message": "Search initiated"})


@main_bp.route("/api/search/status", methods=["GET"])
def api_search_status():
    """Poll search progress."""
    with _search_lock:
        return jsonify(dict(_search_state))


def _update_progress(pct: int, msg: str):
    with _search_lock:
        _search_state["progress"] = pct
        _search_state["message"] = msg


# ------------------------------------------------------------------ #
#  API: Professors
# ------------------------------------------------------------------ #
@main_bp.route("/api/professors", methods=["GET"])
def api_professors():
    professors = db.get_all_professors(limit=50)
    return jsonify(professors)


@main_bp.route("/api/professor/<int:pid>", methods=["GET"])
def api_professor(pid):
    prof = db.get_professor_by_id(pid)
    if not prof:
        return jsonify({"error": "Not found"}), 404
    return jsonify(prof)


# ------------------------------------------------------------------ #
#  API: Email Generation
# ------------------------------------------------------------------ #
@main_bp.route("/api/generate-email", methods=["POST"])
def api_generate_email():
    """Generate personalized email for a professor."""
    data = request.json or {}
    professor_id = data.get("professor_id")
    profile_data = data.get("profile") or {}

    if not professor_id:
        return jsonify({"error": "professor_id required"}), 400

    # Use saved profile if no profile provided
    if not profile_data:
        profile_data = db.get_latest_profile() or {}

    try:
        professor = db.get_professor_by_id(professor_id)
        if not professor:
            return jsonify({"error": "Professor not found"}), 404

        result = email_system.generate_email(professor, profile_data)

        # Log as generated (not yet sent)
        email_id = db.log_email({
            "professor_id": professor_id,
            "professor_name": professor.get("name", ""),
            "professor_email": professor.get("email", ""),
            "subject": result["subject"],
            "body": result["body"],
            "email_type": "initial",
            "status": "generated",
        })
        result["email_id"] = email_id
        return jsonify(result)

    except Exception as e:
        logger.error(f"Email generation error: {e}")
        return jsonify({"error": str(e)}), 500


# ------------------------------------------------------------------ #
#  API: Email Sending
# ------------------------------------------------------------------ #
@main_bp.route("/api/send-email", methods=["POST"])
def api_send_email():
    """Send approved email to professor."""
    data = request.json or {}
    professor_id = data.get("professor_id")
    subject = data.get("subject", "")
    body = data.get("body", "")
    schedule_followup = data.get("schedule_followup", True)

    if not professor_id or not subject or not body:
        return jsonify({"error": "professor_id, subject, and body are required"}), 400

    result = system.send_email_to_professor(
        professor_id=professor_id,
        subject=subject,
        body=body,
        schedule_followup=schedule_followup,
    )
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@main_bp.route("/api/preview-send", methods=["POST"])
def api_preview_send():
    """
    Simulate sending (no actual SMTP) — used when email not configured.
    Records as 'sent' in DB for tracking purposes.
    """
    data = request.json or {}
    professor_id = data.get("professor_id")
    subject = data.get("subject", "")
    body = data.get("body", "")

    professor = db.get_professor_by_id(professor_id)
    if not professor:
        return jsonify({"error": "Professor not found"}), 404

    email_id = db.log_email({
        "professor_id": professor_id,
        "professor_name": professor.get("name", ""),
        "professor_email": professor.get("email", "preview@demo.com"),
        "subject": subject,
        "body": body,
        "email_type": "initial",
        "status": "preview",
        "sent_at": datetime.now(),
    })
    db.conn.execute(
        "UPDATE professors SET status='contacted' WHERE id=?", (professor_id,)
    )
    db.conn.commit()

    return jsonify({"success": True, "email_id": email_id, "mode": "preview"})


# ------------------------------------------------------------------ #
#  API: Dashboard Data
# ------------------------------------------------------------------ #
@main_bp.route("/api/stats", methods=["GET"])
def api_stats():
    return jsonify(db.get_stats())


@main_bp.route("/api/email-log", methods=["GET"])
def api_email_log():
    logs = db.get_email_log(limit=200)
    return jsonify(logs)


@main_bp.route("/api/mark-replied", methods=["POST"])
def api_mark_replied():
    data = request.json or {}
    email_id = data.get("email_id")
    if not email_id:
        return jsonify({"error": "email_id required"}), 400
    db.update_email_status(email_id, "replied")
    return jsonify({"success": True})


@main_bp.route("/api/config-status", methods=["GET"])
def api_config_status():
    """Return which features are enabled."""
    return jsonify({
        "ai_enabled": config.ai_enabled,
        "email_sending_enabled": config.email_sending_enabled,
        "max_emails_per_day": config.MAX_EMAILS_PER_DAY,
        "followup_interval_days": config.FOLLOWUP_INTERVAL_DAYS,
    })


# ------------------------------------------------------------------ #
#  API: Resume Upload
# ------------------------------------------------------------------ #
@main_bp.route("/api/upload-resume", methods=["POST"])
def api_upload_resume():
    """Accept a PDF resume file, parse it, and return structured profile data."""
    if "resume" not in request.files:
        return jsonify({"error": "No file uploaded. Send as 'resume' field."}), 400

    file = request.files["resume"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported."}), 400

    try:
        pdf_bytes = file.read()
        if len(pdf_bytes) > 10 * 1024 * 1024:  # 10 MB limit
            return jsonify({"error": "File too large. Max 10 MB."}), 400

        result = parse_resume(pdf_bytes)

        if result.get("error"):
            return jsonify(result), 400

        return jsonify(result)

    except Exception as e:
        logger.error(f"Resume parsing error: {e}")
        return jsonify({"error": f"Failed to parse resume: {str(e)}"}), 500


# ------------------------------------------------------------------ #
#  API: Follow-up Email
# ------------------------------------------------------------------ #
@main_bp.route("/api/send-followup", methods=["POST"])
def api_send_followup():
    """Generate and send a follow-up email to a professor."""
    data = request.json or {}
    professor_id = data.get("professor_id")

    if not professor_id:
        return jsonify({"error": "professor_id required"}), 400

    professor = db.get_professor_by_id(professor_id)
    if not professor:
        return jsonify({"error": "Professor not found"}), 404

    to_email = professor.get("email", "")
    if not to_email or "@" not in to_email:
        return jsonify({"error": "Professor has no email address. Add one first."}), 400

    student_profile = db.get_latest_profile() or {}

    # Get the original email body if exists
    original = db.conn.execute(
        "SELECT body FROM email_log WHERE professor_id=? ORDER BY created_at DESC LIMIT 1",
        (professor_id,)
    ).fetchone()
    original_body = original["body"] if original else ""

    # Generate follow-up
    email_data = email_system.generate_followup_email(professor, original_body, student_profile)

    # Allow AI override if enabled
    if config.ai_enabled and data.get("use_ai", True):
        try:
            email_data = _generate_ai_followup(professor, original_body, student_profile)
        except Exception as e:
            logger.warning(f"AI follow-up generation failed: {e}")

    # If send_now is True, send immediately; otherwise just return the draft
    if data.get("send_now", False):
        result = email_system.send_email(to_email, email_data["subject"], email_data["body"])
        if result["success"]:
            db.log_email({
                "professor_id": professor_id,
                "professor_name": professor.get("name", ""),
                "professor_email": to_email,
                "subject": email_data["subject"],
                "body": email_data["body"],
                "email_type": "followup",
                "status": "sent",
                "sent_at": datetime.now(),
            })
            return jsonify({"success": True, "message": f"Follow-up sent to {to_email}"})
        else:
            return jsonify({"success": False, "message": result["message"]}), 400
    else:
        return jsonify({
            "subject": email_data["subject"],
            "body": email_data["body"],
            "method": "followup",
        })


def _generate_ai_followup(professor, original_body, student_profile):
    """Generate a follow-up email using Gemini AI."""
    from google import genai
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    prof_name = professor.get("name", "Professor")
    student_name = student_profile.get("name", "Student")
    primary_area = professor.get("research_areas", ["research"])
    area = primary_area[0] if primary_area else "your research"

    prompt = f"""Write a brief, professional follow-up email from a student to a professor.

CONTEXT:
- Student: {student_name}
- Professor: {prof_name}
- Research area: {area}
- Original email excerpt: {original_body[:300]}

RULES:
1. Keep it SHORT — 80-120 words maximum.
2. Reference the original email naturally.
3. Be polite but not groveling. Show continued interest.
4. Do NOT repeat the full original pitch.
5. Return ONLY the email body text.
"""
    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    body = response.text.strip()
    subject = f"Following Up — Research Internship Inquiry | {student_name}"
    return {"subject": subject, "body": body}


# ------------------------------------------------------------------ #
#  API: Update Professor Email
# ------------------------------------------------------------------ #
@main_bp.route("/api/professor/<int:pid>/email", methods=["PUT"])
def api_update_professor_email(pid):
    """Update email address for a professor."""
    data = request.json or {}
    new_email = data.get("email", "").strip()

    if not new_email or "@" not in new_email:
        return jsonify({"error": "Invalid email address"}), 400

    professor = db.get_professor_by_id(pid)
    if not professor:
        return jsonify({"error": "Professor not found"}), 404

    db.conn.execute(
        "UPDATE professors SET email=?, updated_at=? WHERE id=?",
        (new_email, datetime.now(), pid)
    )
    db.conn.commit()

    return jsonify({"success": True, "email": new_email})


# ------------------------------------------------------------------ #
#  API: Gmail Sync
# ------------------------------------------------------------------ #
@main_bp.route("/api/sync-gmail", methods=["POST"])
def api_sync_gmail():
    """Start a background Gmail IMAP sync to import past sent emails."""
    global _sync_state

    with _sync_lock:
        if _sync_state["status"] == "running":
            return jsonify({"error": "Sync already in progress"}), 409

    email_addr = config.GMAIL_EMAIL
    app_password = config.GMAIL_APP_PASSWORD

    if not email_addr or not app_password:
        return jsonify({
            "error": "Gmail credentials not configured. Add GMAIL_EMAIL and GMAIL_APP_PASSWORD to your .env file.",
        }), 400

    # Optional: how many days back to look (default 180)
    data = request.json or {}
    days_back = int(data.get("days_back", 180))

    with _sync_lock:
        _sync_state = {
            "status": "running",
            "progress": 0,
            "message": "Starting Gmail sync…",
            "imported": 0,
            "skipped": 0,
            "total_scanned": 0,
            "error": "",
        }

    def _run_sync():
        global _sync_state
        syncer = GmailSync(email_addr, app_password)

        def _progress(pct, msg):
            with _sync_lock:
                _sync_state["progress"] = pct
                _sync_state["message"] = msg

        result = syncer.sync_sent_emails(db, days_back=days_back, progress_cb=_progress)

        with _sync_lock:
            _sync_state["status"] = "done" if not result.get("errors") else "error"
            _sync_state["progress"] = 100
            _sync_state["imported"] = result["imported"]
            _sync_state["skipped"] = result["skipped"]
            _sync_state["total_scanned"] = result["total_scanned"]
            _sync_state["message"] = (
                f"Done! Imported {result['imported']} emails from {result['total_scanned']} scanned."
            )
            if result.get("errors"):
                _sync_state["error"] = result["errors"][0]
                _sync_state["message"] = result["errors"][0]

        logger.info(f"Gmail sync complete: {result}")

    thread = threading.Thread(target=_run_sync, daemon=True)
    thread.start()

    return jsonify({"status": "started"})


@main_bp.route("/api/sync-gmail/status", methods=["GET"])
def api_sync_status():
    """Poll Gmail sync progress."""
    with _sync_lock:
        return jsonify(dict(_sync_state))
