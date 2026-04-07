"""
resume_parser.py — Extract structured profile data from a PDF resume.

Pipeline:
  1. PyMuPDF extracts raw text from the uploaded PDF.
  2. Google Gemini AI parses the text into structured fields.
  3. Falls back to regex-based extraction when AI is unavailable.
"""

import json
import logging
import re

import fitz  # PyMuPDF

from .config import config

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF byte-stream using PyMuPDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for page in doc:
        pages.append(page.get_text("text"))
    doc.close()
    return "\n".join(pages)


def parse_resume(pdf_bytes: bytes) -> dict:
    """
    Full pipeline: PDF → text → structured profile dict.

    Returns a dict matching the profile_builder schema:
      name, email, university, degree, year, cgpa, bio,
      research_interests, skills, projects,
      github_url, linkedin_url, achievements
    """
    raw_text = extract_text_from_pdf(pdf_bytes)

    if not raw_text.strip():
        return {"error": "Could not extract text from PDF. Is it a scanned image?"}

    if config.ai_enabled:
        try:
            result = _parse_with_ai(raw_text)
            result["_method"] = "ai"
            result["_raw_text"] = raw_text[:500]
            return result
        except Exception as e:
            logger.warning(f"AI resume parsing failed, using regex: {e}")

    result = _parse_with_regex(raw_text)
    result["_method"] = "regex"
    result["_raw_text"] = raw_text[:500]
    return result


# ------------------------------------------------------------------
#  AI-powered parsing (Gemini)
# ------------------------------------------------------------------
def _parse_with_ai(raw_text: str) -> dict:
    """Use Gemini to parse resume text into structured fields."""
    from google import genai

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    prompt = f"""
You are a resume parser. Extract structured information from the following resume text.
Return ONLY a valid JSON object with these exact keys (use empty string or empty list if not found):

{{
  "name": "Full name",
  "email": "Email address",
  "university": "University or college name",
  "degree": "Degree program (e.g. Bachelor's, Master's, PhD)",
  "year": "Current year (e.g. 3rd Year, Final Year)",
  "cgpa": "CGPA or GPA as a number, 0 if not found",
  "bio": "A 2-sentence research statement or professional summary",
  "research_interests": ["interest1", "interest2", ...],
  "skills": ["skill1", "skill2", ...],
  "projects": ["One-line project description 1", "One-line project description 2", ...],
  "github_url": "GitHub URL if found",
  "linkedin_url": "LinkedIn URL if found",
  "portfolio_url": "Portfolio/personal website URL if found",
  "achievements": "Achievements, awards, publications as a single string"
}}

IMPORTANT RULES:
- research_interests should be broad topics like "Machine Learning", "NLP", "Computer Vision"
- skills should be specific technologies like "Python", "PyTorch", "Docker"
- projects should be concise one-line descriptions
- Return ONLY the JSON object, no markdown, no explanation

RESUME TEXT:
{raw_text[:4000]}
"""

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )

    text = response.text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    parsed = json.loads(text)

    # Normalize types
    if isinstance(parsed.get("cgpa"), str):
        try:
            parsed["cgpa"] = float(parsed["cgpa"])
        except ValueError:
            parsed["cgpa"] = 0.0

    if isinstance(parsed.get("research_interests"), str):
        parsed["research_interests"] = [x.strip() for x in parsed["research_interests"].split(",")]
    if isinstance(parsed.get("skills"), str):
        parsed["skills"] = [x.strip() for x in parsed["skills"].split(",")]
    if isinstance(parsed.get("projects"), str):
        parsed["projects"] = [x.strip() for x in parsed["projects"].split("\n") if x.strip()]

    return parsed


