"""
profile_builder.py — Student academic profile parser and structurer.
Converts raw form inputs into a rich, structured profile used by the
matching engine and email generator.
"""

from datetime import datetime


def build_profile(form_data: dict) -> dict:
    """
    Parse and structure raw form input into a canonical student profile.

    Args:
        form_data: Raw dict from Flask request.form or API JSON body.

    Returns:
        Structured profile dict.
    """
    research_interests = _parse_tags(form_data.get("research_interests", ""))
    skills = _parse_tags(form_data.get("skills", ""))
    projects = _parse_projects(form_data.get("projects", ""))

    profile = {
        # Identity
        "name": form_data.get("name", "").strip(),
        "email": form_data.get("email", "").strip(),
        "university": form_data.get("university", "").strip(),
        "degree": form_data.get("degree", "Bachelor's").strip(),
        "year": form_data.get("year", "").strip(),
        "cgpa": _safe_float(form_data.get("cgpa", "")),

        # Research
        "research_interests": research_interests,
        "skills": skills,
        "projects": projects,

        # Links
        "github_url": form_data.get("github_url", "").strip(),
        "linkedin_url": form_data.get("linkedin_url", "").strip(),
        "portfolio_url": form_data.get("portfolio_url", "").strip(),

        # Search config
        "target_institution": form_data.get("target_institution", "").strip(),
        "internship_duration": form_data.get("internship_duration", "2 months").strip(),

        # Extra text for matching
        "bio": form_data.get("bio", "").strip(),
        "achievements": form_data.get("achievements", "").strip(),

        # Metadata
        "created_at": datetime.now().isoformat(),
    }

    # Build a single combined text blob for TF-IDF vectorization
    profile["full_text"] = _build_full_text(profile)

    return profile


def _parse_tags(raw: str) -> list:
    """Split comma/newline separated tags into a cleaned list."""
    if not raw:
        return []
    separators = [",", "\n", ";"]
    for sep in separators:
        raw = raw.replace(sep, ",")
    return [t.strip() for t in raw.split(",") if t.strip()]


def _parse_projects(raw: str) -> list:
    """Parse newline-separated project descriptions into a list."""
    if not raw:
        return []
    return [p.strip() for p in raw.split("\n") if p.strip()]


def _safe_float(val: str) -> float:
    """Safely convert string to float."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _build_full_text(profile: dict) -> str:
    """Concatenate all relevant text fields for vectorization."""
    parts = [
        profile["bio"],
        profile["achievements"],
        " ".join(profile["research_interests"]),
        " ".join(profile["skills"]),
        " ".join(profile["projects"]),
        profile["university"],
    ]
    return " ".join(filter(None, parts))


def get_demo_profile() -> dict:
    """Return a realistic demo profile for UI demonstration."""
    return build_profile({
        "name": "Prit Patel",
        "email": "prit.patel@example.com",
        "university": "PDEU — Pandit Deendayal Energy University",
        "degree": "B.Tech",
        "year": "3rd Year",
        "cgpa": "9.1",
        "research_interests": "Machine Learning, Computer Vision, NLP, AI in Healthcare, Robotics",
        "skills": "Python, PyTorch, TensorFlow, FastAPI, React, Docker, Kubernetes",
        "projects": (
            "Built a real-time AI meeting assistant using Whisper + Groq LLM\n"
            "Developed a phishing detection system with ML-based URL analysis\n"
            "Created an autonomous robot navigation system using ROS and SLAM"
        ),
        "github_url": "https://github.com/pritpatel",
        "linkedin_url": "https://linkedin.com/in/pritpatel",
        "bio": (
            "Final-year B.Tech student passionate about applied ML research, "
            "particularly in real-world AI systems at the intersection of "
            "computer vision and natural language processing."
        ),
        "achievements": (
            "National finalist — Smart India Hackathon 2024. "
            "Published paper on federated learning at ICML workshop."
        ),
        "target_institution": "",
        "internship_duration": "2 months",
    })
