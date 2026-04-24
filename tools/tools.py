import requests
from bs4 import BeautifulSoup
import numpy as np
import pinecone
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone
import os,re,asyncio
from openai import AsyncOpenAI
from openai import OpenAI

# Initialize Pinecone
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv()
from tools.youtube_service import YouTubeService
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=OPENAI_API_KEY)
# Initialize Pinecone
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY")
)

index_name = "ifn-recipes"

# Ensure the index exists
# if index_name not in pc.list_indexes().names():
#     pc.create_index(
#         name=index_name,
#         dimension=1536,
#         metric="cosine"
#     )
index = pc.Index(index_name)



def fetch_second_span_values(url):
    """
    Fetches all values of the second <span> in <p> tags inside 'direction-box-layout1' elements.

    Args:
        url (str): The URL of the recipe webpage.

    Returns:
        list: A list of strings containing the content of the second <span>.
    """
    try:
        # Request the page content
        response = requests.get(url)
        response.raise_for_status()

        # Parse the HTML
        soup = BeautifulSoup(response.content, 'html.parser')

        # Locate all 'direction-box-layout1' elements
        direction_boxes = soup.find_all('div', class_='direction-box-layout1')
        print(direction_boxes)
        # Extract the second <span> value from each <p> tag
        span_values = []
        for box in direction_boxes:
            p_tag = box.find('p')
            if p_tag:
                spans = p_tag.find_all('span')
                if len(spans) > 1:  # Ensure there are at least two <span> elements
                    span_values.append(spans[1].get_text(strip=True))

        return span_values
    except Exception as e:
        print(f"An error occurred: {e}")
        return []

def fetch_youtube_link(url):
    """
    Fetches the YouTube video link from the given URL containing an embedded iframe.
    
    Args:
        url (str): The URL of the webpage to scrape.
    
    Returns:
        str: The YouTube video link if found, else None.
    """
    try:
        # Make a request to the URL
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors

        # Parse the HTML content of the page
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find the iframe tag with the YouTube video
        iframe = soup.find('iframe', src=True)
        
        if iframe and "youtube.com/embed" in iframe['src']:
            # Extract and format the YouTube link
            youtube_link = iframe['src'].split('?')[0]  # Remove query parameters
            return youtube_link
        else:
            return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
import re

def sanitize_id(input_string):
    """
    Sanitizes the given string to make it a valid ASCII ID for Pinecone.

    Args:
        input_string (str): The string to sanitize.

    Returns:
        str: A sanitized ASCII string.
    """
    # Replace non-ASCII characters with a placeholder (e.g., '?')
    sanitized = input_string.encode('ascii', 'ignore').decode('ascii')
    
    # Remove any special characters except for alphanumerics, dashes, and underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', sanitized)
    
    # Truncate if necessary to fit Pinecone ID length limits (if any)
    return sanitized

def extract_recipe_data(api_response):
    """
    Extracts required recipe information from the API response and stores it in Pinecone.
    """
    recipes = api_response.get("news", [])
    extracted_data = []
    print("These are the recipes fetched", len(recipes))

    for recipe in recipes:
        recipe_url = f"https://www.indiafoodnetwork.in{recipe.get('url', '')}"
        youtube_link = fetch_youtube_link(recipe_url) or ""
        ingredients = [ingredient.get("heading", "") for ingredient in recipe.get("ingredient", [])]
        steps = [step.get("description", "") for step in sorted(recipe.get("cookingstep", []), key=lambda x: x.get("uid", 0))]
        story = recipe.get("story", "") or ""
        thumbnail_image = recipe.get("thumbImage", "") or ""
        dish_name = recipe.get("heading", "") or "Unnamed Dish"

        sanitized_id = sanitize_id(dish_name)
        ingredient_text = " ".join(ingredients)
        ingredient_embedding = embeddings.embed_query(ingredient_text)

        try:
            index.upsert([(sanitized_id, ingredient_embedding, {
                "recipe_url": recipe_url,
                "dish_name": dish_name,
                "recipe_youtube_link": youtube_link,
                "ingredients": ingredients,
                "cooking_steps": steps,
                "story": story,
                "dish_image": thumbnail_image
            })])
        except Exception as e:
            print(f"Error upserting recipe '{dish_name}': {e}")
            continue

        extracted_data.append({
            "Dish Name": dish_name,
            "YouTube Link": youtube_link,
            "Ingredients": ingredients,
            "Steps to Cook": steps,
            "Story": story,
            "Thumbnail Image": thumbnail_image
        })

    return extracted_data



def fetch_recipe_data():
    """
    Calls the API and fetches the recipe data.
    """
    api_url = os.getenv("IFN_CONTENT_API_URL", "https://indiafoodnetwork.in/dev/h-api/content")
    headers = {'accept': '*/*', 's-id': os.getenv("FETCH_RECIPE_S_ID")}

    response = requests.get(api_url, headers=headers)
    
    if response.status_code == 200:
        api_response = response.json()
        return extract_recipe_data(api_response)
    else:
        print("Failed to fetch API response.")
        return None

