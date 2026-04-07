"""
database.py — Upgraded SQLite database layer.
Full schema: professors, student_profile, email_log, follow_up_queue.
"""

import sqlite3
import json
import logging
from datetime import datetime, date
from .config import config

logger = logging.getLogger(__name__)


class ProfessorDatabase:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DATABASE_PATH
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row   # Dict-like rows
        self.create_tables()

    # ------------------------------------------------------------------ #
    #  Schema
    # ------------------------------------------------------------------ #
    def create_tables(self):
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS professors (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                name              TEXT NOT NULL,
                university        TEXT,
                department        TEXT,
                email             TEXT,
                scholar_url       TEXT,
                research_areas    TEXT,   -- JSON array
                recent_papers     TEXT,   -- concatenated text
                publication_count INTEGER DEFAULT 0,
                h_index           INTEGER DEFAULT 0,
                bio               TEXT,
                match_score       REAL    DEFAULT 0,
                match_grade       TEXT,
                matched_topics    TEXT,   -- JSON array
                last_contact      DATE,
                status            TEXT    DEFAULT "new",
                notes             TEXT,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS student_profile (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_json   TEXT NOT NULL,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS email_log (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                professor_id   INTEGER REFERENCES professors(id),
                professor_name TEXT,
                professor_email TEXT,
                subject        TEXT,
                body           TEXT,
                email_type     TEXT DEFAULT "initial",   -- initial | followup
                status         TEXT DEFAULT "generated", -- generated | sent | replied | bounced
                sent_at        TIMESTAMP,
                replied_at     TIMESTAMP,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS follow_up_queue (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                email_log_id   INTEGER REFERENCES email_log(id),
                professor_id   INTEGER REFERENCES professors(id),
                scheduled_for  TIMESTAMP NOT NULL,
                status         TEXT DEFAULT "pending",  -- pending | sent | cancelled
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS scraping_logs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                source       TEXT,
                search_term  TEXT,
                results_count INTEGER,
                timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        self.conn.commit()
        self._migrate()

    def _migrate(self):
        """Apply schema migrations safely for existing databases."""
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(professors)").fetchall()]
        if "h_index" not in cols:
            self.conn.execute("ALTER TABLE professors ADD COLUMN h_index INTEGER DEFAULT 0")
            self.conn.commit()
            logger.info("Migration: added h_index column")

    # ------------------------------------------------------------------ #
    #  Professors
    # ------------------------------------------------------------------ #
    def upsert_professor(self, data: dict) -> int:

        """Insert or update a professor by name+university."""
        cursor = self.conn.cursor()
        # Check if exists
        cursor.execute(
            "SELECT id FROM professors WHERE LOWER(name)=LOWER(?) AND LOWER(university)=LOWER(?)",
            (data.get("name", ""), data.get("university", ""))
        )
        row = cursor.fetchone()

        if row:
            pid = row["id"]
            cursor.execute('''
                UPDATE professors SET
                    department=?, email=?, scholar_url=?, research_areas=?,
                    recent_papers=?, publication_count=?, h_index=?, bio=?,
                    match_score=?, match_grade=?, matched_topics=?,
                    status=?, updated_at=?
                WHERE id=?
            ''', (
                data.get("department", ""),
                data.get("email", ""),
                data.get("scholar_url", ""),
                json.dumps(data.get("research_areas", [])),
                data.get("recent_papers", ""),
                data.get("publication_count", 0),
                data.get("h_index", 0),
                data.get("bio", ""),
                data.get("match_score", 0),
                data.get("match_grade", ""),
                json.dumps(data.get("matched_topics", [])),
                data.get("status", "new"),
                datetime.now(),
                pid,
            ))
        else:
            cursor.execute('''
                INSERT INTO professors
                (name, university, department, email, scholar_url, research_areas,
                 recent_papers, publication_count, h_index, bio, match_score, match_grade,
                 matched_topics, status, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                data.get("name", ""),
                data.get("university", ""),
                data.get("department", ""),
                data.get("email", ""),
                data.get("scholar_url", ""),
                json.dumps(data.get("research_areas", [])),
                data.get("recent_papers", ""),
                data.get("publication_count", 0),
                data.get("h_index", 0),
                data.get("bio", ""),
                data.get("match_score", 0),
                data.get("match_grade", ""),
                json.dumps(data.get("matched_topics", [])),
                data.get("status", "new"),
                datetime.now(),
            ))
            pid = cursor.lastrowid

        self.conn.commit()
        return pid

    def get_all_professors(self, limit: int = 100) -> list:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM professors ORDER BY match_score DESC LIMIT ?", (limit,)
        )
        return [self._row_to_prof(r) for r in cursor.fetchall()]

    def get_professor_by_id(self, pid: int) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM professors WHERE id=?", (pid,))
        row = cursor.fetchone()
        return self._row_to_prof(row) if row else None

    def _row_to_prof(self, row) -> dict:
        d = dict(row)
        d["research_areas"] = json.loads(d.get("research_areas") or "[]")
        d["matched_topics"] = json.loads(d.get("matched_topics") or "[]")
        return d

    def clear_professors(self):
        self.conn.execute("DELETE FROM professors")
        self.conn.commit()

    # ------------------------------------------------------------------ #
    #  Student Profile
    # ------------------------------------------------------------------ #
    def save_profile(self, profile: dict) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO student_profile (profile_json) VALUES (?)",
            (json.dumps(profile),)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_latest_profile(self) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT profile_json FROM student_profile ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return json.loads(row["profile_json"]) if row else None

    # ------------------------------------------------------------------ #
    #  Email Log
    # ------------------------------------------------------------------ #
    def log_email(self, data: dict) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO email_log
            (professor_id, professor_name, professor_email, subject, body,
             email_type, status, sent_at)
            VALUES (?,?,?,?,?,?,?,?)
        ''', (
            data.get("professor_id"),
            data.get("professor_name", ""),
            data.get("professor_email", ""),
            data.get("subject", ""),
            data.get("body", ""),
            data.get("email_type", "initial"),
            data.get("status", "generated"),
            data.get("sent_at"),
        ))
        self.conn.commit()
        return cursor.lastrowid

    def update_email_status(self, email_id: int, status: str):
        now = datetime.now()
        extra = {}
        if status == "sent":
            extra["sent_at"] = now
        if status == "replied":
            extra["replied_at"] = now

        fields = ", ".join([f"{k}=?" for k in extra.keys()] + ["status=?", "updated_at=?"])
        values = list(extra.values()) + [status, now, email_id]
        self.conn.execute(f"UPDATE email_log SET {fields} WHERE id=?", values)
        self.conn.commit()

    def get_email_log(self, limit: int = 200) -> list:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM email_log ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in cursor.fetchall()]

    def count_sent_today(self) -> int:
        today = date.today().isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as n FROM email_log WHERE status='sent' AND DATE(sent_at)=?",
            (today,)
        )
        return cursor.fetchone()["n"]

    # ------------------------------------------------------------------ #
    #  Follow-up Queue
    # ------------------------------------------------------------------ #
    def add_follow_up(self, email_log_id: int, professor_id: int, scheduled_for: datetime) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO follow_up_queue (email_log_id, professor_id, scheduled_for)
            VALUES (?,?,?)
        ''', (email_log_id, professor_id, scheduled_for))
        self.conn.commit()
        return cursor.lastrowid

    def get_pending_follow_ups(self) -> list:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT fq.*, el.professor_email, el.professor_name, el.body as original_body
            FROM follow_up_queue fq
            JOIN email_log el ON fq.email_log_id = el.id
            WHERE fq.status='pending' AND fq.scheduled_for <= ?
        ''', (datetime.now(),))
        return [dict(r) for r in cursor.fetchall()]

    def mark_follow_up_sent(self, fq_id: int):
        self.conn.execute(
            "UPDATE follow_up_queue SET status='sent' WHERE id=?", (fq_id,)
        )
        self.conn.commit()

    # ------------------------------------------------------------------ #
    #  Stats
    # ------------------------------------------------------------------ #
    def get_stats(self) -> dict:
        cursor = self.conn.cursor()

        def _count(sql, params=()):
            cursor.execute(sql, params)
            return cursor.fetchone()[0]

        return {
            "total_professors": _count("SELECT COUNT(*) FROM professors"),
            "emails_sent": _count("SELECT COUNT(*) FROM email_log WHERE status='sent'"),
            "emails_replied": _count("SELECT COUNT(*) FROM email_log WHERE status='replied'"),
            "follow_ups_pending": _count("SELECT COUNT(*) FROM follow_up_queue WHERE status='pending'"),
            "sent_today": self.count_sent_today(),
        }

    # ------------------------------------------------------------------ #
    #  Scraping Logs
    # ------------------------------------------------------------------ #
    def log_scraping(self, source: str, search_term: str, results_count: int):
        self.conn.execute(
            "INSERT INTO scraping_logs (source, search_term, results_count) VALUES (?,?,?)",
            (source, search_term, results_count)
        )
        self.conn.commit()


# Shared singleton
db = ProfessorDatabase()
