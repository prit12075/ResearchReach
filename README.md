# Professor Finder AI

An intelligent Flask application designed to help students find and match with research professors globally. It uses AI to parse resumes, match research interests, and automate personalized outreach.

## Features

- **Resume Parsing**: Upload a PDF resume to automatically build your academic profile.
- **Smart Matching**: Uses TF-IDF and Cosine Similarity to find professors whose research aligns with your interests.
- **Automated Outreach**: Generate personalized emails for each professor and schedule follow-ups.
- **Dashboard**: Track your outreach status, replies, and scheduled follow-ups.
- **Gmail Sync**: Sync with your Gmail to import past outreach emails and track student-professor interactions.

## Project Structure

```text
professor-finder/
├── app/                  # Main application package
│   ├── core/             # Business logic (Scrapers, Parsers, Matchers)
│   ├── static/           # CSS, JS, and Images
│   └── templates/        # HTML Templates (Jinja2)
├── run.py                # Server entry point
├── .env                  # Environment variables (Hidden)
├── requirements.txt      # Python dependencies
└── README.md             # This file
```

## Setup Instructions

1. **Clone the repository**:
   ```bash
   git clone <your-repo-url>
   cd professor-finder
   ```

2. **Create a virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```
   Fill in your API keys (Gemini, Gmail App Password, etc.).

5. **Run the application**:
   ```bash
   python run.py
   ```
   The app will be available at `http://localhost:5000` (or the port specified in `.env`).

## Technologies Used

- **Backend**: Flask, Python
- **AI/ML**: Google Gemini (genai), Scikit-learn (TF-IDF)
- **Database**: SQLite
- **Scraping**: BeautifulSoup, Requests
- **Scheduler**: APScheduler