# Initialize OpenAI client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def extract_dish_name_with_gpt(user_query):
    """
    Use GPT-4o-mini to extract dish name from natural language query
    """
    try:
        prompt = f"""
Extract only the dish name from this cooking query. Return just the dish name, nothing else.

Examples:
"I want to make butter chicken" -> "butter chicken"
"How do I cook chicken biryani?" -> "chicken biryani"
"Recipe for chocolate cake please" -> "chocolate cake"
"Can you help me prepare dal makhani?" -> "dal makhani"
"What's the best way to make pasta carbonara?" -> "pasta carbonara"
"I'm craving some paneer tikka" -> "paneer tikka"

Query: "{user_query}"

Dish name:"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts dish names from cooking queries. Return only the dish name, nothing else."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=50,
            temperature=0.1  # Low temperature for consistent extraction
        )
        
        extracted_dish = response.choices[0].message.content.strip()
        
        # Fallback to regex if GPT returns empty or invalid response
        if not extracted_dish or len(extracted_dish) > 100:
            return fallback_extract_dish_name(user_query)
            
        return extracted_dish.lower()
        
    except Exception as e:
        print(f"Error with GPT extraction: {e}")
        # Fallback to regex method
        return fallback_extract_dish_name(user_query)

def fallback_extract_dish_name(query):
    """
    Fallback regex-based extraction if GPT fails
    """
    cleaned = re.sub(r'\b(i want to make|how to make|recipe for|cooking|prepare|cook|help me|can you|what\'s the|best way to)\b', '', query.lower())
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned if cleaned else query.lower()

def filter_recipes_by_ingredients(recipes, user_ingredients, threshold=50):
    def normalize(text):
        return text.strip().lower()

    user_set = set(normalize(i) for i in user_ingredients)

    filtered = []

    for item in recipes:
        recipe_ingredients = item.get("Ingredients", [])
        recipe_set = set(normalize(i) for i in recipe_ingredients)

        matched = set()

        # ✅ Partial + exact match
        for r in recipe_set:
            for u in user_set:
                if u in r or r in u:
                    matched.add(r)
                    break

        if not recipe_set:
            continue

        match_percentage = (len(matched) / len(recipe_set)) * 100

        if match_percentage >= threshold:
            item["match_percentage"] = round(match_percentage, 2)
            item["matched_ingredients"] = list(matched)
            item["missing_ingredients"] = list(recipe_set - matched)

            filtered.append(item)

    # ✅ Sort best matches first
    filtered.sort(key=lambda x: x["match_percentage"], reverse=True)

    return filtered

def fetch_youtube_urls_from_db(dish_names):
    """
    Fetches YouTube URLs from PostgreSQL database for given dish names.
    Returns a dict mapping dish_name -> list of youtube_url rows.
    """
    import psycopg2
    DB_URL = os.getenv("DB_URL")

    result = {}
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        for name in dish_names:
            cur.execute(
                "SELECT url FROM flask_yt_details WHERE title ILIKE %s",
                (f"%{name}%",)
            )
            rows = cur.fetchall()
            result[name] = [row[0] for row in rows if row[0]]
        cur.close()
        conn.close()
    except Exception as e:
        print(f"DB error fetching YouTube URLs: {e}")

    return result



def fetch_recipes_by_filter(recipe_type: str, preparation_time: int, start_index: int = 0, count: int = 10):
    """
    Fetches recipes from India Food Network API filtered by recipe_type and preparation_time.
    YouTube link is fetched from PostgreSQL database instead of YouTube API.
    """
    api_url = os.getenv("IFN_CONTENT_FILTER_API_URL", "https://www.indiafoodnetwork.in/dev/h-api/contentFilter")
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "s-id": os.getenv("FETCH_RECIPES_BY_FILTER_S_ID")
    }
    params = {
        "content_type": "recipe",
        "param_name": ["recipe_type", "preparation_time"],
        "param_value": [recipe_type, str(preparation_time)],
        "startIndex": start_index,
        "count": count
    }

    response = requests.get(api_url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()

    recipes = data.get("news", [])
    parent_names = [item.get("parent_name") for item in recipes if item.get("parent_name")]

    # Step 1: Try fetching YouTube URLs from DB first
    dish_names = [item.get("heading", "") for item in recipes if item.get("heading")]
    yt_urls_map = fetch_youtube_urls_from_db(dish_names)
    print("YouTube URLs fetched from DB:", yt_urls_map)

    # Step 2: Find dish names that got no results from DB
    missing_dishes = [name for name in dish_names if not yt_urls_map.get(name)]

    # Step 3: Fallback to YouTubeService only for missing dishes
    yt_service = None
    if missing_dishes:
        print(f"Falling back to YouTubeService for {len(missing_dishes)} dishes: {missing_dishes}")
        try:
            yt_service = YouTubeService()
        except ValueError as e:
            print(f"YouTubeService error: {e}")

    for item in recipes:
        dish_name = item.get("heading", "")
        urls = yt_urls_map.get(dish_name, [])

        if urls:
            # DB had results — use them
            item["similar_youtube_videos"] = [{"video_url": url} for url in urls]
            item["scraped_youtube_link"] = urls[0]
        else:
            # Fallback to YouTube API for this dish
            similar_videos = []
            if yt_service and dish_name:
                try:
                    similar_videos = yt_service.search_recipe_videos(
                        recipe_name=dish_name,
                        max_results=3
                    )
                except Exception as e:
                    print(f"Error fetching YouTube videos for {dish_name}: {e}")

            item["similar_youtube_videos"] = similar_videos
            item["scraped_youtube_link"] = similar_videos[0]["video_url"] if similar_videos else ""

    return parent_names, recipes


def _is_non_veg_recipe(dish_name: str, ingredients: list) -> bool:
    """Check if a recipe contains non-vegetarian ingredients based on dish name and ingredient list."""
    non_veg_keywords = [
        "chicken", "mutton", "lamb", "goat", "pork", "beef", "meat", "keema",
        "fish", "prawn", "shrimp", "crab", "lobster", "squid", "octopus", "clam",
        "salmon", "tuna", "surmai", "pomfret", "rawas", "bangda", "rohu", "hilsa",
        "egg", "anda", "omelette", "omelet",
        "bacon", "ham", "sausage", "salami", "pepperoni",
        "murgh", "gosht", "jhinga", "machhi", "machi", "machli",
        "tikka chicken", "butter chicken", "tandoori chicken",
        "rogan josh", "nihari", "haleem", "seekh kabab","egg", "eggs",
    ]
    # Check dish name
    name_lower = dish_name.lower()
    for keyword in non_veg_keywords:
        if keyword in name_lower:
            return True
    # Check ingredients
    for ing in ingredients:
        ing_lower = ing.lower()
        for keyword in non_veg_keywords:
            if keyword in ing_lower:
                return True
    return False


def _is_non_vegan_recipe(dish_name: str, ingredients: list) -> bool:
    """Check if a recipe contains non-vegan ingredients."""
    non_vegan_keywords = [
        # All non-veg keywords
        "chicken", "mutton", "lamb", "goat", "pork", "beef", "meat", "keema",
        "fish", "prawn", "shrimp", "crab", "lobster", "squid", "egg", "anda",
        "murgh", "gosht", "jhinga", "machhi", "machi", "machli",
        # Dairy and animal products
        "milk", "cream", "butter", "ghee", "paneer", "cheese", "curd", "yogurt",
        "yoghurt", "dahi", "khoya", "mawa", "malai", "whey",
        "honey", "gelatin",
    ]
    name_lower = dish_name.lower()
    for keyword in non_vegan_keywords:
        if keyword in name_lower:
            return True
    for ing in ingredients:
        ing_lower = ing.lower()
        for keyword in non_vegan_keywords:
            if keyword in ing_lower:
                return True
    return False


def _contains_disliked(dish_name: str, ingredients: list, disliked: list) -> bool:
    """Check if a recipe contains any disliked ingredients."""
    name_lower = dish_name.lower()
    for d in disliked:
        d_lower = d.lower()
        if d_lower in name_lower:
            return True
        for ing in ingredients:
            if d_lower in ing.lower():
                return True
    return False


def fetch_recipe_by_filter_for_values(
    recipe_type: str,
    preparation_time: int,
    food_type: str = "",
    cuisines: list = None,
    disliked: list = None,
    mood: str = "",
    start_index: int = 0,
    count: int = 10
):
    """
    Fetches recipes from India Food Network API filtered by recipe_type and preparation_time,
    then filters results based on foodType (veg/non-veg), disliked ingredients, and cuisines using
    programmatic checks + OpenAI for cuisine/mood matching.
    """
    api_url = os.getenv("IFN_CONTENT_FILTER_API_URL", "https://www.indiafoodnetwork.in/dev/h-api/contentFilter")
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "s-id": os.getenv("FETCH_RECIPES_BY_FILTER_S_ID")
    }
    params = {
        "content_type": "recipe",
        "param_name": ["recipe_type", "preparation_time"],
        "param_value": [recipe_type, str(preparation_time)],
        "startIndex": start_index,
        "count": count
    }

    print(f"[API REQUEST] Calling IFN API with params: recipe_type={recipe_type}, preparation_time={preparation_time}, startIndex={start_index}, count={count}")
    response = requests.get(api_url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()

    recipes = data.get("news", [])
    total_from_api = len(recipes)
    print(f"[API RESPONSE] Total recipes returned from IFN API: {total_from_api} (requested count={count})")
    for i, r in enumerate(recipes):
        print(f"  [{i}] {r.get('heading', 'N/A')}")

    # ============ STEP 1: Hard programmatic filter for foodType and disliked ============
    food_type_lower = food_type.lower().strip() if food_type else ""
    filtered_recipes = []

    for item in recipes:
        dish_name = item.get("heading", "")
        ingredients = [i.get("heading", "") for i in item.get("ingredient", [])]

        # Filter by foodType
        if food_type_lower in ["vegetarian", "veg"]:
            if _is_non_veg_recipe(dish_name, ingredients):
                print(f"[FILTERED OUT - non-veg] {dish_name}")
                continue
        elif food_type_lower == "vegan":
            if _is_non_vegan_recipe(dish_name, ingredients):
                print(f"[FILTERED OUT - non-vegan] {dish_name}")
                continue

        # Filter by disliked ingredients
        if disliked and _contains_disliked(dish_name, ingredients, disliked):
            print(f"[FILTERED OUT - disliked] {dish_name}")
            continue

        filtered_recipes.append(item)

    print(f"[FILTER] {len(recipes)} recipes -> {len(filtered_recipes)} after foodType/disliked filter")
    recipes = filtered_recipes

    # ============ STEP 2: OpenAI filter for cuisines and mood ============
    if recipes and (cuisines or mood):
        recipe_summaries = []
        for idx, item in enumerate(recipes):
            ingredients = [i.get("heading", "") for i in item.get("ingredient", [])]
            recipe_summaries.append({
                "index": idx,
                "name": item.get("heading", ""),
                "ingredients": ingredients,
                "parent_name": item.get("parent_name", "")
            })

        filter_prompt = f"""You are an Indian food expert. I have a list of recipes that are already filtered for dietary restrictions. Now I need you to rank and filter them based on cuisine and mood preferences.

User preferences:
- Preferred Cuisines: {', '.join(cuisines) if cuisines else 'any'}
- Mood: {mood if mood else 'any'}

Rules:
1. If cuisines are specified, ONLY keep recipes that belong to those cuisines. For example:
   - "north indian" includes dishes like dal makhani, paneer butter masala, chole, rajma, aloo gobi, paratha, naan dishes, etc.
   - "south indian" includes dishes like dosa, idli, sambar, rasam, appam, uttapam, etc.
   - "chinese/indo-chinese" includes manchurian, fried rice, noodles, etc.