# ------------------------------------------------------------------
#  Regex fallback
# ------------------------------------------------------------------
def _parse_with_regex(raw_text: str) -> dict:
    """Basic regex-based resume parsing as fallback."""
    result = {
        "name": "",
        "email": "",
        "university": "",
        "degree": "",
        "year": "",
        "cgpa": 0.0,
        "bio": "",
        "research_interests": [],
        "skills": [],
        "projects": [],
        "github_url": "",
        "linkedin_url": "",
        "portfolio_url": "",
        "achievements": "",
    }

    lines = raw_text.split("\n")
    text_lower = raw_text.lower()

    # Email
    email_match = re.search(r"[\w.+%-]+@[\w.-]+\.\w{2,}", raw_text)
    if email_match:
        result["email"] = email_match.group(0)

    # Name — usually the first non-empty line
    for line in lines[:5]:
        line = line.strip()
        if line and not re.search(r"@|http|resume|cv|curriculum", line.lower()):
            if len(line) < 60 and not line[0].isdigit():
                result["name"] = line
                break

    # GitHub
    gh = re.search(r"https?://github\.com/[\w\-]+", raw_text, re.IGNORECASE)
    if gh:
        result["github_url"] = gh.group(0)

    # LinkedIn
    li = re.search(r"https?://(?:www\.)?linkedin\.com/in/[\w\-]+", raw_text, re.IGNORECASE)
    if li:
        result["linkedin_url"] = li.group(0)

    # CGPA/GPA
    cgpa_match = re.search(r"(?:CGPA|GPA|CPI)[:\s]*(\d+\.?\d*)", raw_text, re.IGNORECASE)
    if cgpa_match:
        try:
            result["cgpa"] = float(cgpa_match.group(1))
        except ValueError:
            pass

    # University
    uni_patterns = [
        r"(?:University|Institute|College|IIT|NIT|BITS|IIIT|VIT|SRM)\s*(?:of)?\s*[\w\s,]+",
    ]
    for pat in uni_patterns:
        match = re.search(pat, raw_text, re.IGNORECASE)
        if match:
            result["university"] = match.group(0).strip()[:80]
            break

    # Skills — look for a skills section
    skills_section = _extract_section(raw_text, ["skills", "technical skills", "technologies"])
    if skills_section:
        # Split by common delimiters
        skills = re.split(r"[,;|•·\n]", skills_section)
        result["skills"] = [s.strip() for s in skills if s.strip() and len(s.strip()) < 40][:15]

    # Projects
    projects_section = _extract_section(raw_text, ["projects", "key projects", "academic projects"])
    if projects_section:
        project_lines = [l.strip() for l in projects_section.split("\n") if l.strip() and len(l.strip()) > 10]
        result["projects"] = project_lines[:5]

    # Research interests
    research_section = _extract_section(raw_text, ["research", "research interests", "areas of interest"])
    if research_section:
        interests = re.split(r"[,;|•·\n]", research_section)
        result["research_interests"] = [i.strip() for i in interests if i.strip() and len(i.strip()) < 50][:8]

    # Degree
    degree_match = re.search(
        r"(B\.?Tech|B\.?Sc|M\.?Tech|M\.?Sc|Ph\.?D|Bachelor|Master|MBA)", raw_text, re.IGNORECASE
    )
    if degree_match:
        d = degree_match.group(1)
        if re.match(r"b", d, re.IGNORECASE):
            result["degree"] = "Bachelor's"
        elif re.match(r"m", d, re.IGNORECASE):
            result["degree"] = "Master's"
        elif re.match(r"ph", d, re.IGNORECASE):
            result["degree"] = "PhD"

    return result


def _extract_section(text: str, section_names: list) -> str:
    """Extract text under a section header."""
    lines = text.split("\n")
    collecting = False
    collected = []

    for line in lines:
        stripped = line.strip().lower()
        # Check if this line is a section header
        if any(name in stripped for name in section_names):
            collecting = True
            continue
        # Stop at the next section header
        if collecting and stripped and re.match(r"^[A-Z][A-Z\s]{2,}$", line.strip()):
            break
        if collecting:
            collected.append(line)
    return "\n".join(collected[:20])
