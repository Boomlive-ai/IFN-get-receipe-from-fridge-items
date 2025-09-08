from IPython.display import Markdown
import textwrap
import os, json, re
import base64
from openai import OpenAI
from PIL import Image
import io

import requests
from datetime import datetime, timedelta
# Commented out Gemini code
# import google.generativeai as genai
# GOOGLE_API_KEY=os.getenv('GOOGLE_API_KEY')
# genai.configure(api_key=GOOGLE_API_KEY)
# llm  = genai.GenerativeModel('gemini-1.5-pro-latest')

# OpenAI setup
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=OPENAI_API_KEY)

def encode_image_to_base64(image_path):
    """Encode image file to base64 for OpenAI API"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def encode_pil_image_to_base64(pil_image):
    """Encode PIL Image to base64 for OpenAI API"""
    buffer = io.BytesIO()
    # Save as JPEG if it's not already
    if pil_image.mode == 'RGBA':
        pil_image = pil_image.convert('RGB')
    pil_image.save(buffer, format='JPEG')
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

def generate_food_or_ingredients_in_image(img):
    # Commented out Gemini implementation
    # response = llm.generate_content([
    #     "Analyze image and provide list of what are main ingredients(Eg:- Colliflower) detected which we can use to cook in JSON format", 
    #     img
    # ])
    # response = llm.generate_content([
    #         "Analyze the image and provide a list of detected food ingredients in JSON format. "
    #         "The response **MUST** strictly follow this structure:\n"
    #         '{\n  "ingredients": ["Tomato Puree", "Jam", "Yogurt", "Chocolate Spread", "Pickle", "Milk", "Gochujang", "Butter", "Soy Sauce", "Pickles", "Orange", "Juice"]\n}'
    #         "\nOnly include actual food ingredients and nothing else."
    #         "\nEnsure the response contains no additional text, explanations, or formatting issues."
    #         "\nIf no valid ingredients are detected, return an empty list in the same format."
    #         "\nExample of an empty response:"
    #         '\n{\n  "ingredients": []\n}'
    #         "\nStrictly follow this format with no additional information."
    #         , img
    #     ])

    # OpenAI implementation
    try:
        # Check if img is a file path (string) or PIL Image
        if isinstance(img, str):
            base64_image = encode_image_to_base64(img)
        elif hasattr(img, 'save'):  # PIL Image object
            base64_image = encode_pil_image_to_base64(img)
        else:
            # Handle other cases - try to convert to PIL Image first
            try:
                if hasattr(img, 'read'):  # File-like object
                    img = Image.open(img)
                    base64_image = encode_pil_image_to_base64(img)
                else:
                    raise ValueError("Unsupported image type")
            except Exception as e:
                return {"error": f"Failed to process image: {str(e)}"}
        
        response = client.chat.completions.create(
            model="gpt-4.1-mini",  # Using latest OpenAI model
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analyze the image and provide a list of detected food ingredients in JSON format. "
                                   "The response **MUST** strictly follow this structure:\n"
                                   '{\n  "ingredients": ["Tomato Puree", "Jam", "Yogurt", "Chocolate Spread", "Pickle", "Milk", "Gochujang", "Butter", "Soy Sauce", "Pickles", "Orange", "Juice"]\n}'
                                   "\nOnly include actual food ingredients and nothing else."
                                   "\nEnsure the response contains no additional text, explanations, or formatting issues."
                                   "\nIf no valid ingredients are detected, return an empty list in the same format."
                                   "\nExample of an empty response:"
                                   '\n{\n  "ingredients": []\n}'
                                   "\nStrictly follow this format with no additional information."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.1
        )
    except Exception as e:
        return {"error": f"Failed to analyze image: {str(e)}"}

    print("isme arha hai")

    # OpenAI response handling
    if response.choices:
        # Extract the text from the response
        raw_text = response.choices[0].message.content
        print(raw_text)
        # Parse JSON from the raw text
        try:
            cleaned_text = clean_raw_text(raw_text)
            parsed_result = json.loads(cleaned_text)
            print(parsed_result)
            return parsed_result
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON from AI response: {str(e)}")
    else:
        return {"error": "No ingredients detected."}

    # Commented out Gemini response handling
    # if response.candidates:
    # # Extract the text from the first candidate
    #     raw_text = response.candidates[0].content.parts[0].text
    #     print(raw_text)
    #     # Parse JSON from the raw text
    #     try:
    #         cleaned_text = clean_raw_text(raw_text)
    #         parsed_result = json.loads(cleaned_text)
    #         print(parsed_result)
    #         return parsed_result
    #     except json.JSONDecodeError as e:
    #         raise ValueError(f"Failed to parse JSON from AI response: {str(e)}")
    # else:
    #     return {"error": "No ingredients detected."}

def clean_raw_text(raw_text):
    """
    Clean the raw text to extract only valid JSON content.
    Removes triple backticks, "json" markers, and extracts JSON payload.
    """
    # Remove starting and ending backticks with "json" marker
    raw_text = raw_text.lstrip('```json').rstrip('```').strip()

    # Extract JSON content within curly braces    
    json_match = re.search(r'{.*}', raw_text, re.DOTALL)
    if json_match:
        return json_match.group(0).strip()  # Extract and clean
    raise ValueError("No valid JSON object found in the raw text.")

def to_markdown(text):
    text = text.replace('•', '  *')
    return Markdown(textwrap.indent(text, '> ', predicate=lambda _: True))
# def get_festivals(api_key=None, start_date=None, end_date=None):
#     """Get festivals in specified date range in India"""
#     import requests
#     from datetime import datetime, timedelta
    
#     # Default to current week if no dates provided
#     if not start_date or not end_date:
#         today = datetime.now()
#         start_date = (today - timedelta(days=today.weekday())).date()
#         end_date = (start_date + timedelta(days=6))
    
#     festivals_in_range = []
    
#     try:
#         # Primary source: calendar-bharat
#         years_to_check = list(set([start_date.year, end_date.year]))
        
#         for year in years_to_check:
#             calendar_url = f"https://jayantur13.github.io/calendar-bharat/calendar/{year}.json"
#             r = requests.get(calendar_url, timeout=10)
            
#             if r.status_code == 200:
#                 calendar_data = r.json()
                
#                 # Navigate through the correct structure: year -> month -> date
#                 year_data = calendar_data.get(str(year), {})
                
#                 for month_name, month_data in year_data.items():
#                     # month_name is like "January 2025", "February 2025", etc.
                    
#                     for date_key, event_info in month_data.items():
#                         # date_key is like "January 1, 2025, Wednesday"
#                         try:
#                             # Extract just the date part (remove day name)
#                             # Split by comma and take first two parts
#                             date_parts = date_key.split(', ')
#                             if len(date_parts) >= 2:
#                                 date_str = f"{date_parts[0]}, {date_parts[1]}"  # "January 1, 2025"
#                                 event_date = datetime.strptime(date_str, "%B %d, %Y").date()
                                
#                                 if start_date <= event_date <= end_date:
#                                     # Get event details
#                                     event_name = event_info.get('event', '')
#                                     event_type = event_info.get('type', '')
                                    
#                                     # Filter for festivals (include both "Religional Festival" and other festival types)
#                                     if ('Festival' in event_type or 
#                                         'Government Holiday' in event_type or 
#                                         event_type == 'Good to know'):
                                        
#                                         festivals_in_range.append({
#                                             'date': event_date.strftime('%Y-%m-%d'),
#                                             'name': event_name,
#                                             'type': event_type,
#                                             'extras': event_info.get('extras', ''),
#                                             'source': 'calendar-bharat'
#                                         })
                        
#                         except (ValueError, IndexError) as e:
#                             # Skip invalid date entries
#                             print(f"Error parsing date '{date_key}': {e}")
#                             continue
#     except Exception as e:
#         print(f"Error fetching festivals: {e}")
#         return []
    
#     # Remove duplicates and sort by date
#     unique_festivals = {}
#     for festival in festivals_in_range:
#         key = f"{festival['date']}_{festival['name']}"
#         if key not in unique_festivals:
#             unique_festivals[key] = festival
    
#     # Sort by date
#     result = list(unique_festivals.values())
#     result.sort(key=lambda x: x['date'])
    
#     # Clean response format (remove extra fields for API response)
#     return [{'date': f['date'], 'name': f['name']} for f in result]

def get_festivals(start_date=None, end_date=None, range_type="week"):
    """Get festivals in specified date range in India using Drik Panchang scraper"""
    from datetime import datetime, timedelta
    import calendar
    from tools.drik_panchang_scraper import DrikPanchangFestivalScraper
    from tools.festivals import GoogleCalendarFestivalScraper
    today = datetime.now()

    # --- Determine date range ---
    if not start_date or not end_date:
        if range_type == "month":
            start_date = today.replace(day=1).date()
            end_date = today.replace(day=calendar.monthrange(today.year, today.month)[1]).date()
        elif range_type == "year":
            start_date = datetime(today.year, 1, 1).date()
            end_date = datetime(today.year, 12, 31).date()
        else:  # default to week
            start_date = (today - timedelta(days=today.weekday())).date()
            end_date = start_date + timedelta(days=6)

    print(f"[DEBUG] get_festivals: range_type={range_type}, start_date={start_date}, end_date={end_date}")

    # --- Collect years needed ---
    years_needed = list(range(start_date.year, end_date.year + 1))
    results = []

    for year in years_needed:
        print(f"[DEBUG] Processing year {year}")

        if range_type == "month" and start_date.year == end_date.year:
            raw_data = {f"{calendar.month_name[start_date.month]} {year}":
                        GoogleCalendarFestivalScraper.get_festivals_for_month(year, start_date.month)}
        elif range_type == "year":
            raw_data = GoogleCalendarFestivalScraper.get_festivals_for_year(year)
        else:
            raw_data = GoogleCalendarFestivalScraper.get_festivals_for_year(year)

        # Flatten monthwise festivals
        for month_name, festivals in raw_data.items():
            for f in festivals:
                try:
                    fest_date = datetime.strptime(f["date"], "%Y-%m-%d").date()
                    if start_date <= fest_date <= end_date:
                        results.append({
                            "date": fest_date.strftime("%Y-%m-%d"),
                            "name": f["name"]
                        })
                except Exception as e:
                    print(f"[DEBUG] Skipping invalid entry: {f} — {e}")

    # --- Deduplicate and sort ---
    unique = {f"{f['date']}_{f['name']}": f for f in results}
    sorted_results = sorted(unique.values(), key=lambda x: x["date"])

    print(f"[DEBUG] Filtered festivals: {len(sorted_results)} festivals found")
    return sorted_results