2. If mood is specified, prefer recipes matching that mood:
   - "comfort" = rich, hearty, creamy, indulgent dishes
   - "healthy" = light, nutritious, low-oil dishes
   - "light" = simple, easy-to-digest dishes
3. Be strict with cuisine filtering - if a dish clearly does not belong to the specified cuisine, remove it.

Here are the recipes:
{json.dumps(recipe_summaries, indent=2)}

Return ONLY a JSON array of the indices (from the list above) of recipes that match the cuisine and mood preferences. Example: [0, 2, 5]
If no recipes match, return an empty array: []
Return ONLY the JSON array, no explanation."""

        try:
            sync_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            ai_response = sync_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": filter_prompt}],
                temperature=0
            )
            result_text = ai_response.choices[0].message.content.strip()
            # Clean markdown code blocks if present
            if result_text.startswith("```"):
                result_text = result_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            filtered_indices = json.loads(result_text)
            if isinstance(filtered_indices, list) and len(filtered_indices) > 0:
                recipes = [recipes[i] for i in filtered_indices if i < len(recipes)]
                print(f"[FILTER] OpenAI cuisine/mood filter: {len(filtered_indices)} out of {len(recipe_summaries)} kept")
            else:
                print("[FILTER] OpenAI returned empty or invalid, keeping all recipes after programmatic filter")
        except Exception as e:
            print(f"[FILTER] OpenAI filtering error: {e}, keeping all recipes after programmatic filter")

    parent_names = [item.get("parent_name") for item in recipes if item.get("parent_name")]

    # Fetch YouTube URLs
    dish_names = [item.get("heading", "") for item in recipes if item.get("heading")]
    yt_urls_map = fetch_youtube_urls_from_db(dish_names)
    print("YouTube URLs fetched from DB:", yt_urls_map)

    missing_dishes = [name for name in dish_names if not yt_urls_map.get(name)]

    yt_service = None
    if missing_dishes:
        print(f"Falling back to YouTubeService for {len(missing_dishes)} dishes: {missing_dishes}")
        try:
            yt_service = YouTubeService()
        except ValueError as e:
            print(f"YouTubeService error: {e}")

    for item in recipes:
        dish_name = item.get("heading", "")
        urls = yt_urls_map.get(dish_name, [])

        if urls:
            item["similar_youtube_videos"] = [{"video_url": url} for url in urls]
            item["scraped_youtube_link"] = urls[0]
        else:
            similar_videos = []
            if yt_service and dish_name:
                try:
                    similar_videos = yt_service.search_recipe_videos(
                        recipe_name=dish_name,
                        max_results=3
                    )
                except Exception as e:
                    print(f"Error fetching YouTube videos for {dish_name}: {e}")

            item["similar_youtube_videos"] = similar_videos
            item["scraped_youtube_link"] = similar_videos[0]["video_url"] if similar_videos else ""

    return parent_names, recipes


async def find_recipe_using_query(user_query):
    """
    Finds recipes based on natural language query using GPT-4o-mini for better processing
    """
    print(f"Processing query: '{user_query}'")
    
    # Use GPT to extract dish name
    processed_query = await extract_dish_name_with_gpt(user_query)
    print(f"Original query: '{user_query}' -> GPT extracted: '{processed_query}'")
    
    # Generate embedding for the processed query
    try:
        user_vector = await asyncio.to_thread(embeddings.embed_query, processed_query)
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None

    # Query Pinecone for matches
    try:
        result = await asyncio.to_thread(index.query, vector=user_vector, top_k=24, include_metadata=True)

        if not result or not result.get('matches'):
            return None

        # Initialize YouTubeService
        try:
            yt_service = YouTubeService()
        except ValueError as e:
            print(f"YouTubeService error: {e}")
            yt_service = None

        matched_recipes = []
        for match in result['matches']:
            dish_name = match["metadata"]["dish_name"]

            # Fetch related videos from YouTube
            similar_youtube_videos = []
            if yt_service:
                try:
                    similar_youtube_videos = await asyncio.to_thread(
                        yt_service.search_recipe_videos,
                        recipe_name=dish_name,
                        max_results=10
                    )
                except Exception as e:
                    print(f"Error fetching YouTube videos for {dish_name}: {e}")
                    similar_youtube_videos = []
            
            # Clean up the recipe URL
            recipe_url = match["metadata"]["recipe_url"]
            if "/recipes/" in recipe_url:
                base_url = recipe_url.split("/recipes/")[0] + "/recipes/"
                recipe_name_with_id = recipe_url.split("/")[-1]
                recipe_url = base_url + recipe_name_with_id
                
            matched_recipes.append({
                "Dish Name": dish_name,
                "YouTube Link": match["metadata"]["recipe_youtube_link"],
                "Ingredients": match["metadata"]["ingredients"],
                "Steps to Cook": match["metadata"]["cooking_steps"],
                "Story": match["metadata"]["story"],
                "Thumbnail Image": match["metadata"]["dish_image"],
                "Recipe URL": recipe_url,
                "Similar YouTube Videos": similar_youtube_videos,
                "Match Score": match.get("score", 0),
                "Extracted Query": processed_query  # Show what was actually searched
            })

        # Sort by relevance score (highest first)
        matched_recipes.sort(key=lambda x: x["Match Score"], reverse=True)
        return matched_recipes

    except Exception as e:
        print(f"Error querying Pinecone: {e}")
        return None
import asyncio
from tools.youtube_service import YouTubeService

async def find_recipe_by_ingredients(user_ingredients, recipe_type=None, preparation_time=None):
    """
    Finds the best matching recipes based on provided ingredients using Pinecone asynchronously,
    and fetches similar YouTube videos from India Food Network channel.
    """
    user_ingredients_text = " ".join(user_ingredients)

    # Generate embedding for the user-provided ingredients asynchronously
    try:
        user_vector = await asyncio.to_thread(embeddings.embed_query, user_ingredients_text)
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None

    # Query Pinecone for matches asynchronously
    try:
        result = await asyncio.to_thread(index.query, vector=user_vector, top_k=24, include_metadata=True)

        if not result or not result.get('matches'):
            return None

        # Initialize YouTubeService (outside the loop for reuse)
        try:
            yt_service = YouTubeService()
        except ValueError as e:
            print(f"YouTubeService error: {e}")
            yt_service = None

        matched_recipes = []
        for match in result['matches']:
            dish_name = match["metadata"]["dish_name"]

            # Fetch related videos from YouTube
            similar_youtube_videos = []
            if yt_service:
                similar_youtube_videos = await asyncio.to_thread(
                    yt_service.search_recipe_videos,
                    recipe_name=dish_name,
                    max_results=10
                )
             # Clean up the recipe URL by removing category paths
            recipe_url = match["metadata"]["recipe_url"]
            if "/recipes/" in recipe_url:
                # Extract base URL and recipe name
                base_url = recipe_url.split("/recipes/")[0] + "/recipes/"
                recipe_name_with_id = recipe_url.split("/")[-1]  # Get the last part (recipe-name-id)
                recipe_url = base_url + recipe_name_with_id
                
            matched_recipes.append({
                "Dish Name": dish_name,
                "YouTube Link": match["metadata"]["recipe_youtube_link"],
                "Ingredients": match["metadata"]["ingredients"],
                "Steps to Cook": match["metadata"]["cooking_steps"],
                "Story": match["metadata"]["story"],
                "Thumbnail Image": match["metadata"]["dish_image"],
                "Recipe URL": recipe_url, #match["metadata"]["recipe_url"],
                "Similar YouTube Videos": similar_youtube_videos  # List of similar videos from same channel
            })

        return matched_recipes

    except Exception as e:
        print(f"Error querying Pinecone: {e}")
        return None


# import asyncio
# async def find_recipe_by_ingredients(user_ingredients):
#     """
#     Finds the best matching recipes based on provided ingredients using Pinecone asynchronously.
#     """
#     # Print the ingredients
#     user_ingredients_text = " ".join(user_ingredients)
#     # print("Ingredients Text:", user_ingredients_text)

#     # Generate embedding for the user-provided ingredients asynchronously
#     try:
#         user_vector = await asyncio.to_thread(embeddings.embed_query, user_ingredients_text)
#     except Exception as e:
#         print(f"Error generating embedding: {e}")
#         return None

#     # Query Pinecone for matches asynchronously (using keyword arguments)
#     try:
#         result = await asyncio.to_thread(index.query, vector=user_vector, top_k=3, include_metadata=True)
#         # print("Query Result:", result)

