import requests
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# Constants
MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
)

# Google Calendar API Configuration
GOOGLE_CALENDAR_API_KEY = "AIzaSyCqM48SD4d5j2ccE57TWKXhzrdC9QKvn8E"
INDIAN_HOLIDAY_CALENDAR_ID = "en.indian%23holiday%40group.v.calendar.google.com"
CALENDAR_API_BASE_URL = "https://www.googleapis.com/calendar/v3/calendars"

# Data directory for storing JSON files
DATA_DIR = Path(__file__).parent / "festival_data"
DATA_DIR.mkdir(exist_ok=True)

# Mapping rules for festivals → recipes

FESTIVAL_MAPPINGS = {
    "eid": "Eid Recipes",
    "Milad un-Nabi": "Eid Recipes",
    "diwali": "Diwali Recipes",
    "durga": "durga-puja",
    "onam": "Onam recipes",
    # "holi": "Holi Recipes",
    # "christmas": "Christmas Recipes",
    # "dussehra": "Dussehra Recipes",
    "navratri": "Navratri Recipes",
    # "karwa chauth": "Karwa Chauth Recipes",
    "raksha bandhan": "Raksha Bandhan Recipes",
    # "janmashtami": "Janmashtami Recipes",
    # "ganesh chaturthi": "Ganesh Chaturthi Recipes"
}
def normalize_festival_name(name: str) -> str:
    """Map festival names to recipe categories if matched."""
    lower_name = name.lower()
    for keyword, mapped_value in FESTIVAL_MAPPINGS.items():
        if keyword in lower_name:
            return mapped_value
    return name

class GoogleCalendarFestivalScraper:
    """Streamlined scraper for Indian festivals using Google Calendar API"""

    @staticmethod
    def _get_json_file_path(year: int) -> Path:
        """Get the path for the JSON file for a given year."""
        return DATA_DIR / f"festivals_{year}.json"
    
    @staticmethod
    def _load_from_json(year: int) -> Optional[Dict[str, List[Dict[str, str]]]]:
        """Load festival data from JSON file if it exists."""
        json_file = GoogleCalendarFestivalScraper._get_json_file_path(year)
        if json_file.exists():
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('festivals', data)
            except (json.JSONDecodeError, IOError):
                return None
        return None
    
    @staticmethod
    def _save_to_json(year: int, data: Dict[str, List[Dict[str, str]]]) -> bool:
        """Save festival data to JSON file."""
        json_file = GoogleCalendarFestivalScraper._get_json_file_path(year)
        try:
            json_data = {
                "year": year,
                "generated_at": datetime.now().isoformat(),
                "source": "Google Calendar API",
                "festivals": data
            }
            
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            return True
        except IOError:
            return False

    @staticmethod
    def _fetch_holidays_from_api(year: int) -> List[Dict]:
        """Fetch holidays from Google Calendar API for a specific year."""
        time_min = f"{year}-01-01T00:00:00Z"
        time_max = f"{year + 1}-01-01T00:00:00Z"
        
        url = f"{CALENDAR_API_BASE_URL}/{INDIAN_HOLIDAY_CALENDAR_ID}/events"
        params = {
            'timeMin': time_min,
            'timeMax': time_max,
            'maxResults': 250,
            'singleEvents': True,
            'orderBy': 'startTime',
            'key': GOOGLE_CALENDAR_API_KEY
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get('items', [])
        except (requests.exceptions.RequestException, json.JSONDecodeError):
            return []

    @staticmethod
    def _parse_google_calendar_events(events: List[Dict]) -> Dict[str, List[Dict[str, str]]]:
        """Parse Google Calendar events into month-wise festival data with name mapping."""
        festivals_by_month = {}
        seen_festivals = {}  # Track duplicates by month and mapped name
        
        for event in events:
            try:
                # Get event name
                original_name = event.get('summary', '').strip()
                if not original_name:
                    continue
                
                # Apply festival name mapping
                mapped_name = normalize_festival_name(original_name)
                
                # Get event date
                start = event.get('start', {})
                if 'date' in start:
                    date_str = start['date']
                elif 'dateTime' in start:
                    date_str = start['dateTime'][:10]
                else:
                    continue
                
                # Parse date
                try:
                    event_date = datetime.fromisoformat(date_str.replace('Z', ''))
                    date_iso = event_date.strftime("%Y-%m-%d")
                    month_year = f"{MONTH_NAMES[event_date.month - 1]} {event_date.year}"
                    
                    # Check for duplicates (same month + same mapped name)
                    duplicate_key = f"{month_year}_{mapped_name}"
                    if duplicate_key in seen_festivals:
                        continue
                    
                    # Initialize month list if not exists
                    if month_year not in festivals_by_month:
                        festivals_by_month[month_year] = []
                    
                    # Add festival with mapped name
                    festival = {
                        "date": date_iso,
                        "name": mapped_name
                    }
                    
                    festivals_by_month[month_year].append(festival)
                    seen_festivals[duplicate_key] = True
                        
                except ValueError:
                    continue
                    
            except Exception:
                continue
        
        # Sort festivals by date within each month
        for month in festivals_by_month:
            festivals_by_month[month].sort(key=lambda x: x['date'])
        
        return festivals_by_month

    @staticmethod
    def _fetch_festivals_for_year(year: int) -> Dict[str, List[Dict[str, str]]]:
        """Fetch and parse festival data from Google Calendar API."""
        events = GoogleCalendarFestivalScraper._fetch_holidays_from_api(year)
        return GoogleCalendarFestivalScraper._parse_google_calendar_events(events)

    @staticmethod
    def generate_json_for_year(year: int, force_update: bool = False) -> bool:
        """Generate JSON file for a specific year by fetching from Google Calendar API."""
        json_file = GoogleCalendarFestivalScraper._get_json_file_path(year)
        
        if json_file.exists() and not force_update:
            return True
        
        try:
            festival_data = GoogleCalendarFestivalScraper._fetch_festivals_for_year(year)
            if festival_data:
                return GoogleCalendarFestivalScraper._save_to_json(year, festival_data)
            return False
        except Exception:
            return False

    @staticmethod
    def get_festivals_for_year(year: int) -> Dict[str, List[Dict[str, str]]]:
        """Get festivals for a year. First tries to load from JSON, falls back to API if needed."""
        # Try to load from JSON first
        json_data = GoogleCalendarFestivalScraper._load_from_json(year)
        if json_data:
            return json_data
        
        # Fallback to API
        try:
            festival_data = GoogleCalendarFestivalScraper._fetch_festivals_for_year(year)
            if festival_data:
                GoogleCalendarFestivalScraper._save_to_json(year, festival_data)
            return festival_data
        except Exception:
            return {}

    @staticmethod
    def get_festivals_for_month(year: int, month: int) -> List[Dict[str, str]]:
        """Get festivals for a specific month."""
        data = GoogleCalendarFestivalScraper.get_festivals_for_year(year)
        key = f"{MONTH_NAMES[month-1]} {year}"
        return data.get(key, [])

# --- CLI Interface for Local JSON Generation ---
def generate_json_files(years: List[int], force_update: bool = False):
    """Helper function to generate JSON files for multiple years."""
    for year in years:
        GoogleCalendarFestivalScraper.generate_json_for_year(year, force_update)

# --- Example Usage ---
if __name__ == "__main__":
    # Generate JSON files
    generate_json_files([2025, 2026], force_update=False)
    
    # Test data retrieval
    sept_festivals = GoogleCalendarFestivalScraper.get_festivals_for_month(2025, 9)
    for festival in sept_festivals:
        print(f"  {festival['date']}: {festival['name']}")