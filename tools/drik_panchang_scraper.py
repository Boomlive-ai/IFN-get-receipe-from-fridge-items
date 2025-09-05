import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from datetime import datetime, timedelta
import re
from collections import OrderedDict
from typing import List, Dict, Optional
import time
import random
import json
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

# Mapping rules for festivals → recipes
FESTIVAL_MAPPINGS = {
    "eid": "Eid Recipes",
    # Add more mappings as needed:
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
    """Scraper for DrikPanchang Indian Festival Calendar"""

    # --- Helpers ---
    

    @staticmethod
    def _fetch_html(year: int) -> BeautifulSoup:
        # Rotate User-Agents
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        
        session = requests.Session()
        
        # More convincing headers
        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",  # Added Hindi for Indian site
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
        
        # First, visit the homepage to get cookies
        try:
            print("Getting initial cookies...")
            homepage = session.get("https://www.drikpanchang.com", timeout=30)
            print(f"Homepage status: {homepage.status_code}")
            time.sleep(random.uniform(2, 4))  # Human-like delay
        except:
            pass
        
        for attempt in range(3):
            for u in URLS:
                url = u.format(year=year)
                try:
                    if attempt > 0:
                        delay = random.uniform(3, 7)  # Longer random delays
                        print(f"Waiting {delay:.1f}s before retry...")
                        time.sleep(delay)
                    
                    print(f"Attempt {attempt + 1}: Fetching {url}")
                    r = session.get(url, timeout=45)
                    
                    print(f"Status: {r.status_code}, Length: {len(r.text)}")
                    
                    if r.status_code == 200 and len(r.text) > 1000:
                        return BeautifulSoup(r.text, "html.parser")
                    elif r.status_code == 403:
                        print("Still blocked - trying next URL or retry")
                        continue
                        
                except requests.exceptions.RequestException as e:
                    print(f"Request failed: {e}")
                    continue
        
        raise RuntimeError(f"Failed to fetch calendar for {year} - all attempts blocked")

    @staticmethod
    def _parse_li_text(li_text: str) -> Optional[Dict[str,str]]:
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
            return festivals  # success

        # fallback: token-based
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
                if len(tok.split()) <= 8:  # heuristic
                    last_name = tok
        return festivals

    @staticmethod
    def _month_sections(soup, year: int):
        header_re = re.compile(rf"^({'|'.join(MONTH_NAMES)})\s+{year}$", re.I)
        headers = [(h.get_text(strip=True), h) for h in soup.find_all(lambda t: isinstance(t, Tag) and header_re.match(t.get_text(strip=True)))]
        return [(title, h, headers[i+1][1] if i+1 < len(headers) else None) for i,(title,h) in enumerate(headers)]

    # --- Public Methods ---
    @staticmethod
    def get_festivals_for_year(year: int) -> Dict[str,List[Dict[str,str]]]:
        soup = DrikPanchangFestivalScraper._fetch_html(year)
        results = OrderedDict()
        for title, start, end in DrikPanchangFestivalScraper._month_sections(soup, year):
            results[title] = DrikPanchangFestivalScraper._parse_section(start, end)
        return results

    @staticmethod
    def get_festivals_for_month(year: int, month: int) -> List[Dict[str,str]]:
        data = DrikPanchangFestivalScraper.get_festivals_for_year(year)
        key = f"{MONTH_NAMES[month-1]} {year}"
        return data.get(key, [])

    @staticmethod
    def get_festivals_for_week(year: int, month: int, week_number: int) -> List[Dict[str,str]]:
        month_fests = DrikPanchangFestivalScraper.get_festivals_for_month(year, month)
        first_day = datetime(year, month, 1)
        start_week = first_day + timedelta(weeks=week_number-1)
        end_week = start_week + timedelta(days=6)
        return [f for f in month_fests if start_week <= datetime.fromisoformat(f["date"]) <= end_week]

    @staticmethod
    def get_festivals_in_range(start_date: str, end_date: str) -> List[Dict[str,str]]:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        data = DrikPanchangFestivalScraper.get_festivals_for_year(start.year)
        fests = [f for month in data.values() for f in month]
        return [f for f in fests if start <= datetime.fromisoformat(f["date"]) <= end]


# --- Example ---
if __name__ == "__main__":
    print("=== September 2025 Festivals ===")
    print(DrikPanchangFestivalScraper.get_festivals_for_month(2025, 9))

    print("\n=== Week 2 of September 2025 ===")
    print(DrikPanchangFestivalScraper.get_festivals_for_week(2025, 9, 2))

    print("\n=== Custom Range (2025-08-20 to 2025-09-04) ===")
    print(DrikPanchangFestivalScraper.get_festivals_in_range("2025-08-20", "2025-09-04"))