#         if result and result.get('matches'):
#             matched_recipes = [
#                 {
#                     "Dish Name": match["metadata"]["dish_name"],
#                     "YouTube Link": match["metadata"]["recipe_youtube_link"],
#                     "Ingredients": match["metadata"]["ingredients"],
#                     "Steps to Cook": match["metadata"]["cooking_steps"],
#                     "Story": match["metadata"]["story"],
#                     "Thumbnail Image": match["metadata"]["dish_image"],
#                     "Recipe URL": match["metadata"]["recipe_url"]
#                 }
#                 for match in result['matches']
#             ]
#             return matched_recipes
#         else:
#             return None
#     except Exception as e:
#         print(f"Error querying Pinecone: {e}")
#         return None




# def find_recipe_by_ingredients(user_ingredients):
#     """
#     Finds the best matching recipes based on provided ingredients using Pinecone.
#     """
#     print("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
#     print(user_ingredients)
#     print("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")

#     user_ingredients_text = " ".join(user_ingredients)
#     print(user_ingredients_text)
#     print("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")

#     # user_vector = np.random.rand(1536).tolist()  # Simulating proper embedding
#     user_vector = embeddings.embed_query(user_ingredients_text)

#     # Query Pinecone for all matches
#     result = index.query(vector=user_vector, top_k=3, include_metadata=True)
#     print("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
#     print(result)
#     print("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")

#     if result and result['matches']:
#         matched_recipes = [{
#             "Dish Name": match["metadata"]["dish_name"],
#             "YouTube Link": match["metadata"]["recipe_youtube_link"],
#             "Ingredients": match["metadata"]["ingredients"],
#             "Steps to Cook": match["metadata"]["cooking_steps"],
#             "Story": match["metadata"]["story"],
#             "Thumbnail Image": match["metadata"]["dish_image"],
#             "Recipe URL": match["metadata"]["recipe_url"]
#         } for match in result['matches']]
#         return matched_recipes
#     else:
#         return None
    




def store_all_recipe_data_in_pinecone():
    all_receipes_info = []
    start_index = 0
    count = 20

    while True:
        
        print("Current start index:", start_index)

        # Construct API URL with the custom range
        api_url = f'{os.getenv("IFN_CONTENT_API_URL", "https://indiafoodnetwork.in/dev/h-api/content")}?startIndex={start_index}&count={count}'
        headers = {
            "accept": "*/*",
            "s-id": os.getenv("FETCH_RECIPE_S_ID")
        }
        print(f"Requesting API URL: {api_url}")

        # Make the API request
        response = requests.get(api_url, headers=headers)
        
        # Check if the request was successful
        if response.status_code == 200:
            data = response.json()
            current_page_receipes_info = extract_recipe_data(data)
            if(len(current_page_receipes_info)==0):
                break
            # Break the loop if no articles are returned
            all_receipes_info.append(current_page_receipes_info)
            start_index += count
        else:
            print(f"Failed to fetch articles. Status code: {response.status_code}")
            break

    return all_receipes_info

# async def get_festival_recipes(festivals_data, top_dishes=5, top_recipes=3):
#     """
#     Complete flow: festivals -> LLM dishes -> vector store recipes
    
#     Args:
#         festivals_data (list): List of festival dicts with 'name' key
#         top_dishes (int): Number of dishes to get from LLM per festival
#         top_recipes (int): Number of recipes to get from vector store per dish
    
#     Returns:
#         dict: Festival name mapped to recipes
#     """
#     results = {}
#     print(festivals_data, "Festivals DATA")
    
#     for festival in festivals_data:
#         festival_name = festival.get('name', '')
#         if not festival_name:
#             continue
            
#         try:
#             # Step 1: Get dishes from LLM
#             prompt = f"List {top_dishes} traditional dishes for {festival_name}. Return only dish names, one per line."
            
#             response = await client.chat.completions.create(
#                 model="gpt-4o-mini",
#                 messages=[
#                     {"role": "system", "content": "Return only dish names, one per line."},
#                     {"role": "user", "content": prompt}
#                 ],
#                 max_tokens=100,
#                 temperature=0.3
#             )
            
#             # Parse dishes
#             dishes = [dish.strip().split('.', 1)[-1].strip() for dish in response.choices[0].message.content.strip().split('\n') if dish.strip()]
#             print("DISHES", dishes)
#             # Step 2: Search each dish in vector store
#             festival_recipes = []
#             for dish in dishes[:top_dishes]:
#                 try:
#                     # Generate embedding and search
#                     dish_vector = await asyncio.to_thread(embeddings.embed_query, dish.lower())
#                     result = await asyncio.to_thread(index.query, vector=dish_vector, top_k=top_recipes, include_metadata=True)
                    
#                     # Extract recipes
#                     if result and result.get('matches'):
#                         for match in result['matches']:
#                             if match.get('score', 0) > 0.7:  # Quality threshold
#                                 festival_recipes.append({
#                                     "dish_name": match["metadata"]["dish_name"],
#                                     "ingredients": match["metadata"]["ingredients"],
#                                     "cooking_steps": match["metadata"]["cooking_steps"],
#                                     "recipe_url": match["metadata"]["recipe_url"],
#                                     "thumbnail": match["metadata"].get("dish_image", ""),
#                                     "youtube_link": match["metadata"].get("recipe_youtube_link", ""),
#                                     "suggested_for": dish,
#                                     "score": match.get('score', 0)
#                                 })
#                 except Exception as e:
#                     print(f"Error searching dish '{dish}': {e}")
#                     continue
            
#             # Remove duplicates and sort by score
#             unique_recipes = {recipe["dish_name"]: recipe for recipe in festival_recipes}
#             sorted_recipes = sorted(unique_recipes.values(), key=lambda x: x["score"], reverse=True)
            
#             results[festival_name] = sorted_recipes
            
#         except Exception as e:
#             print(f"Error processing festival '{festival_name}': {e}")
#             results[festival_name] = []
    
#     return results


import asyncio
import aiohttp
import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
import json

def extract_youtube_videos_from_story(story_html: str) -> List[Dict[str, str]]:
    """Extract YouTube video information from the HTML story content"""
    videos = []
    if not story_html:
        return videos
    
    try:
        soup = BeautifulSoup(story_html, 'html.parser')
        
        # Find all iframe elements with YouTube embeds
        iframes = soup.find_all('iframe', src=re.compile(r'youtube\.com/embed/'))
        
        for iframe in iframes:
            src = iframe.get('src', '')
            video_match = re.search(r'youtube\.com/embed/([a-zA-Z0-9_-]+)', src)
            
            if video_match:
                video_id = video_match.group(1)
                
                # Try to find description from surrounding elements
                description = ""
                title = ""
                
                # Look for heading before the iframe
                previous_elements = iframe.find_all_previous(['h2', 'h3', 'h4', 'p'])
                for elem in previous_elements[:3]:  # Check last 3 elements
                    if elem.name in ['h2', 'h3', 'h4'] and elem.get_text(strip=True):
                        title = elem.get_text(strip=True)
                        break
                
                # Look for description in nearby paragraphs
                next_p = iframe.find_next('p')
                if next_p:
                    description = next_p.get_text(strip=True)
                
                videos.append({
                    'video_id': video_id,
                    'youtube_url': f"https://www.youtube.com/watch?v={video_id}",
                    'embed_url': src,
                    'title': title,
                    'description': description
                })
    except Exception as e:
        print(f"Error extracting YouTube videos: {e}")
    
    return videos



