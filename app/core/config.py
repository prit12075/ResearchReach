import os
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
    FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))
    DEBUG = os.getenv("FLASK_ENV", "development") == "development"

    # Database
    DATABASE_PATH = os.getenv("DATABASE_PATH", "professor_finder.db")

    # AI / LLM
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

    # Email
    GMAIL_EMAIL = os.getenv("GMAIL_EMAIL", "")
    GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587

    # Rate limits
    MAX_EMAILS_PER_DAY = int(os.getenv("MAX_EMAILS_PER_DAY", 10))
    FOLLOWUP_INTERVAL_DAYS = int(os.getenv("FOLLOWUP_INTERVAL_DAYS", 3))

    # Optional APIs
    SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

    # Feature flags
    @property
    def ai_enabled(self):
        return bool(self.GEMINI_API_KEY or self.OPENAI_API_KEY)

    @property
    def email_sending_enabled(self):
        return bool(self.GMAIL_EMAIL and self.GMAIL_APP_PASSWORD)

config = Config()
