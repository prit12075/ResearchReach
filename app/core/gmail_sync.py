"""
gmail_sync.py — Import previously sent professor emails from Gmail Sent folder.

Uses IMAP (no extra OAuth needed — same app password as sending).
Parses sent emails, detects professor outreach by keyword heuristics,
and imports them into the email_log + professors tables.
"""

import imaplib
import email
import email.header
import logging
import re
import json
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# Keywords that suggest an email is professor outreach
PROFESSOR_KEYWORDS = [
    "professor", "prof.", "dr.", "research", "internship",
    "lab", "phd", "faculty", "advisor", "mentor",
    "opportunity", "graduate", "undergraduate",
]

# Common academic TLDs/domains to identify professor recipients
ACADEMIC_PATTERNS = [
    r"\.edu$", r"\.ac\.", r"\.university\.", r"iit\.", r"mit\.edu",
]


class GmailSync:
    def __init__(self, email_addr: str, app_password: str):
        self.email_addr = email_addr
        self.app_password = app_password

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #
    def sync_sent_emails(
        self,
        db,
        days_back: int = 180,
        progress_cb=None,
        max_emails: int = 500,
    ) -> dict:
        """
        Connect to Gmail IMAP, scan Sent folder, import professor emails.

        Args:
            db: ProfessorDatabase instance
            days_back: How many days of history to scan
            progress_cb: Optional callback(pct, message) for progress updates
            max_emails: Safety cap on emails to process

        Returns:
            {"imported": int, "skipped": int, "total_scanned": int, "errors": list}
        """
        result = {"imported": 0, "skipped": 0, "total_scanned": 0, "errors": []}

        def _progress(pct, msg):
            logger.info(f"[Sync {pct}%] {msg}")
            if progress_cb:
                progress_cb(pct, msg)

        try:
            _progress(5, "Connecting to Gmail…")
            mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            mail.login(self.email_addr, self.app_password)

            _progress(10, "Opening Sent Mail folder…")

            # Try different Sent folder names Gmail uses
            sent_folders = ["[Gmail]/Sent Mail", "Sent", "[Google Mail]/Sent Mail", "INBOX.Sent"]
            selected = False
            for folder in sent_folders:
                try:
                    status, _ = mail.select(f'"{folder}"', readonly=True)
                    if status == "OK":
                        selected = True
                        break
                except Exception:
                    continue

            if not selected:
                # List available folders for debugging
                _, folder_list = mail.list()
                folders = [f.decode() for f in folder_list]
                logger.warning(f"Could not find Sent folder. Available: {folders}")
                result["errors"].append("Could not find Gmail Sent folder.")
                mail.logout()
                return result

            # Build date filter
            since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
            _progress(15, f"Searching emails since {since_date}…")

            _, msg_ids = mail.search(None, f'(SINCE "{since_date}")')
            all_ids = msg_ids[0].split() if msg_ids[0] else []
            total = len(all_ids)

            _progress(20, f"Found {total} sent emails to scan…")

            if total == 0:
                mail.logout()
                result["total_scanned"] = 0
                return result

            # Process most recent first, cap at max_emails
            ids_to_process = list(reversed(all_ids))[:max_emails]

            for i, msg_id in enumerate(ids_to_process):
                pct = 20 + int((i / len(ids_to_process)) * 70)
                if i % 20 == 0:
                    _progress(pct, f"Scanning email {i+1} of {len(ids_to_process)}…")

                try:
                    _, msg_data = mail.fetch(msg_id, "(RFC822)")
                    raw = msg_data[0][1]
                    parsed = email.message_from_bytes(raw)

                    processed = self._process_email(parsed, db)
                    result["total_scanned"] += 1

                    if processed == "imported":
                        result["imported"] += 1
                    else:
                        result["skipped"] += 1

                except Exception as e:
                    logger.debug(f"Error processing email {msg_id}: {e}")
                    result["errors"].append(str(e))

            mail.logout()
            _progress(95, f"Imported {result['imported']} professor emails!")

        except imaplib.IMAP4.error as e:
            msg = str(e)
            if "AUTHENTICATIONFAILED" in msg or "Invalid credentials" in msg:
                result["errors"].append(
                    "Gmail login failed. Make sure you're using an App Password, not your regular password. "
                    "Go to Google Account → Security → App Passwords."
                )
            else:
                result["errors"].append(f"IMAP error: {msg}")
            logger.error(f"IMAP error: {e}")

        except Exception as e:
            result["errors"].append(str(e))
            logger.error(f"Sync error: {e}")

        return result

    # ------------------------------------------------------------------ #
    #  Email Processing
    # ------------------------------------------------------------------ #
    def _process_email(self, msg, db) -> str:
        """
        Parse one sent email. Return 'imported' or 'skipped'.
        """
        to_addr = self._decode_header(msg.get("To", ""))
        subject = self._decode_header(msg.get("Subject", ""))
        date_str = msg.get("Date", "")

        if not to_addr or not subject:
            return "skipped"

        # Check if this looks like a professor outreach email
        if not self._is_professor_email(to_addr, subject, self._get_body(msg)):
            return "skipped"

        # Extract fields
        prof_email = self._extract_email(to_addr)
        prof_name = self._extract_name_from_to(to_addr)
        body = self._get_body(msg)
        sent_at = self._parse_date(date_str)

        if not prof_email:
            return "skipped"

        # Check if already in log (avoid duplication)
        existing = db.conn.execute(
            "SELECT id FROM email_log WHERE professor_email=? AND subject=?",
            (prof_email, subject),
        ).fetchone()

        if existing:
            return "skipped"

        # Find or create professor record
        prof_row = db.conn.execute(
            "SELECT id FROM professors WHERE LOWER(email)=LOWER(?)",
            (prof_email,),
        ).fetchone()

        if prof_row:
            prof_id = prof_row["id"]
        else:
            # Create minimal professor record from the email
            university = self._guess_university(prof_email, body)
            prof_id = db.upsert_professor({
                "name": prof_name or self._name_from_email(prof_email),
                "university": university,
                "department": "",
                "email": prof_email,
                "scholar_url": "",
                "research_areas": [],
                "recent_papers": "",
                "publication_count": 0,
                "bio": "",
                "match_score": 0.0,
                "match_grade": "Imported",
                "matched_topics": [],
                "status": "contacted",
            })

        # Log the email
        db.log_email({
            "professor_id": prof_id,
            "professor_name": prof_name or self._name_from_email(prof_email),
            "professor_email": prof_email,
            "subject": subject,
            "body": body[:3000],   # cap at 3000 chars
            "email_type": "followup" if self._is_followup(subject) else "initial",
            "status": "sent",
            "sent_at": sent_at,
        })

        # Mark professor as contacted
        db.conn.execute(
            "UPDATE professors SET status='contacted' WHERE id=?", (prof_id,)
        )
        db.conn.commit()

        return "imported"

    # ------------------------------------------------------------------ #
    #  Heuristics
    # ------------------------------------------------------------------ #
    def _is_professor_email(self, to_addr: str, subject: str, body: str) -> bool:
        """Decide if this email looks like professor outreach."""
        combined = (to_addr + " " + subject + " " + body[:500]).lower()

        # Must hit at least 2 professor keywords
        hits = sum(1 for kw in PROFESSOR_KEYWORDS if kw in combined)
        if hits < 2:
            return False

        # Prefer academic email domains, but don't require them
        recipient_email = self._extract_email(to_addr)
        if recipient_email:
            domain = recipient_email.split("@")[-1].lower()
            is_academic = any(
                re.search(pat, domain) for pat in ACADEMIC_PATTERNS
            )
            if is_academic:
                return True

        # Non-academic domain: require stronger signal (3+ keywords)
        return hits >= 3

    def _is_followup(self, subject: str) -> bool:
        s = subject.lower()
        return any(kw in s for kw in ["follow", "follow-up", "following up", "checking in", "re:", "fwd:"])

    def _guess_university(self, email_addr: str, body: str) -> str:
        """Try to infer university from email domain or body text."""
        domain = email_addr.split("@")[-1].lower()

        # Map common domains
        known = {
            "mit.edu": "MIT",
            "stanford.edu": "Stanford University",
            "harvard.edu": "Harvard University",
            "berkeley.edu": "UC Berkeley",
            "cmu.edu": "Carnegie Mellon University",
            "cornell.edu": "Cornell University",
            "caltech.edu": "Caltech",
            "ox.ac.uk": "University of Oxford",
            "cam.ac.uk": "University of Cambridge",
            "iitb.ac.in": "IIT Bombay",
            "iitd.ac.in": "IIT Delhi",
            "iitm.ac.in": "IIT Madras",
            "iisc.ac.in": "IISc Bangalore",
        }

        if domain in known:
            return known[domain]

        # Try to extract from subdomain: research.example.edu → example
        parts = domain.split(".")
        if len(parts) >= 2:
            name = parts[-2].replace("-", " ").title()
            if "university" not in name.lower():
                return f"{name} University"
            return name

        return ""

    # ------------------------------------------------------------------ #
    #  Parsers
    # ------------------------------------------------------------------ #
    def _decode_header(self, raw: str) -> str:
        if not raw:
            return ""
        parts = email.header.decode_header(raw)
        decoded = []
        for part, enc in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(enc or "utf-8", errors="replace"))
            else:
                decoded.append(str(part))
        return " ".join(decoded)

    def _extract_email(self, to_field: str) -> str:
        m = re.search(r"[\w.+%-]+@[\w.-]+\.\w{2,}", to_field)
        return m.group(0).lower() if m else ""

    def _extract_name_from_to(self, to_field: str) -> str:
        """Extract display name from 'Name <email>' format."""
        m = re.match(r'^"?([^"<]+)"?\s*<', to_field.strip())
        if m:
            return m.group(1).strip().strip('"').strip("'")
        return ""

    def _name_from_email(self, email_addr: str) -> str:
        """Make a readable name from email local-part."""
        local = email_addr.split("@")[0]
        local = re.sub(r"[\._\-\d]", " ", local)
        return " ".join(w.capitalize() for w in local.split() if w)

    def _get_body(self, msg) -> str:
        """Extract plain text body from email (or stripped html)."""
        body_parts = []
        html_parts = []
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        body_parts.append(part.get_payload(decode=True).decode(charset, errors="replace"))
                    except Exception:
                        pass
                elif ctype == "text/html":
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        html = part.get_payload(decode=True).decode(charset, errors="replace")
                        text_only = re.sub(r'<style[^>]*>[\s\S]*?</style>|<script[^>]*>[\s\S]*?</script>', '', html, flags=re.IGNORECASE)
                        text_only = re.sub(r'<[^>]+>', ' ', text_only)
                        text_only = re.sub(r'\s+', ' ', text_only).strip()
                        html_parts.append(text_only)
                    except Exception:
                        pass
        else:
            try:
                charset = msg.get_content_charset() or "utf-8"
                content = msg.get_payload(decode=True).decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    text_only = re.sub(r'<style[^>]*>[\s\S]*?</style>|<script[^>]*>[\s\S]*?</script>', '', content, flags=re.IGNORECASE)
                    text_only = re.sub(r'<[^>]+>', ' ', text_only)
                    content = re.sub(r'\s+', ' ', text_only).strip()
                body_parts.append(content)
            except Exception:
                pass
        
        final_body = "\n".join(body_parts) if body_parts else "\n".join(html_parts)
        return final_body[:3000]

    def _parse_date(self, date_str: str):
        if not date_str:
            return datetime.now()
        try:
            return parsedate_to_datetime(date_str).replace(tzinfo=None)
        except Exception:
            return datetime.now()