async def get_festival_recipes(
    festivals_data: List[Dict],
    session_id: Optional[str] = None
) -> Dict[str, List[Dict]]:

    """
    Fetch festival recipes from India Food Network API.
    First tries with searchType=Tags, falls back to plain search if no recipes found.
    """

    base_url = os.getenv("IFN_NEWS_API_URL", "https://indiafoodnetwork.in/dev/h-api/news")
    headers = {
        "accept": "*/*",
        "s-id": session_id or os.getenv("FETCH_RECIPES_BY_FILTER_S_ID"),
    }

    results = {}

    async with aiohttp.ClientSession() as session:
        for festival in festivals_data:
            festival_name = festival.get("name", "")
            if not festival_name:
                continue

            recipes = []

            async def fetch_recipes(params):
                """Helper to fetch and parse recipes"""
                nonlocal recipes
                async with session.get(base_url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        for item in data.get("news", []):
                            try:
                                youtube_videos = extract_youtube_videos_from_story(item.get("story", ""))

                                tags = item.get("tags", "")
                                if isinstance(tags, str):
                                    tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
                                elif not isinstance(tags, list):
                                    tags = []

                                recipe_data = {
                                    "heading": item.get("heading", ""),
                                    "thumbUrl": item.get("thumbUrl", ""),
                                    "url": item.get("url", ""),
                                    "tags": tags,
                                    "youtube_videos": youtube_videos,
                                    "description": item.get("description", ""),
                                    "keywords": item.get("keywords", ""),
                                }
                                recipes.append(recipe_data) 
                            except Exception as e:
                                print(f"Error processing recipe item: {e}")
                    else:
                        print(f"API request failed for {festival_name}: {response.status}")

            try:
                # 1. Try with searchType=Tags
                await fetch_recipes({"search": festival_name, "searchType": "Tags"})

                # 2. If no recipes found, fallback to plain search
                if not recipes:
                    print(f"No recipes found with tags for {festival_name}, retrying without tags...")
                    await fetch_recipes({"search": festival_name})

                results[festival_name] = recipes
                print(f"Found {len(recipes)} recipes for {festival_name}")

            except Exception as e:
                print(f"Error fetching recipes for {festival_name}: {e}")
                results[festival_name] = []

    return results

# def fetch_recipes_from_db_by_filters(
#     meal_type: str = "",
#     cuisine: str = "",
#     diet: str = "",
#     prep_time_minutes: int = 0,
#     cook_time_minutes: int = 0,
#     servings: int = 0,
# ):
#     """
#     Fetch recipe titles from the 'recipes' table in Postgres (DB_URL) using
#     optional filters. Any filter left empty / 0 is ignored.

#     Returns a dict grouping titles by meal_type:
#         {
#             "breakfast": [...],
#             "lunch":     [...],
#             "snack":     [...],
#             "dinner":    [...],
#             "dessert":   [...],
#         }

#     If `meal_type` is provided (e.g. 'breakfast'), only that bucket is filled.
#     If `meal_type` is empty or 'all', all five buckets are returned.
#     """
#     import psycopg2
#     DB_URL = os.getenv("DB_URL")

#     buckets = ["breakfast", "lunch", "snack", "dinner", "dessert"]
#     grouped = {b: [] for b in buckets}

#     # Build the WHERE clause dynamically so empty filters are ignored.
#     where_clauses = []
#     params = []

#     mt = (meal_type or "").strip().lower()
#     if mt and mt != "all":
#         if mt not in buckets:
#             # Unknown meal_type -> return empty grouped result
#             return grouped
#         where_clauses.append("LOWER(meal_type) = %s")
#         params.append(mt)
#     else:
#         # Only pull rows whose meal_type is one of our known buckets
#         where_clauses.append("LOWER(meal_type) = ANY(%s)")
#         params.append(buckets)

#     if cuisine and cuisine.strip():
#         where_clauses.append("LOWER(cuisine) = %s")
#         params.append(cuisine.strip().lower())

#     if diet and diet.strip():
#         where_clauses.append("LOWER(diet) = %s")
#         params.append(diet.strip().lower())

#     # Treat 0 / None as "no filter" for numeric fields; otherwise use <= so the
#     # user gets recipes that fit *within* their time/servings budget.
#     if prep_time_minutes and int(prep_time_minutes) > 0:
#         where_clauses.append("prep_time_minutes <= %s")
#         params.append(int(prep_time_minutes))

#     if cook_time_minutes and int(cook_time_minutes) > 0:
#         where_clauses.append("cook_time_minutes <= %s")
#         params.append(int(cook_time_minutes))

#     if servings and int(servings) > 0:
#         where_clauses.append("servings >= %s")
#         params.append(int(servings))

#     where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
#     query = f"SELECT title, meal_type FROM recipes WHERE {where_sql};"

#     try:
#         conn = psycopg2.connect(DB_URL)
#         cur = conn.cursor()
#         cur.execute(query, params)
#         rows = cur.fetchall()
#         cur.close()
#         conn.close()
#     except Exception as e:
#         print(f"[DB ERROR] fetch_recipes_from_db_by_filters: {e}")
#         return grouped

#     for title, row_meal_type in rows:
#         if not title:
#             continue
#         key = (row_meal_type or "").strip().lower()
#         if key in grouped:
#             grouped[key].append(title)

#     return grouped

def fetch_recipes_from_db_by_filters(
    meal_type: str = "",
    cuisine: str = "",
    diet: str = "",
    prep_time_minutes: int = 0,
    cook_time_minutes: int = 0,
    servings: int = 0,
):
    """
    Fetch recipes (title + id) from the 'recipes' table in Postgres (DB_URL)
    using optional filters. Any filter left empty / 0 is ignored.

    Returns a dict grouping recipes by meal_type:
        {
            "breakfast": [{"title": "Poha", "id": "uuid-..."}, ...],
            "lunch":     [...],
            "snack":     [...],
            "dinner":    [...],
            "dessert":   [...],
        }
    """
    import psycopg2
    DB_URL = os.getenv("DB_URL")

    buckets = ["breakfast", "lunch", "snack", "dinner", "dessert"]
    grouped = {b: [] for b in buckets}

    where_clauses = []
    params = []

    mt = (meal_type or "").strip().lower()
    if mt and mt != "all":
        if mt not in buckets:
            return grouped
        where_clauses.append("LOWER(meal_type) = %s")
        params.append(mt)
    else:
        where_clauses.append("LOWER(meal_type) = ANY(%s)")
        params.append(buckets)

    if cuisine and cuisine.strip():
        where_clauses.append("LOWER(cuisine) = %s")
        params.append(cuisine.strip().lower())

    if diet and diet.strip():
        where_clauses.append("LOWER(diet) = %s")
        params.append(diet.strip().lower())

    if prep_time_minutes and int(prep_time_minutes) > 0:
        where_clauses.append("prep_time_minutes <= %s")
        params.append(int(prep_time_minutes))

    if cook_time_minutes and int(cook_time_minutes) > 0:
        where_clauses.append("cook_time_minutes <= %s")
        params.append(int(cook_time_minutes))

    if servings and int(servings) > 0:
        where_clauses.append("servings >= %s")
        params.append(int(servings))

    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
    query = f"SELECT id, title, meal_type FROM recipes WHERE {where_sql};"

    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] fetch_recipes_from_db_by_filters: {e}")
        return grouped

    for recipe_id, title, row_meal_type in rows:
        if not title:
            continue
        key = (row_meal_type or "").strip().lower()
        if key in grouped:
            grouped[key].append({"title": title, "id": str(recipe_id)})

    return grouped

def fetch_recipes_flat_from_db(
    meal_type: str = "",
    cuisines: list = None,
    disliked: list = None,
    diet: str = "",
    prep_time_minutes: int = 0,
    cook_time_minutes: int = 0,
    servings: int = 0,
    start_index: int = 0,
    count: int = 10,
):
    """
    Fetch recipes (title + id) from the 'recipes' table in Postgres (DB_URL)
    as a flat list — no meal_type grouping.

    All filters are optional. Pagination via start_index + count.

    Returns:
        list[dict]: [{"title": "...", "id": "..."}, ...]
    """
    import psycopg2
    DB_URL = os.getenv("DB_URL")

    cuisines = cuisines or []
    disliked = disliked or []

    where_clauses = []
    params = []

    mt = (meal_type or "").strip().lower()
    if mt and mt != "all":
        where_clauses.append("LOWER(meal_type) = %s")
        params.append(mt)

    # if diet and diet.strip():
    #     where_clauses.append("LOWER(diet) = %s")
    #     params.append(diet.strip().lower())
    
    if diet and diet.strip():
        d = diet.strip().lower()
        # Normalize extracted value -> DB value
        if d in ("vegetarian", "veg"):
            db_value = "veg"
        elif d in ("non-vegetarian", "non-veg", "nonveg", "non vegetarian"):
            db_value = "non-veg"
        elif d == "vegan":
            db_value = "vegan"
        else:
            db_value = d
        where_clauses.append("LOWER(TRIM(diet)) = %s")
        params.append(db_value)

    # Multiple cuisines -> match ANY of them
    if cuisines:
        cuisines_lower = [c.strip().lower() for c in cuisines if c.strip()]
        if cuisines_lower:
            where_clauses.append("LOWER(cuisine) = ANY(%s)")
            params.append(cuisines_lower)

    # Disliked -> exclude if title contains any of these terms.
    # (If your DB has a separate ingredients column, swap `title` for that.)
    for term in disliked:
        term = term.strip()
        if term:
            where_clauses.append("title NOT ILIKE %s")
            params.append(f"%{term}%")

    if prep_time_minutes and int(prep_time_minutes) > 0:
        where_clauses.append("prep_time_minutes <= %s")
        params.append(int(prep_time_minutes))

    if cook_time_minutes and int(cook_time_minutes) > 0:
        where_clauses.append("cook_time_minutes <= %s")
        params.append(int(cook_time_minutes))

    if servings and int(servings) > 0:
        where_clauses.append("servings >= %s")
        params.append(int(servings))

    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
    query = (
        f"SELECT id, title FROM recipes "
        f"WHERE {where_sql} "
        f"ORDER BY title "
        f"LIMIT %s OFFSET %s;"
    )
    params.extend([int(count), int(start_index)])

    results = []
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] fetch_recipes_flat_from_db: {e}")
        return results

    for recipe_id, title in rows:
        if not title:
            continue
        results.append({"title": title, "id": str(recipe_id)})

    return results

