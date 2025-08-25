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
from tools.youtube_service import YouTubeService
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=OPENAI_API_KEY)
# Load environment variables from .env file
load_dotenv()
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
    api_url = "https://indiafoodnetwork.in/dev/h-api/content"
    headers = {'accept': '*/*', 's-id': 'zAJPIArp1GpBnYPBoTgkruBzSRfbriwHr3uKdl4sSZwufsbhpg89F1wDqvpD6NoD'}
    
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

async def find_recipe_by_ingredients(user_ingredients):
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
        api_url = f'https://indiafoodnetwork.in/dev/h-api/content?startIndex={start_index}&count={count}'
        headers = {
            "accept": "*/*",
            "s-id": "zAJPIArp1GpBnYPBoTgkruBzSRfbriwHr3uKdl4sSZwufsbhpg89F1wDqvpD6NoD"
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

async def get_festival_recipes(festivals_data, top_dishes=5, top_recipes=3):
    """
    Complete flow: festivals -> LLM dishes -> vector store recipes
    
    Args:
        festivals_data (list): List of festival dicts with 'name' key
        top_dishes (int): Number of dishes to get from LLM per festival
        top_recipes (int): Number of recipes to get from vector store per dish
    
    Returns:
        dict: Festival name mapped to recipes
    """
    results = {}
    print(festivals_data, "Festivals DATA")
    
    for festival in festivals_data:
        festival_name = festival.get('name', '')
        if not festival_name:
            continue
            
        try:
            # Step 1: Get dishes from LLM
            prompt = f"List {top_dishes} traditional dishes for {festival_name}. Return only dish names, one per line."
            
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Return only dish names, one per line."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.3
            )
            
            # Parse dishes
            dishes = [dish.strip().split('.', 1)[-1].strip() for dish in response.choices[0].message.content.strip().split('\n') if dish.strip()]
            print("DISHES", dishes)
            # Step 2: Search each dish in vector store
            festival_recipes = []
            for dish in dishes[:top_dishes]:
                try:
                    # Generate embedding and search
                    dish_vector = await asyncio.to_thread(embeddings.embed_query, dish.lower())
                    result = await asyncio.to_thread(index.query, vector=dish_vector, top_k=top_recipes, include_metadata=True)
                    
                    # Extract recipes
                    if result and result.get('matches'):
                        for match in result['matches']:
                            if match.get('score', 0) > 0.7:  # Quality threshold
                                festival_recipes.append({
                                    "dish_name": match["metadata"]["dish_name"],
                                    "ingredients": match["metadata"]["ingredients"],
                                    "cooking_steps": match["metadata"]["cooking_steps"],
                                    "recipe_url": match["metadata"]["recipe_url"],
                                    "thumbnail": match["metadata"].get("dish_image", ""),
                                    "youtube_link": match["metadata"].get("recipe_youtube_link", ""),
                                    "suggested_for": dish,
                                    "score": match.get('score', 0)
                                })
                except Exception as e:
                    print(f"Error searching dish '{dish}': {e}")
                    continue
            
            # Remove duplicates and sort by score
            unique_recipes = {recipe["dish_name"]: recipe for recipe in festival_recipes}
            sorted_recipes = sorted(unique_recipes.values(), key=lambda x: x["score"], reverse=True)
            
            results[festival_name] = sorted_recipes
            
        except Exception as e:
            print(f"Error processing festival '{festival_name}': {e}")
            results[festival_name] = []
    
    return results
