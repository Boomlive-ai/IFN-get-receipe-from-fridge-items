import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from datetime import datetime, timedelta
import re
from collections import OrderedDict
from typing import List, Dict, Optional

# Constants
MONTH_NAMES = (
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
)
DATE_RE = re.compile(rf"({'|'.join(MONTH_NAMES)})\s+\d{{1,2}},\s+\d{{4}}", re.I)

URLS = [
    # "https://www.drikpanchang.com/calendars/indian/indiancalendar-{year}.html",
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
        headers = {"User-Agent": "Mozilla/5.0"}
        for u in URLS:
            url = u.format(year=year)
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200 and len(r.text) > 1000:
                return BeautifulSoup(r.text, "html.parser")
        raise RuntimeError(f"Failed to fetch calendar for {year}")

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