# def fetch_recipes_by_ingredients_match(
#     ingredients: list,
#     match_threshold: float = 0.85,
#     limit: int = 20,
# ):
#     """
#     Find recipes that use the user's ingredients.

#     Match percentage = (matched ingredients) / (user's ingredient count)
#     i.e. "how many of what the user has does this recipe actually use?"

#     Args:
#         ingredients: list of ingredient names the user has.
#         match_threshold: fraction between 0 and 1 (default 0.85 = 85%).
#         limit: max number of recipes to return.

#     Returns:
#         list[dict]: [{"title": "...", "id": "..."}, ...] sorted by best match first.
#     """
#     import psycopg2
#     DB_URL = os.getenv("DB_URL")

#     normalized = list({i.strip().lower() for i in (ingredients or []) if i and i.strip()})
#     if not normalized:
#         print("[DEBUG] No ingredients provided after normalization")
#         return []

#     user_count = len(normalized)

#     # DEBUG: show what we're about to query with
#     print(f"[DEBUG] normalized ingredients: {normalized}")
#     print(f"[DEBUG] user_count: {user_count}")
#     print(f"[DEBUG] threshold: {match_threshold}  (need >= {user_count * match_threshold:.2f} matches)")
#     print(f"[DEBUG] limit: {limit}")

#     query = """
#         SELECT
#             r.id,
#             r.title,
#             COUNT(DISTINCT ri.normalized_name) FILTER (
#                 WHERE ri.normalized_name = ANY(%s)
#             ) AS matched,
#             COUNT(DISTINCT ri.normalized_name) AS total
#         FROM recipes r
#         JOIN recipe_ingredients ri ON ri.recipe_id = r.id
#         GROUP BY r.id, r.title
#         HAVING (
#             COUNT(DISTINCT ri.normalized_name) FILTER (
#                 WHERE ri.normalized_name = ANY(%s)
#             )::float / %s::float
#         ) >= %s
#         ORDER BY matched DESC, total ASC, r.title ASC
#         LIMIT %s;
#     """

#     params = [normalized, normalized, user_count, float(match_threshold), int(limit)]

#     results = []
#     try:
#         conn = psycopg2.connect(DB_URL)
#         cur = conn.cursor()
#         cur.execute(query, params)
#         rows = cur.fetchall()
#         cur.close()
#         conn.close()

#         # DEBUG: show what came back
#         print(f"[DEBUG] rows returned from DB: {len(rows)}")
#         for row in rows[:5]:
#             print(f"[DEBUG]   {row}")
#     except Exception as e:
#         print(f"[DB ERROR] fetch_recipes_by_ingredients_match: {e}")
#         return results

#     for recipe_id, title, matched, total in rows:
#         if not title:
#             continue
#         results.append({"title": title, "id": str(recipe_id)})

#     return results

def fetch_recipes_by_ingredients_match(
    ingredients: list,
    match_threshold: float = 0.85,
    limit: int = 20,
    start_index: int = 0,
):
    """
    Find recipes that use the user's ingredients.

    Match percentage = (matched ingredients) / (user's ingredient count)
    i.e. "how many of what the user has does this recipe actually use?"
    """
    import psycopg2
    DB_URL = os.getenv("DB_URL")

    normalized = list({i.strip().lower() for i in (ingredients or []) if i and i.strip()})
    if not normalized:
        print("[DEBUG] No ingredients provided after normalization")
        return []

    user_count = len(normalized)

    print(f"[DEBUG] normalized ingredients: {normalized}")
    print(f"[DEBUG] user_count: {user_count}")
    print(f"[DEBUG] threshold: {match_threshold}  (need >= {user_count * match_threshold:.2f} matches)")
    print(f"[DEBUG] limit: {limit}, start_index: {start_index}")

    query = """
        SELECT
            r.id,
            r.title,
            COUNT(DISTINCT ri.normalized_name) FILTER (
                WHERE ri.normalized_name = ANY(%s)
            ) AS matched,
            COUNT(DISTINCT ri.normalized_name) AS total
        FROM recipes r
        JOIN recipe_ingredients ri ON ri.recipe_id = r.id
        GROUP BY r.id, r.title
        HAVING (
            COUNT(DISTINCT ri.normalized_name) FILTER (
                WHERE ri.normalized_name = ANY(%s)
            )::float / %s::float
        ) >= %s
        ORDER BY matched DESC, total ASC, r.title ASC
        LIMIT %s OFFSET %s;
    """

    params = [
        normalized, normalized, user_count,
        float(match_threshold),
        int(limit), int(start_index),
    ]

    results = []
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        print(f"[DEBUG] rows returned from DB: {len(rows)}")
        for row in rows[:5]:
            print(f"[DEBUG]   {row}")
    except Exception as e:
        print(f"[DB ERROR] fetch_recipes_by_ingredients_match: {e}")
        return results

    for recipe_id, title, matched, total in rows:
        if not title:
            continue
        results.append({"title": title, "id": str(recipe_id)})

    return results

# def classify_and_extract_recipe_query(user_query: str) -> dict:
#     """
#     Use OpenAI to classify a natural-language recipe request into one of
#     three intents and extract the parameters needed by that function.

#     Returns a dict like:
#         {
#             "intent": "by_ingredients" | "grouped_by_meal" | "flat_filter",
#             "params": { ...keyword args for the chosen function... }
#         }
#     """
#     import json

#     system_prompt = """You are a recipe query parser. Given a user's natural-language
# request, classify it into ONE of three intents and extract relevant parameters.

# INTENTS:

# 1. "by_ingredients" — user lists ingredients they have and wants recipes they can make.
#    Trigger phrases: "I have X, Y, Z", "what can I cook with…", "using these ingredients…"
#    params: {
#      "ingredients": [list of ingredient strings],
#      "match_threshold": float 0.0–1.0 (default 0.5),
#      "limit": int (default 20)
#    }

# 2. "grouped_by_meal" — user wants recipes across multiple meal types at once
#    (a day plan, full meal plan, "show me breakfast + lunch + dinner").
#    Trigger phrases: "full day meal plan", "breakfast and dinner ideas", "plan my meals"
#    params: {
#      "meal_type": "all",
#      "cuisine": str or "",
#      "diet": "vegetarian"|"vegan"|"non-vegetarian"|"",
#      "prep_time_minutes": int (0 = no limit),
#      "cook_time_minutes": int (0 = no limit),
#      "servings": int (0 = no limit)
#    }

# 3. "flat_filter" — user wants a single meal type with optional filters.
#    This is the DEFAULT when the query names just one meal type.
#    Trigger phrases: "quick veg lunch", "italian dinner under 30 min", "healthy snacks"
#    params: {
#      "meal_type": "breakfast"|"lunch"|"snack"|"dinner"|"dessert",
#      "cuisines": [list of strings],
#      "disliked": [list of strings to avoid],
#      "diet": "vegetarian"|"vegan"|"non-vegetarian"|"",
#      "prep_time_minutes": int,
#      "cook_time_minutes": int,
#      "servings": int,
#      "count": int (default 10)
#    }

# RULES:
# - If user lists ingredients they HAVE, always pick "by_ingredients".
# - If query mentions multiple meal types or "day plan", pick "grouped_by_meal".
# - Otherwise pick "flat_filter".
# - Extract times as integers in minutes (e.g. "half an hour" -> 30, "an hour" -> 60).
# - Extract diet from words like "veg"/"vegetarian" -> "vegetarian", "vegan" -> "vegan",
#   "non-veg"/"chicken"/"meat" -> "non-vegetarian". If unclear, leave as "".
# - For disliked: words like "no mushroom", "without brinjal", "I hate okra" -> add to disliked.
# - Respond with ONLY a JSON object, no markdown fences, no prose."""

