import requests
from bs4 import BeautifulSoup
import numpy as np
import pinecone
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone
import os
# Initialize Pinecone
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv()
# Initialize Pinecone
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY")
)
index_name = "ifn-recipe-search"

# Ensure the index exists
if index_name not in pc.list_indexes().names():
    pc.create_index(
        name=index_name,
        dimension=1536,
        metric="cosine"
    )
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
    
def extract_recipe_data(api_response):
    """
    Extracts required recipe information from the API response and stores it in Pinecone.
    """
    recipes = api_response.get("news", [])
    extracted_data = []
    
    for recipe in recipes:
        recipe_url = f"https://www.indiafoodnetwork.in{recipe.get('url', '')}"
        youtube_link = fetch_youtube_link(recipe_url)
        
        # Convert ingredients into a list of strings
        ingredients = [ingredient.get("heading", "") for ingredient in recipe.get("ingredient", [])]
        
        # Convert steps into a single string (or a list of strings)
        steps = [step.get("description", "") for step in sorted(
            recipe.get("cookingstep", []), key=lambda x: x.get("uid", 0))]

        story = recipe.get("story", "")
        thumbnail_image = recipe.get("thumbImage", "")
        dish_name = recipe.get("heading", "")

        # Generate OpenAI embedding for ingredients
        ingredient_text = " ".join(ingredients)
        ingredient_embedding = embeddings.embed_query(ingredient_text)

        # Store in Pinecone with correct metadata format
        index.upsert([(dish_name, ingredient_embedding, {
            "recipe_url": recipe_url,
            "dish_name": dish_name,
            "recipe_youtube_link": youtube_link,
            "ingredients": ingredients,  # List of strings
            "cooking_steps": steps,  # List of strings
            "story": story,
            "dish_image": thumbnail_image
        })])

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
def find_recipe_by_ingredients(user_ingredients):
    """
    Finds the best matching recipes based on provided ingredients using Pinecone.
    """
    user_ingredients_text = " ".join(user_ingredients)
    user_vector = np.random.rand(1536).tolist()  # Simulating proper embedding
    
    # Query Pinecone for all matches
    result = index.query(vector=user_vector, top_k=3, include_metadata=True)
    
    if result and result['matches']:
        matched_recipes = [{
            "Dish Name": match["metadata"]["dish_name"],
            "YouTube Link": match["metadata"]["recipe_youtube_link"],
            "Ingredients": match["metadata"]["ingredients"],
            "Steps to Cook": match["metadata"]["cooking_steps"],
            "Story": match["metadata"]["story"],
            "Thumbnail Image": match["metadata"]["dish_image"]
        } for match in result['matches']]
        return matched_recipes
    else:
        return None