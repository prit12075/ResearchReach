import os
import sys

# Add the app directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.web_scraper import WebScraper
from app.core.config import config

def run_test():
    if not config.ai_enabled:
        print("AI is not enabled. Please set GEMINI_API_KEY.")
        return
        
    scraper = WebScraper()
    print("Running Gemini AI Search...")
    results = scraper._gemini_professor_search("Reinforcement Learning", "MIT")
    for idx, r in enumerate(results):
        print(f"\n--- Result {idx+1} ---")
        for k, v in r.items():
            print(f"{k}: {v}")
            
if __name__ == "__main__":
    run_test()