#     try:
#         response = client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": system_prompt},
#                 {"role": "user", "content": user_query},
#             ],
#             temperature=0,
#             response_format={"type": "json_object"},
#         )
#         raw = response.choices[0].message.content.strip()
#         parsed = json.loads(raw)
#         print(f"[DEBUG][smart_ai] parsed intent: {parsed}")
#         return parsed
#     except Exception as e:
#         print(f"[OPENAI ERROR] classify_and_extract_recipe_query: {e}")
#         # Safe fallback: treat as flat_filter with no constraints
#         return {
#             "intent": "flat_filter",
#             "params": {"meal_type": "", "count": 10},
#         }

def classify_and_extract_recipe_query(user_query: str) -> dict:
    """
    Use OpenAI to classify a natural-language recipe request into one of
    three intents and extract the parameters needed by that function.
    """
    import json
    from openai import OpenAI

    # Create a dedicated sync client so we never collide with any AsyncOpenAI
    # `client` that might exist at module scope.
    sync_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    system_prompt = """You are a recipe query parser. Your ONLY job is to read a user's
natural-language request and output a JSON object classifying it into ONE intent
and extracting EVERY relevant parameter mentioned.

CRITICAL RULES:
- NEVER leave a field empty/0 if the user mentioned it. Extract aggressively.
- Always output valid JSON. No prose, no markdown fences.
- Time phrases -> integer minutes: "45 minutes"->45, "half hour"->30, "an hour"->60, "quick"->20.
  When user says "X minutes to make/cook", put X into BOTH prep_time_minutes AND cook_time_minutes.
- Diet extraction (MANDATORY when mentioned):
    "veg", "vegetarian"            -> "vegetarian"
    "vegan"                        -> "vegan"
    "non-veg", "non veg", "nonveg",
    "chicken", "mutton", "meat",
    "fish", "egg", "seafood"       -> "non-vegetarian"
- Cuisine extraction: "north indian","south indian","italian","mexican","chinese","thai",
  "punjabi","bengali","maharashtrian","gujarati", etc.
- If a meal type is not clearly stated (breakfast/lunch/snack/dinner/dessert),
  leave meal_type as "" but STILL fill diet/cuisine/time.

INTENTS:

1. "by_ingredients"
   Trigger: user says "I have X", "I've got…", "what can I cook with…", "using these ingredients".
   params: {
     "ingredients": [string, ...],
     "match_threshold": float (default 0.5),
     "limit": int (default 20)
   }

2. "grouped_by_meal"
   Trigger: user wants MULTIPLE meal types ("day plan", "meal plan", "breakfast and dinner").
   params: {
     "meal_type": "all",
     "cuisine": string,
     "diet": "vegetarian"|"vegan"|"non-vegetarian"|"",
     "prep_time_minutes": int,
     "cook_time_minutes": int,
     "servings": int
   }

3. "flat_filter"  (DEFAULT — use when query is about one or no meal type)
   params: {
     "meal_type": "breakfast"|"lunch"|"snack"|"dinner"|"dessert"|"",
     "cuisines": [string, ...],
     "disliked": [string, ...],
     "diet": "vegetarian"|"vegan"|"non-vegetarian"|"",
     "prep_time_minutes": int,
     "cook_time_minutes": int,
     "servings": int,
     "count": int (default 10)
   }

EXAMPLES:

User: "I want to make 45 minutes non veg food"
Output: {
  "intent": "flat_filter",
  "params": {
    "meal_type": "",
    "cuisines": [],
    "disliked": [],
    "diet": "non-vegetarian",
    "prep_time_minutes": 45,
    "cook_time_minutes": 45,
    "servings": 0,
    "count": 10
  }
}

User: "quick veg lunch under 30 minutes, no mushroom"
Output: {
  "intent": "flat_filter",
  "params": {
    "meal_type": "lunch",
    "cuisines": [],
    "disliked": ["mushroom"],
    "diet": "vegetarian",
    "prep_time_minutes": 30,
    "cook_time_minutes": 30,
    "servings": 0,
    "count": 10
  }
}

User: "I have tomato, onion, paneer — what can I cook?"
Output: {
  "intent": "by_ingredients",
  "params": {
    "ingredients": ["tomato", "onion", "paneer"],
    "match_threshold": 0.5,
    "limit": 20
  }
}

User: "full day vegetarian meal plan for 4 people"
Output: {
  "intent": "grouped_by_meal",
  "params": {
    "meal_type": "all",
    "cuisine": "",
    "diet": "vegetarian",
    "prep_time_minutes": 0,
    "cook_time_minutes": 0,
    "servings": 4
  }
}

User: "italian dinner"
Output: {
  "intent": "flat_filter",
  "params": {
    "meal_type": "dinner",
    "cuisines": ["italian"],
    "disliked": [],
    "diet": "",
    "prep_time_minutes": 0,
    "cook_time_minutes": 0,
    "servings": 0,
    "count": 10
  }
}"""

    try:
        response = sync_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        parsed = json.loads(raw)
        print(f"[DEBUG][smart_ai] user_query: {user_query}")
        print(f"[DEBUG][smart_ai] parsed intent: {parsed}")
        return parsed
    except Exception as e:
        print(f"[OPENAI ERROR] classify_and_extract_recipe_query: {e}")
        return {
            "intent": "flat_filter",
            "params": {"meal_type": "", "count": 10},
        }
        
# ---------- YouTube recipe classification helpers ----------

ALLOWED_RECIPE_TYPES = {"Breakfast", "Lunch", "Dinner", "Snack", "Drink", "Dessert"}
ALLOWED_RECIPE_CATEGORIES = {"Veg", "Non Veg"}
NUTRITION_KEYS = ("calories_kcal", "protein_g", "carbs_g", "fat_g")

_CLASSIFY_SYSTEM_PROMPT = """You are a nutrition and recipe classification assistant.

For each recipe you will:
1. Classify it into exactly ONE recipe_type of: Breakfast, Lunch, Dinner, Snack, Drink, Dessert.
   - Drinks/smoothies/beverages/juices/lassi/tea/coffee -> Drink
   - Sweets/halwa/cakes/ice cream/kheer/pudding/cookies -> Dessert
   - Chaats/pakoras/finger food/small bites/dips/spreads -> Snack
   - Paratha/poha/upma/idli/dosa/eggs/toast/pancakes/omelette -> Breakfast
   - Curries/rice/heavy meals/biryani/pasta/full meals -> Lunch or Dinner
2. Classify recipe_category as exactly ONE of: "Veg" or "Non Veg".
   - Non Veg if it contains meat, chicken, mutton, beef, pork, fish, prawns, shrimp, crab, lamb, bacon, ham, or egg
   - Veg otherwise (dairy, paneer, cheese, yogurt, honey are Veg)
3. Estimate nutrition PER SERVING as integers:
   - calories_kcal, protein_g, carbs_g, fat_g

Respond with STRICT JSON only, using EXACTLY these six keys and no others:
recipe_type, recipe_category, calories_kcal, protein_g, carbs_g, fat_g

Example output:
{
  "recipe_type": "Snack",
  "recipe_category": "Veg",
  "calories_kcal": 180,
  "protein_g": 5,
  "carbs_g": 15,
  "fat_g": 11
}"""

def _normalize_recipe_type(raw):
    rtype = (raw or "").strip().title()
    if rtype in ALLOWED_RECIPE_TYPES:
        return rtype
    low = rtype.lower()
    if "breakfast" in low: return "Breakfast"
    if "lunch" in low:     return "Lunch"
    if "dinner" in low:    return "Dinner"
    if "snack" in low or "appetizer" in low: return "Snack"
    if "drink" in low or "beverage" in low:  return "Drink"
    if "dessert" in low or "sweet" in low:   return "Dessert"
    return None


def _normalize_recipe_category(raw):
    cat = (raw or "").strip().lower().replace("-", " ").replace("_", " ")
    if cat in ("non veg", "nonveg", "non vegetarian", "non-vegetarian"):
        return "Non Veg"
    if cat in ("veg", "vegetarian", "vegan"):
        return "Veg"
    return None


