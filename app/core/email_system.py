"""
email_system.py — AI-powered email generator + Gmail SMTP sender.

Generates personalized outreach emails using:
  1. Google Gemini AI (if API key present)
  2. High-quality template fallback (no API key needed)

Sends via Gmail SMTP with App Password authentication.
"""

import smtplib
import ssl
import logging
import textwrap
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from .config import config

logger = logging.getLogger(__name__)


class EmailSystem:
    def __init__(self):
        self.smtp_server = config.SMTP_SERVER
        self.smtp_port   = config.SMTP_PORT
        # NOTE: Read email/password at call time so .env changes
        # take effect after a server restart without code changes.

    @property
    def email(self):    return config.GMAIL_EMAIL
    @property
    def password(self): return config.GMAIL_APP_PASSWORD

    # ------------------------------------------------------------------ #
    #  Email Generation
    # ------------------------------------------------------------------ #
    def generate_email(self, professor: dict, student_profile: dict) -> dict:
        """
        Generate a personalized email for a professor.

        Returns: {"subject": str, "body": str, "method": str}
        """
        if config.ai_enabled:
            try:
                result = self._generate_with_ai(professor, student_profile)
                result["method"] = "ai"
                return result
            except Exception as e:
                logger.warning(f"AI generation failed, using template: {e}")

        result = self._generate_from_template(professor, student_profile)
        result["method"] = "template"
        return result

    def _generate_with_ai(self, professor: dict, student_profile: dict) -> dict:
        """Generate email using Google Gemini (google-genai SDK v1.x)."""
        try:
            from google import genai
            client = genai.Client(api_key=config.GEMINI_API_KEY)
        except ImportError:
            raise RuntimeError("google-genai not installed. Run: pip install google-genai")

        prof_name = professor.get("name", "Professor")
        prof_areas = ", ".join(professor.get("research_areas", [])[:3])
        prof_papers = professor.get("recent_papers", "")[:300]
        prof_uni = professor.get("university", "your institution")

        student_name = student_profile.get("name", "Student")
        student_uni = student_profile.get("university", "my university")
        student_interests = ", ".join(student_profile.get("research_interests", [])[:5])
        student_projects = "\n".join(student_profile.get("projects", [])[:2])
        student_skills = ", ".join(student_profile.get("skills", [])[:6])
        duration = student_profile.get("internship_duration", "2 months")
        github = student_profile.get("github_url", "")
        linkedin = student_profile.get("linkedin_url", "")

        prompt = f"""
You are writing a professional, sincere cold outreach email from a student to a professor.

STUDENT:
- Name: {student_name}
- University: {student_uni}
- Research interests: {student_interests}
- Key projects: {student_projects}
- Skills: {student_skills}
- GitHub: {github}
- LinkedIn: {linkedin}

PROFESSOR:
- Name: {prof_name}
- Institution: {prof_uni}
- Research areas: {prof_areas}
- Recent publications: {prof_papers}

INSTRUCTIONS:
1. Write a professional, warm email asking for a {duration} research internship.
2. Reference the professor's SPECIFIC recent work naturally.
3. Draw clear connections between the student's projects/skills and the professor's research.
4. Keep the tone enthusiastic but not over-the-top. Avoid flattery clichés.
5. Length: 200–280 words body, 3–4 paragraphs.
6. Do NOT include a subject line in the body — only return the email body.
7. Sign off with the student's name and key links.

Return ONLY the email body text. No markdown formatting.
"""
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        body = response.text.strip()

        subject = (
            f"Interest in Your Research on {_first_area(professor)} — "
            f"Internship Inquiry from {student_name}"
        )
        return {"subject": subject, "body": body}

    def _generate_from_template(self, professor: dict, student_profile: dict) -> dict:
        """High-quality template-based email generation."""
        prof_name = professor.get("name", "Professor")
        prof_last_name = prof_name.split()[-1] if prof_name else "Professor"
        prof_areas = professor.get("research_areas", ["your research area"])
        prof_uni = professor.get("university", "your institution")
        prof_papers = professor.get("recent_papers", "")

        student_name = student_profile.get("name", "[Your Name]")
        student_uni = student_profile.get("university", "[Your University]")
        student_interests = student_profile.get("research_interests", [])
        student_projects = student_profile.get("projects", [])
        student_skills = student_profile.get("skills", [])
        github = student_profile.get("github_url", "")
        linkedin = student_profile.get("linkedin_url", "")
        duration = student_profile.get("internship_duration", "2 months")

        # Find the best interest overlap
        primary_area = _first_area(professor)
        student_primary = student_interests[0] if student_interests else "machine learning"
        related_project = student_projects[0] if student_projects else "a related research project"
        top_skills = ", ".join(student_skills[:4]) if student_skills else "Python and ML frameworks"

        # Build a specific reference to their work
        paper_ref = ""
        if prof_papers:
            first_paper = prof_papers.split(".")[0][:120]
            paper_ref = f'particularly your recent work on "{first_paper}"'
        else:
            paper_ref = f"your work in {primary_area}"

        body = textwrap.dedent(f"""
Dear Professor {prof_last_name},

I hope this message finds you well. I have been following your research in {primary_area} at {prof_uni} — {paper_ref} — and I find the direction deeply compelling.

I am {student_name}, a student at {student_uni} with a strong focus on {student_primary}. I have been working on {related_project}, which has given me hands-on experience with {top_skills}. Your research aligns closely with the problems I am most excited about, and I believe there is genuine overlap where I could contribute meaningfully.

I would be honored to explore the possibility of a {duration} research internship under your guidance. I am eager to apply my background to your ongoing projects and to learn from your team's expertise in {", ".join(prof_areas[:2])}.

I have attached my CV for your review. Please also find my work at:
{f"GitHub: {github}" if github else ""}
{f"LinkedIn: {linkedin}" if linkedin else ""}

Thank you sincerely for your time and consideration. I look forward to the possibility of working together.

Best regards,
{student_name}
{student_uni}
        """).strip()

        subject = (
            f"Research Internship Inquiry — {primary_area} | {student_name}"
        )
        return {"subject": subject, "body": body}

    # ------------------------------------------------------------------ #
    #  Email Sending
    # ------------------------------------------------------------------ #
    def send_email(self, to_email: str, subject: str, body: str) -> dict:
        """
        Send an email via Gmail SMTP.

        Returns: {"success": bool, "message": str}
        """
        if not config.email_sending_enabled:
            return {
                "success": False,
                "message": "Email sending not configured. Add GMAIL_EMAIL and GMAIL_APP_PASSWORD to .env",
            }

        if not to_email or "@" not in to_email:
            return {"success": False, "message": "Invalid recipient email address."}

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.email
            msg["To"] = to_email

            # Plain text part
            msg.attach(MIMEText(body, "plain"))

            # HTML part (light styling)
            html_body = _body_to_html(body)
            msg.attach(MIMEText(html_body, "html"))

            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.ehlo()
                server.starttls(context=context)
                server.login(self.email, self.password)
                server.sendmail(self.email, to_email, msg.as_string())

            logger.info(f"Email sent to {to_email}: {subject}")
            return {"success": True, "message": f"Email sent successfully to {to_email}"}

        except smtplib.SMTPAuthenticationError:
            msg = "Gmail authentication failed. Check your App Password in .env"
            logger.error(msg)
            return {"success": False, "message": msg}
        except Exception as e:
            logger.error(f"Send failed: {e}")
            return {"success": False, "message": str(e)}

    def generate_followup_email(self, professor: dict, original_body: str, student_profile: dict) -> dict:
        """Generate a brief follow-up email."""
        prof_name = professor.get("name", "Professor")
        prof_last = prof_name.split()[-1] if prof_name else "Professor"
        student_name = student_profile.get("name", "[Your Name]")
        primary_area = _first_area(professor)

        body = textwrap.dedent(f"""
Dear Professor {prof_last},

I hope you are doing well. I wanted to follow up on my previous email regarding a potential research internship in {primary_area}.

I remain very interested in your work and would love the opportunity to contribute to your team. If you have had a chance to review my application, I would greatly appreciate any feedback or the opportunity for a brief conversation.

I understand you are likely very busy, and I appreciate your time.

Best regards,
{student_name}
        """).strip()

        subject = f"Following Up — Research Internship Inquiry | {student_name}"
        return {"subject": subject, "body": body}


# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #
def _first_area(professor: dict) -> str:
    areas = professor.get("research_areas", [])
    return areas[0] if areas else "your research area"


def _body_to_html(body: str) -> str:
    paragraphs = body.split("\n\n")
    html_paragraphs = "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs)
    return f"""
    <html><body style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        {html_paragraphs}
    </body></html>
    """


# Singleton
email_system = EmailSystem()
