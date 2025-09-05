import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from datetime import datetime, timedelta
import re
from collections import OrderedDict
from typing import List, Dict, Optional
import time
import random
import json
import os
from pathlib import Path

# Constants
MONTH_NAMES = (
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
)
DATE_RE = re.compile(rf"({'|'.join(MONTH_NAMES)})\s+\d{{1,2}},\s+\d{{4}}", re.I)

URLS = [
    "https://www.drikpanchang.com/calendars/indian/indiancalendar.html?year={year}",
    "https://www.drikpanchang.com/calendars/indian/indiancalendar.html"
]

# Data directory for storing JSON files
DATA_DIR = Path(__file__).parent / "festival_data"
DATA_DIR.mkdir(exist_ok=True)

# Mapping rules for festivals → recipes
FESTIVAL_MAPPINGS = {
    "eid": "Eid Recipes",
    # "diwali": "Diwali Recipes",
    # "holi": "Holi Recipes",
    # "christmas": "Christmas Recipes"
}

def normalize_festival_name(name: str) -> str:
    """Map festival names to recipe categories if matched."""
    lower_name = name.lower()
    for keyword, mapped_value in FESTIVAL_MAPPINGS.items():
        if keyword in lower_name:
            return mapped_value
    return name

class DrikPanchangFestivalScraper:
    """Scraper for DrikPanchang Indian Festival Calendar with JSON caching"""

    # --- JSON File Operations ---
    
    @staticmethod
    def _get_json_file_path(year: int) -> Path:
        """Get the path for the JSON file for a given year."""
        return DATA_DIR / f"festivals_{year}.json"
    
    @staticmethod
    def _load_from_json(year: int) -> Optional[Dict[str, List[Dict[str, str]]]]:
        """Load festival data from JSON file if it exists."""
        json_file = DrikPanchangFestivalScraper._get_json_file_path(year)
        if json_file.exists():
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"Loaded festival data for {year} from JSON file")
                return data
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading JSON file for {year}: {e}")
                return None
        return None
    
    @staticmethod
    def _save_to_json(year: int, data: Dict[str, List[Dict[str, str]]]) -> bool:
        """Save festival data to JSON file."""
        json_file = DrikPanchangFestivalScraper._get_json_file_path(year)
        try:
            # Add metadata
            json_data = {
                "year": year,
                "generated_at": datetime.now().isoformat(),
                "source": "DrikPanchang",
                "festivals": data
            }
            
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            print(f"Saved festival data for {year} to {json_file}")
            return True
        except IOError as e:
            print(f"Error saving JSON file for {year}: {e}")
            return False

    @staticmethod
    def generate_json_for_year(year: int, force_update: bool = False) -> bool:
        """
        Generate JSON file for a specific year by scraping.
        Use this function locally to generate JSON files.
        """
        json_file = DrikPanchangFestivalScraper._get_json_file_path(year)
        
        if json_file.exists() and not force_update:
            print(f"JSON file for {year} already exists. Use force_update=True to regenerate.")
            return True
        
        try:
            print(f"Generating JSON file for {year}...")
            scraped_data = DrikPanchangFestivalScraper._scrape_festivals_for_year(year)
            return DrikPanchangFestivalScraper._save_to_json(year, scraped_data)
        except Exception as e:
            print(f"Failed to generate JSON for {year}: {e}")
            return False

    # --- Web Scraping Methods ---
    
    @staticmethod
    def _fetch_html(year: int) -> BeautifulSoup:
        """Fetch HTML from DrikPanchang website."""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        
        session = requests.Session()
        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            "DNT": "1",
            "Sec-CH-UA": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"'
        }
        session.headers.update(headers)
        
        for attempt in range(3):
            for u in URLS:
                url = u.format(year=year)
                try:
                    if attempt > 0:
                        delay = random.uniform(3, 7)
                        print(f"Waiting {delay:.1f}s before retry...")
                        time.sleep(delay)
                    
                    print(f"Attempt {attempt + 1}: Fetching {url}")
                    r = session.get(url, timeout=45)
                    print(f"Status: {r.status_code}, Length: {len(r.text)}")
                    
                    if r.status_code == 200 and len(r.text) > 1000:
                        return BeautifulSoup(r.text, "html.parser")
                    elif r.status_code == 403:
                        print("Blocked - trying next URL or retry")
                        continue
                        
                except requests.exceptions.RequestException as e:
                    print(f"Request failed: {e}")
                    continue
        
        raise RuntimeError(f"Failed to fetch calendar for {year}")

    @staticmethod
    def _parse_li_text(li_text: str) -> Optional[Dict[str,str]]:
        """Parse festival text from list items."""
        m = DATE_RE.search(li_text)
        if not m:
            return None
        date_str = m.group(0)
        name = li_text[:m.start()].strip(" :-–—,") or li_text[m.end():].strip(" :-–—,")
        try:
            date_iso = datetime.strptime(date_str, "%B %d, %Y").strftime("%Y-%m-%d")
            return {"date": date_iso, "name": normalize_festival_name(name)}
        except:
            return None

    @staticmethod
    def _parse_section(start: Tag, end: Optional[Tag]) -> List[Dict[str,str]]:
        """Parse a section of the HTML for festivals."""
        festivals = []
        node = start
        while node and node != end:
            if isinstance(node, Tag) and node.name == "ul":
                for li in node.find_all("li"):
                    parsed = DrikPanchangFestivalScraper._parse_li_text(li.get_text(" ", strip=True))
                    if parsed:
                        festivals.append(parsed)
            node = node.next_element

        if festivals:
            return festivals

        # Fallback parsing
        texts, node = [], start
        while node and node != end:
            if isinstance(node, NavigableString):
                t = str(node).strip()
                if t:
                    texts.append(t)
            node = node.next_element

        tokens = [t.strip(" ,;:-–—") for t in " | ".join(texts).split("|") if t.strip()]
        last_name = None
        for tok in tokens:
            m = DATE_RE.search(tok)
            if m:
                try:
                    date_iso = datetime.strptime(m.group(0), "%B %d, %Y").strftime("%Y-%m-%d")
                    if last_name:
                        festivals.append({"date": date_iso, "name": normalize_festival_name(last_name)})
                except:
                    pass
                last_name = None
            else:
                if len(tok.split()) <= 8:
                    last_name = tok
        return festivals

    @staticmethod
    def _month_sections(soup, year: int):
        """Extract month sections from the HTML."""
        header_re = re.compile(rf"^({'|'.join(MONTH_NAMES)})\s+{year}$", re.I)
        headers = [(h.get_text(strip=True), h) for h in soup.find_all(lambda t: isinstance(t, Tag) and header_re.match(t.get_text(strip=True)))]
        return [(title, h, headers[i+1][1] if i+1 < len(headers) else None) for i,(title,h) in enumerate(headers)]

    @staticmethod
    def _scrape_festivals_for_year(year: int) -> Dict[str,List[Dict[str,str]]]:
        """Scrape festival data directly from website (internal method)."""
        soup = DrikPanchangFestivalScraper._fetch_html(year)
        results = OrderedDict()
        for title, start, end in DrikPanchangFestivalScraper._month_sections(soup, year):
            results[title] = DrikPanchangFestivalScraper._parse_section(start, end)
        return results

    # --- Public Methods (Production Ready) ---
    
    @staticmethod
    def get_festivals_for_year(year: int) -> Dict[str,List[Dict[str,str]]]:
        """
        Get festivals for a year. First tries to load from JSON, 
        falls back to scraping if JSON doesn't exist.
        """
        # Try to load from JSON first
        json_data = DrikPanchangFestivalScraper._load_from_json(year)
        if json_data:
            return json_data.get('festivals', json_data)
        
        # Fallback to scraping (mainly for development)
        print(f"JSON file not found for {year}, attempting to scrape...")
        try:
            scraped_data = DrikPanchangFestivalScraper._scrape_festivals_for_year(year)
            # Save for future use
            DrikPanchangFestivalScraper._save_to_json(year, scraped_data)
            return scraped_data
        except Exception as e:
            print(f"Scraping failed for {year}: {e}")
            return {}

    @staticmethod
    def get_festivals_for_month(year: int, month: int) -> List[Dict[str,str]]:
        """Get festivals for a specific month."""
        data = DrikPanchangFestivalScraper.get_festivals_for_year(year)
        key = f"{MONTH_NAMES[month-1]} {year}"
        return data.get(key, [])

    @staticmethod
    def get_festivals_for_week(year: int, month: int, week_number: int) -> List[Dict[str,str]]:
        """Get festivals for a specific week."""
        month_fests = DrikPanchangFestivalScraper.get_festivals_for_month(year, month)
        first_day = datetime(year, month, 1)
        start_week = first_day + timedelta(weeks=week_number-1)
        end_week = start_week + timedelta(days=6)
        return [f for f in month_fests if start_week <= datetime.fromisoformat(f["date"]) <= end_week]

    @staticmethod
    def get_festivals_in_range(start_date: str, end_date: str) -> List[Dict[str,str]]:
        """Get festivals within a date range."""
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        data = DrikPanchangFestivalScraper.get_festivals_for_year(start.year)
        fests = [f for month in data.values() for f in month]
        return [f for f in fests if start <= datetime.fromisoformat(f["date"]) <= end]

    # --- Utility Methods ---
    
    @staticmethod
    def list_available_years() -> List[int]:
        """List all years for which JSON data is available."""
        years = []
        for file in DATA_DIR.glob("festivals_*.json"):
            try:
                year = int(file.stem.split('_')[1])
                years.append(year)
            except ValueError:
                continue
        return sorted(years)
    
    @staticmethod
    def is_year_cached(year: int) -> bool:
        """Check if data for a year is already cached in JSON."""
        return DrikPanchangFestivalScraper._get_json_file_path(year).exists()