def _to_int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def classify_recipe_with_openai(recipe: dict) -> dict:
    """
    Enrich a single recipe dict with recipe_type, recipe_category, and
    per-serving nutrition using OpenAI. Returns the enriched fields or None.
    Reads OPENAI_API_KEY from the .env file.
    """
    import json
    from openai import OpenAI
    from dotenv import load_dotenv

    # Make sure .env is loaded (safe to call multiple times)
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[CLASSIFY ERROR] OPENAI_API_KEY not found in environment / .env")
        return None

    sync_client = OpenAI(api_key=api_key)

    name = recipe.get("title") or "Unknown"
    desc = (recipe.get("description") or "")[:800]

    ing_lines = []
    for ing in (recipe.get("ingredients") or []):
        if isinstance(ing, dict):
            h = (ing.get("heading") or "").strip()
            q = (ing.get("quantity") or "").strip()
            if h:
                ing_lines.append(f"- {q + ' ' if q else ''}{h}")
        elif isinstance(ing, str):
            ing_lines.append(f"- {ing}")

    user_prompt = (
        f"Recipe name: {name}\n"
        f"Description: {desc}\n\n"
        f"Ingredients:\n{chr(10).join(ing_lines) if ing_lines else '(none listed)'}\n\n"
        f"Return JSON with recipe_type, recipe_category, and nutrition per serving."
    )

    for attempt in range(3):
        try:
            resp = sync_client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                max_tokens=200,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
            )
            raw_text = resp.choices[0].message.content or "{}"
            print(f"[CLASSIFY attempt {attempt+1}] raw response: {raw_text}")

            data = json.loads(raw_text)
            rtype = _normalize_recipe_type(data.get("recipe_type"))
            rcat  = _normalize_recipe_category(data.get("recipe_category"))
            nutrition = {k: _to_int(data.get(k)) for k in NUTRITION_KEYS}

            # Diagnostic: show which piece (if any) failed
            print(f"[CLASSIFY attempt {attempt+1}] "
                  f"rtype={rtype!r}, rcat={rcat!r}, nutrition={nutrition}")

            if rtype and rcat and all(v is not None for v in nutrition.values()):
                return {"recipe_type": rtype, "recipe_category": rcat, **nutrition}
            else:
                print(f"[CLASSIFY attempt {attempt+1}] validation failed — retrying")
        except Exception as e:
            print(f"[CLASSIFY ERROR attempt {attempt+1}] {e}")

    print(f"[CLASSIFY] gave up after 3 attempts for: {recipe.get('title')}")
    return None

import re

def _slugify(text: str) -> str:
    """Make a URL-safe slug from a title."""
    s = (text or "").lower()
    s = re.sub(r"[^\w\s-]", "", s)         # drop punctuation
    s = re.sub(r"[-\s]+", "-", s).strip("-")
    return s or "untitled"


def parse_steps_from_description(description: str) -> list:
    """
    Best-effort extraction of cooking steps from a YouTube description.
    Looks for a 'Method:' / 'Instructions:' / 'Steps:' header and collects
    lines until another section header appears.

    Returns a list of step strings.
    """
    if not description:
        return []

    lines = description.split("\n")
    steps = []
    in_steps = False
    step_headers = ("method", "instructions", "steps", "recipe", "directions", "preparation")

    for line in lines:
        stripped = line.strip()
        low = stripped.lower().rstrip(":")

        if not in_steps:
            if any(low.startswith(h) for h in step_headers):
                in_steps = True
            continue

        if not stripped:
            continue
        # Stop at next section header
        if stripped.endswith(":") and len(stripped.split()) <= 3:
            break
        # Ignore hashtag-only lines and very short noise
        if stripped.startswith("#") and " " not in stripped:
            break

        # Strip leading "1.", "Step 1:", "-", "•"
        cleaned = re.sub(r"^\s*(step\s*\d+[:.)]?|\d+[.)]|[-•*])\s*", "",
                         stripped, flags=re.IGNORECASE).strip()
        if cleaned:
            steps.append(cleaned)

    return steps


def insert_youtube_recipe_into_db(recipe: dict) -> str:
    """
    Insert one enriched YouTube recipe into recipes + recipe_ingredients +
    recipe_steps. Deduplicates on ifn_recipe_id (= YouTube video ID).

    Returns:
        str: the recipe UUID on success, or None on failure.
    """
    import psycopg2
    from psycopg2.extras import Json

    DB_URL = os.getenv("DB_URL")

    title       = (recipe.get("title") or "").strip()
    description = recipe.get("description") or ""
    url         = recipe.get("url") or recipe.get("youtube_url") or ""
    published   = recipe.get("published_at") or recipe.get("published_date")

    if not title:
        print("[DB INSERT] skipping — empty title")
        return None

    # Pull YouTube video ID out of the URL for dedupe (ifn_recipe_id is UNIQUE)
    m = re.search(r"(?:v=|youtu\.be/)([\w-]{6,})", url)
    video_id = m.group(1) if m else None

    # diet: map classifier's "Veg" / "Non Veg" -> DB values "veg" / "non-veg"
    rcat = (recipe.get("recipe_category") or "").strip().lower()
    diet_value = "non-veg" if rcat in ("non veg", "non-veg", "nonveg") else (
                 "veg"     if rcat == "veg" else None)

    # meal_type: classifier outputs "Breakfast" etc. — keep your DB style (lowercase)
    rtype = (recipe.get("recipe_type") or "").strip().lower() or None
    # map "drink" -> "snack" if you don't have that bucket; otherwise keep as-is
    # (adjust to match what your other endpoints expect)

    slug_base = _slugify(title)
    slug = f"{slug_base}-{video_id}" if video_id else slug_base

    ingredients = recipe.get("ingredients") or []
    steps = parse_steps_from_description(description)

    conn = None
    try:
        conn = psycopg2.connect(DB_URL)
        conn.autocommit = False
        cur = conn.cursor()

        # --- 1. Insert/get the parent recipes row ---
        cur.execute(
            """
            INSERT INTO recipes (
                ifn_recipe_id, slug, title, description,
                diet, meal_type,
                calories_kcal, protein_g, carbs_g, fat_g,
                ifn_url, source, published_at, is_published
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            ON CONFLICT (ifn_recipe_id) DO UPDATE SET
                title         = EXCLUDED.title,
                description   = EXCLUDED.description,
                diet          = EXCLUDED.diet,
                meal_type     = EXCLUDED.meal_type,
                calories_kcal = EXCLUDED.calories_kcal,
                protein_g     = EXCLUDED.protein_g,
                carbs_g       = EXCLUDED.carbs_g,
                fat_g         = EXCLUDED.fat_g,
                ifn_url       = EXCLUDED.ifn_url,
                published_at  = EXCLUDED.published_at,
                updated_at    = NOW()
            RETURNING id;
            """,
            (
                video_id, slug, title, description,
                diet_value, rtype,
                recipe.get("calories_kcal"),
                recipe.get("protein_g"),
                recipe.get("carbs_g"),
                recipe.get("fat_g"),
                url, "youtube", published, True,
            ),
        )
        recipe_id = cur.fetchone()[0]

        # --- 2. Wipe + re-insert ingredients (simplest way to stay in sync) ---
        cur.execute("DELETE FROM recipe_ingredients WHERE recipe_id = %s;", (recipe_id,))

        for idx, ing in enumerate(ingredients):
            if isinstance(ing, dict):
                name = (ing.get("heading") or "").strip()
                qty  = (ing.get("quantity") or "").strip() or None
            elif isinstance(ing, str):
                name, qty = ing.strip(), None
            else:
                continue
            if not name:
                continue

            cur.execute(
                """
                INSERT INTO recipe_ingredients (
                    recipe_id, ingredient_name, normalized_name,
                    quantity, sort_order
                ) VALUES (%s, %s, %s, %s, %s);
                """,
                (recipe_id, name, name.lower(), qty, idx),
            )

        # --- 3. Wipe + re-insert steps ---
        cur.execute("DELETE FROM recipe_steps WHERE recipe_id = %s;", (recipe_id,))

        for i, step_text in enumerate(steps, start=1):
            cur.execute(
                """
                INSERT INTO recipe_steps (recipe_id, step_number, instruction)
                VALUES (%s, %s, %s);
                """,
                (recipe_id, i, step_text),
            )

        conn.commit()
        cur.close()
        print(f"[DB INSERT] OK  '{title}'  id={recipe_id}  "
              f"ings={len(ingredients)} steps={len(steps)}")
        return str(recipe_id)

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[DB INSERT ERROR] '{title}': {e}")
        return None
    finally:
        if conn:
            conn.close()