# --- CLI Interface for Local JSON Generation ---
def generate_json_files(years: List[int], force_update: bool = False):
    """
    Helper function to generate JSON files for multiple years.
    Run this locally to create JSON files.
    """
    for year in years:
        print(f"\n--- Processing {year} ---")
        success = DrikPanchangFestivalScraper.generate_json_for_year(year, force_update)
        if success:
            print(f"✓ Successfully generated JSON for {year}")
        else:
            print(f"✗ Failed to generate JSON for {year}")
        
        # Add delay between years to be respectful
        if year != years[-1]:
            time.sleep(5)

# --- Example Usage ---
if __name__ == "__main__":
    # For local development: Generate JSON files
    print("=== Generating JSON Files ===")
    generate_json_files([2025, 2026], force_update=False)
    
    print("\n=== Available Years ===")
    print(DrikPanchangFestivalScraper.list_available_years())
    
    print("\n=== Testing Data Retrieval ===")
    print("September 2025 Festivals:")
    print(DrikPanchangFestivalScraper.get_festivals_for_month(2025, 9))
    
    print("\nWeek 2 of September 2025:")
    print(DrikPanchangFestivalScraper.get_festivals_for_week(2025, 9, 2))
    
    print("\nCustom Range (2025-08-20 to 2025-09-04):")
    print(DrikPanchangFestivalScraper.get_festivals_in_range("2025-08-20", "2025-09-04"))
