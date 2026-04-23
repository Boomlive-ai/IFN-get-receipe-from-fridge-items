from flask import Flask, request, jsonify
import os, json
import asyncio
from dotenv import load_dotenv
import requests
from tools.detect_items import detect_items
# from tools.tools import fetch_youtube_link, find_recipe_by_ingredients, fetch_recipe_data, store_all_recipe_data_in_pinecone,find_recipe_using_query, get_festival_recipes
from tools.tools import fetch_youtube_link, find_recipe_by_ingredients, fetch_recipe_data, store_all_recipe_data_in_pinecone, find_recipe_using_query, get_festival_recipes, fetch_recipes_by_filter, fetch_recipe_by_filter_for_values, fetch_recipes_from_db_by_filters, fetch_recipes_flat_from_db
from flask_cors import CORS  # Import CORS
from utils import get_festivals  # Import the new festival function
from tools.youtube_service import YouTubeService
# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Allow all origins

app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.environ['OPENAI_API_KEY'] = os.getenv("OPENAI_API_KEY")

def allowed_file(filename):
    """Helper function to check if the file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['jpg', 'jpeg', 'png']

@app.route('/', methods=['GET'])
def home():
    """Default route to check API status and list all available endpoints with detailed documentation."""
    return jsonify({
        "status": "API is running",
        "message": "Welcome to the Object Detection & Recipe Service",
        "available_endpoints": [
            {
                "route": "/detect_items",
                "method": "POST",
                "description": "Upload an image for object detection.",
                "request_body": {
                    "file": "Image file (JPEG/PNG) [Required]"
                },
                "response": {
                    "200": {
                        "example": {
                            "filename": "uploaded_image.jpg",
                            "detected_items": ["apple", "banana", "milk"]
                        }
                    },
                    "400": {
                        "example": {
                            "error": "No file part / Invalid file type"
                        }
                    },
                    "500": {
                        "example": {
                            "error": "Error processing the image"
                        }
                    }
                }
            },
            {
                "route": "/find_recipe_from_image",
                "method": "POST",
                "description": "Upload an image, detect ingredients, and find recipes.",
                "request_body": {
                    "file": "Image file (JPEG/PNG) [Required]"
                },
                "response": {
                    "200": {
                        "example": {
                            "recipes": [
                                {
                                    "name": "Pasta with Tomato Sauce",
                                    "ingredients": ["tomato", "pasta", "cheese"],
                                    "instructions": "Boil pasta, add sauce, mix with cheese."
                                }
                            ]
                        }
                    },
                    "400": {
                        "example": {
                            "error": "No file provided / No ingredients detected"
                        }
                    },
                    "404": {
                        "example": {
                            "error": "No matching recipes found"
                        }
                    },
                    "500": {
                        "example": {
                            "error": "Error processing the image"
                        }
                    }
                }
            },
            {
                "route": "/fetch-recipe-data",
                "method": "GET",
                "description": "Fetch recipe steps from a given source.",
                "request_params": "None",
                "response": {
                    "200": {
                        "example": {
                            "result": "Fetched recipe data"
                        }
                    }
                }
            },
            {
                "route": "/find_recipe",
                "method": "GET",
                "description": "Get recipe suggestions based on user-provided ingredients.",
                "request_params": {
                    "ingredients": "Comma-separated list of ingredients (e.g., ?ingredients=tomato,cheese) [Required]"
                },
                "response": {
                    "200": {
                        "example": {
                            "recipes": [
                                {
                                    "name": "Cheese Omelette",
                                    "ingredients": ["cheese", "eggs"],
                                    "instructions": "Whisk eggs, add cheese, cook in a pan."
                                }
                            ]
                        }
                    },
                    "400": {
                        "example": {
                            "error": "No ingredients provided"
                        }
                    },
                    "404": {
                        "example": {
                            "error": "No matching recipe found"
                        }
                    }
                }
            },
            {
                "route": "/find_recipe_by_query",
                "method": "GET",
                "description": "Find recipes using natural language queries like 'I want to make butter chicken'",
                "request_params": {
                    "query": "Natural language recipe query (e.g., ?query=I want to make butter chicken) [Required]"
                },
                "response": {
                    "200": {
                        "example": {
                            "query": "I want to make butter chicken",
                            "recipes_found": 3,
                            "recipes": [
                                {
                                    "Dish Name": "Butter Chicken",
                                    "YouTube Link": "https://youtube.com/watch?v=example",
                                    "Ingredients": "chicken, butter, tomatoes, cream, spices",
                                    "Steps to Cook": "1. Marinate chicken 2. Cook in butter 3. Add sauce",
                                    "Story": "Traditional Indian dish loved worldwide",
                                    "Thumbnail Image": "https://example.com/image.jpg",
                                    "Recipe URL": "https://example.com/recipe",
                                    "Similar YouTube Videos": ["video1", "video2"],
                                    "Match Score": 0.95
                                }
                            ]
                        }
                    },
                    "400": {
                        "example": {
                            "error": "No query provided"
                        }
                    },
                    "404": {
                        "example": {
                            "error": "No matching recipes found"
                        }
                    }
                }
            },
            {
                "route": "/festivals",
                "method": "GET",
                "description": "Get Indian festivals for flexible date ranges",
                "request_params": {
                    "api_key": "Optional API key for enhanced results",
                    "range": "Range type: 'week' (default), 'month', or 'custom'",
                    "start_date": "Start date for custom range (YYYY-MM-DD format)",
                    "end_date": "End date for custom range (YYYY-MM-DD format)"
                },
                "response": {
                    "200": {
                        "example": {
                            "range_type": "week",
                            "range_description": "Current Week",
                            "date_range": "Aug 19-25, 2025",
                            "start_date": "2025-08-19",
                            "end_date": "2025-08-25",
                            "festivals_count": 2,
                            "festivals": [
                                {
                                    "date": "2025-08-20",
                                    "name": "Raksha Bandhan"
                                }
                            ]
                        }
                    },
                    "400": {
                        "example": {
                            "error": "Invalid range parameter / Missing required dates"
                        }
                    },
                    "500": {
                        "example": {
                            "error": "Failed to fetch festivals"
                        }
                    }
                }
            },
            {
                "route": "/festivals/week",
                "method": "GET",
                "description": "Quick access to current week's festivals",
                "request_params": {
                    "api_key": "Optional API key for enhanced results"
                },
                "response": {
                    "200": {
                        "example": {
                            "range_type": "week",
                            "range_description": "Current Week",
                            "festivals_count": 1,
                            "festivals": [
                                {
                                    "date": "2025-08-20",
                                    "name": "Raksha Bandhan"
                                }
                            ]
                        }
                    }
                }
            },
            {
                "route": "/festival-recipes",
                "method": "GET",
                "description": "Get festivals and their traditional recipes with complete recipe data from India Food Network",
                "request_params": {
                    "api_key": "Optional API key for enhanced festival results",
                    "range": "Range type: 'week' (default), 'month', or 'custom'",
                    "start_date": "Start date for custom range (YYYY-MM-DD format)",
                    "end_date": "End date for custom range (YYYY-MM-DD format)"
                },
                "response": {
                    "200": {
                        "example": {
                            "results": [
                                {
                                    "festival": "Baisakhi",
                                    "date": "2025-04-13",
                                    "recipes": [
                                        {
                                            "heading": "Baisakhi Special: Saagwala Mutton",
                                            "thumbUrl": "https://indiafoodnetwork.in/wp-content/uploads/2017/04/Saag-wala-mutton.jpg",
                                            "url": "https://www.indiafoodnetwork.in/recipes/baisakhi-special-saagwala-mutton",
                                            "tags": ["meat", "mutton", "spinach", "Regional New Year", "Baisakhi"],
                                            "youtube_videos": [
                                                {
                                                    "video_id": "fB4XmyDFe7w",
                                                    "youtube_url": "https://www.youtube.com/watch?v=fB4XmyDFe7w",
                                                    "embed_url": "//www.youtube.com/embed/fB4XmyDFe7w",
                                                    "title": "Saagwala mutton",
                                                    "description": "Mutton marinated in spices and curd..."
                                                }
                                            ],
                                            "description": "Baisakhi is almost here, and it's time to celebrate the festival with a rich Punjabi dish...",
                                            "author": "Seema Gadh",
                                            "date_created": "2017-04-12 11:50:40.0",
                                            "main_category": "Cook at Home",
                                            "keywords": "",
                                            "news_id": 683799
                                        }
                                    ]
                                }
                            ]
                        }
                    },
                    "400": {
                        "example": {
                            "error": "Invalid date format / Missing required parameters"
                        }
                    },
                    "500": {
                        "example": {
                            "error": "Failed to fetch festival recipes"
                        }
                    }
                }
            }
        ],
        "usage_examples": [
            {
                "description": "Get current week's festivals with recipes",
                "url": "/festival-recipes"
            },
            {
                "description": "Get current month's festivals with recipes", 
                "url": "/festival-recipes?range=month"
            },
            {
                "description": "Get festivals and recipes for custom date range",
                "url": "/festival-recipes?range=custom&start_date=2025-04-01&end_date=2025-04-30"
            },
            {
                "description": "Get festivals for specific date range",
                "url": "/festivals?range=custom&start_date=2025-04-01&end_date=2025-04-15"
            }
        ]
    }), 200



@app.route('/detect_items', methods=['POST'])
async def upload_image():
    """Async image upload & object detection"""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file and allowed_file(file.filename):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)

        try:
            # Run detect_items asynchronously
            detected_items = await asyncio.to_thread(detect_items, file_path)
            return jsonify({
                "filename": file.filename,
                "detected_items": detected_items,
            }), 200
        except Exception as e:
            return jsonify({"error": f"Failed to process image: {str(e)}"}), 500
    else:
        return jsonify({"error": "Invalid file type. Please upload a valid image file."}), 400

@app.route('/find_recipe_from_image', methods=['POST'])
async def get_recipe_from_image():
    """Async API to detect ingredients & find recipes"""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)

        try:
            # Run detect_items asynchronously
            detected_items = await asyncio.to_thread(detect_items, file_path)

            # Debugging logs
            # print("Type of detected_items:", type(detected_items))
            # print("Contents of detected_items:", detected_items)

            # Parse detected_items if it's a string
            if isinstance(detected_items, str):
                try:
                    detected_items = json.loads(detected_items)
                except json.JSONDecodeError as e:
                    return jsonify({"error": f"Failed to parse JSON from detect_items: {str(e)}"}), 500

            # Ensure detected_items is a dictionary with "ingredients" key
            if not isinstance(detected_items, dict) or "ingredients" not in detected_items:
                return jsonify({"error": "Invalid response structure from detect_items"}), 500


            detected_ingredients = detected_items["ingredients"]
         # Case 1: If detected_ingredients is a list of names
            if isinstance(detected_ingredients, list) and isinstance(detected_ingredients[0], str):
                detected_ingredients = detected_ingredients
            
            # Case 2: If detected_ingredients is a list of dictionaries with 'name'
            elif isinstance(detected_ingredients, list) and isinstance(detected_ingredients[0], dict):
                detected_ingredients=  [ingredient['name'] for ingredient in detected_ingredients if 'name' in ingredient]
            # Extract ingredients

            # print("Detected ingredients:", detected_ingredients)
            # ingredient_names = [ingredient['name'] for ingredient in detected_ingredients]
            # print("Detected ingredients names:", ingredient_names)

            if not detected_ingredients:
                return jsonify({"error": "No ingredients detected"}), 400

            
            # Call find_recipe_by_ingredients asynchronously
            # matched_recipes = await asyncio.to_thread(find_recipe_by_ingredients, detected_ingredients)
            matched_recipes = await find_recipe_by_ingredients(detected_ingredients)

            if matched_recipes:
                return jsonify(matched_recipes), 200
            else:
                return jsonify({"error": "No matching recipes found"}), 404
        except Exception as e:
            return jsonify({"error": f"Failed to process image: {str(e)}"}), 500
    else:
        return jsonify({"error": "Invalid file type. Please upload a valid image file."}), 400

@app.route('/fetch-recipe-data', methods=['GET'])
def fetch_recipe_data_and_store_it_in_pinecone():
    """Fetch recipe steps from a given source"""
    result = fetch_recipe_data()
    return jsonify({"result": result})


@app.route('/find_recipe', methods=['GET'])
async def get_recipe():
    """Get a recipe suggestion based on user input ingredients.
    
    If ingredients, recipe_type, and preparation_time are all provided,
    fetches recipes via fetch_recipes_by_filter and returns the same
    response shape as /recipe_by_api.
    Otherwise falls back to the existing find_recipe_by_ingredients flow.
    """
    user_ingredients = request.args.getlist('ingredients')
    print(user_ingredients)
    recipe_type = request.args.get('recipe_type', '').strip()
    preparation_time = request.args.get('preparation_time', '').strip()

    if not user_ingredients:
        return jsonify({"error": "No ingredients provided"}), 400

    # --- 3-parameter flow ---
    if recipe_type and preparation_time:
        try:
            preparation_time = int(preparation_time)
        except ValueError:
            return jsonify({"error": "preparation_time must be an integer"}), 400

        try:
            parent_names, raw_recipes = fetch_recipes_by_filter(recipe_type, preparation_time)

            if not raw_recipes:
                return jsonify({"error": "No matching recipes found"}), 404

            recipes = []
            for item in raw_recipes:
                recipe_url = f"https://www.indiafoodnetwork.in{item.get('url', '')}"
                ingredients = [i.get("heading", "") for i in item.get("ingredient", [])]
                steps = [
                    s.get("description", "")
                    for s in sorted(item.get("cookingstep", []), key=lambda x: x.get("uid", 0))
                ]
                recipes.append({
                    "Dish Name":       item.get("heading", ""),
                    "parent_name":     item.get("parent_name", ""),
                    "YouTube Link":    item.get("scraped_youtube_link", ""),
                    "Ingredients":     ingredients,
                    "Steps to Cook":   steps,
                    "Story":           item.get("story", ""),
                    "Thumbnail Image": item.get("thumbImage", ""),
                    "Recipe URL":      recipe_url,
                })

            return jsonify({
                "recipe_type":      recipe_type,
                "preparation_time": preparation_time,
                "recipes_found":    len(recipes),
                "parent_names":     parent_names,
                "recipes":          recipes
            }), 200

        except requests.exceptions.HTTPError as e:
            return jsonify({"error": f"Upstream API error: {str(e)}"}), 502
        except Exception as e:
            return jsonify({"error": f"Failed to fetch recipes: {str(e)}"}), 500

    # --- existing ingredients-only flow ---
    print(user_ingredients)
    matched_recipe = await find_recipe_by_ingredients(user_ingredients)

    if matched_recipe:
        return jsonify(matched_recipe), 200
    else:
        return jsonify({"error": "No matching recipe found"}), 404


@app.route('/store_receipe_info', methods=['GET'])
async def store_recipes():
    stored_recipes = store_all_recipe_data_in_pinecone()

    if stored_recipes:
        return jsonify(stored_recipes), 200
    else:
        return jsonify({"error": "No matching recipe found"}), 404
    
@app.route('/find_recipe_by_query', methods=['GET'])
async def get_recipe_by_query():
    """Get recipe suggestions based on natural language query"""
    query = request.args.get('query')
    
    if not query:
        return jsonify({"error": "No query provided"}), 400
    
    print(f"Received query: {query}")
    
    try:
        # Run find_recipe_using_query asynchronously
        matched_recipes = await find_recipe_using_query(query)

        if matched_recipes:
            return jsonify({
                "query": query,
                "recipes_found": len(matched_recipes),
                "recipes": matched_recipes
            }), 200
        else:
            return jsonify({"error": "No matching recipes found"}), 404
            
    except Exception as e:
        return jsonify({"error": f"Failed to process query: {str(e)}"}), 500
    
@app.route('/festivals', methods=['GET'])
def get_festivals_api():
    """Get Indian festivals for current week, current month, or custom date range"""
    api_key = request.args.get('api_key')
    start_date_param = request.args.get('start_date')  # Format: YYYY-MM-DD
    end_date_param = request.args.get('end_date')      # Format: YYYY-MM-DD
    range_type = request.args.get('range', 'week')     # Options: 'week', 'month', 'custom'
    
    try:
        from datetime import datetime, timedelta
        import calendar
        
        today = datetime.now()
        
        # Determine date range based on parameters
        if range_type == 'custom':
            if not start_date_param or not end_date_param:
                return jsonify({
                    "error": "start_date and end_date are required for custom range"
                }), 400
            
            try:
                start_date = datetime.strptime(start_date_param, '%Y-%m-%d')
                end_date = datetime.strptime(end_date_param, '%Y-%m-%d')
                
                if start_date > end_date:
                    return jsonify({"error": "start_date must be before or equal to end_date"}), 400
                    
                date_range_label = f"{start_date.strftime('%b %d')}-{end_date.strftime('%d, %Y')}"
                range_description = "Custom Range"
                
            except ValueError:
                return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
                
        elif range_type == 'month':
            # Current month
            start_date = today.replace(day=1)  # First day of current month
            # Last day of current month
            last_day = calendar.monthrange(today.year, today.month)[1]
            end_date = today.replace(day=last_day)
            
            date_range_label = f"{start_date.strftime('%b %d')}-{end_date.strftime('%d, %Y')}"
            range_description = "Current Month"
            
        elif range_type == 'week':
            # Current week (Monday to Sunday)
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)
            
            date_range_label = f"{start_date.strftime('%b %d')}-{end_date.strftime('%d, %Y')}"
            range_description = "Current Week"
            
        else:
            return jsonify({
                "error": "Invalid range parameter. Use 'week', 'month', or 'custom'"
            }), 400
        
        # Override with custom dates if provided (even for week/month)
        if start_date_param and end_date_param and range_type != 'custom':
            try:
                start_date = datetime.strptime(start_date_param, '%Y-%m-%d')
                end_date = datetime.strptime(end_date_param, '%Y-%m-%d')
                
                if start_date > end_date:
                    return jsonify({"error": "start_date must be before or equal to end_date"}), 400
                    
                date_range_label = f"{start_date.strftime('%b %d')}-{end_date.strftime('%d, %Y')}"
                range_description = f"Custom {range_type.title()}"
                
            except ValueError:
                return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        # Fetch festivals
        festivals = get_festivals(api_key, start_date.date(), end_date.date())
        
        # Prepare response
        response_data = {
            "range_type": range_type,
            "range_description": range_description,
            "date_range": date_range_label,
            "start_date": start_date.strftime('%Y-%m-%d'),
            "end_date": end_date.strftime('%Y-%m-%d'),
            "festivals_count": len(festivals),
            "festivals": festivals
        }
        
        if not festivals:
            response_data["message"] = f"No festivals found in the {range_description.lower()}"
        
        return jsonify(response_data), 200
            
    except Exception as e:
        return jsonify({"error": f"Failed to fetch festivals: {str(e)}"}), 500


# Optional: Add a separate endpoint for quick access to different ranges
@app.route('/festivals/week', methods=['GET'])
def get_current_week_festivals():
    """Get festivals for current week"""
    api_key = request.args.get('api_key')
    request.args = request.args.copy()
    request.args['range'] = 'week'
    return get_festivals_api()

@app.route('/festival-recipes', methods=['GET'])
def festival_recipes():
    '''
    GET /festival-recipes?range=week|month|custom&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
    Returns festivals for the specified range and LLM-picked dishes with their recipes.
    '''
    from datetime import datetime, timedelta
    import calendar, asyncio

    range_type = request.args.get('range', 'week')
    start_date_param = request.args.get('start_date')
    end_date_param = request.args.get('end_date')

    today = datetime.now()

    # Determine the date range
    if range_type == 'custom' and start_date_param and end_date_param:
        start_date = datetime.strptime(start_date_param, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_param, "%Y-%m-%d")
    elif range_type == 'month':
        start_date = today.replace(day=1)
        end_date = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    else:  # default to week
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)

    print(f"[DEBUG] Route: range_type={range_type}, start_date={start_date.date()}, end_date={end_date.date()}")

    # Step 1: Fetch festivals using updated function
    festivals = get_festivals(
        start_date=start_date.date(),
        end_date=end_date.date(),
        range_type=range_type
    )
    print("###################################################################################################")
    print(festivals)
    print("###################################################################################################")

    print(f"[DEBUG] Festivals found: {len(festivals)}")
    print(get_festival_recipes("Eid Recipes"))
    print("###################################################################################################")

    # Step 2: Use your existing function to get recipes
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    festival_recipes = loop.run_until_complete(get_festival_recipes(festivals))
    loop.close()

    # print(f"[DEBUG] Recipes fetched: {festival_recipes}")

    # Format response
    results = []
    for festival in festivals:
        festival_name = festival["name"]
        recipes = festival_recipes.get(festival_name, [])
        results.append({
            "festival": festival_name,
            "date": festival["date"],
            "recipes": recipes
        })

    return jsonify({"results": results})


@app.route('/recipe_by_api', methods=['GET'])
def recipe_by_api():
    """
    Find recipes filtered by recipe_type and preparation_time via India Food Network API.
    
    Query params:
        recipe_type       - e.g. 'breakfast', 'lunch', 'dinner'  [Required]
        preparation_time  - integer in minutes, e.g. 15           [Required]
    """
    
    recipe_type = request.args.get('recipe_type', '').strip()
    preparation_time = request.args.get('preparation_time', '').strip()
    start_index = request.args.get('startIndex', '0').strip()
    count = request.args.get('count', '10').strip()

    if not recipe_type:
        return jsonify({"error": "recipe_type is required"}), 400
    if not preparation_time:
        return jsonify({"error": "preparation_time is required"}), 400

    try:
        preparation_time = int(preparation_time)
    except ValueError:
        return jsonify({"error": "preparation_time must be an integer"}), 400

    try:
        start_index = int(start_index)
        if start_index < 0:
            return jsonify({"error": "startIndex must be a non-negative integer"}), 400
    except ValueError:
        return jsonify({"error": "startIndex must be an integer"}), 400

    try:
        count = int(count)
        if count < 1:
            return jsonify({"error": "count must be a positive integer"}), 400
    except ValueError:
        return jsonify({"error": "count must be an integer"}), 400

    try:
        parent_names, raw_recipes = fetch_recipes_by_filter(recipe_type, preparation_time, start_index, count)

        if not raw_recipes:
            return jsonify({"error": "No matching recipes found"}), 404

        # Build response in the same shape as find_recipe_by_query
        recipes = []
        for item in raw_recipes:
            recipe_url = f"https://www.indiafoodnetwork.in{item.get('url', '')}"
            ingredients = [i.get("heading", "") for i in item.get("ingredient", [])]
            steps = [
                s.get("description", "")
                for s in sorted(item.get("cookingstep", []), key=lambda x: x.get("uid", 0))
            ]
            recipes.append({
                "Dish Name":       item.get("heading", ""),
                "parent_name":     item.get("parent_name", ""),
                "YouTube Link": item.get("scraped_youtube_link", ""),
                "Ingredients":     ingredients,
                "Steps to Cook":   steps,
                "Story":           item.get("story", ""),
                "Thumbnail Image": item.get("thumbImage", ""),
                "Recipe URL":      recipe_url,
            })

        return jsonify({
            "recipe_type":        recipe_type,
            "preparation_time":   preparation_time,
            "start_index":        start_index,
            "count":              count,
            "recipes_found":      len(recipes),
            "parent_names":       parent_names,
            "recipes":            recipes
        }), 200

    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"Upstream API error: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": f"Failed to fetch recipes: {str(e)}"}), 500


# @app.route('/recipe_by_values', methods=['GET'])
# def recipe_by_values():
#     """
#     Find recipes filtered by user preferences using AI-based filtering.

#     Query params:
#         mealType          - e.g. 'breakfast', 'lunch', 'dinner'       [Required]
#         preparationTime   - integer in minutes, e.g. 30               [Required]
#         foodType          - e.g. 'vegetarian', 'non-vegetarian', 'vegan'  [Optional]
#         mood              - e.g. 'comfort', 'healthy', 'light'        [Optional]
#         cuisines          - comma-separated, e.g. 'north indian,south indian' [Optional]
#         disliked          - comma-separated, e.g. 'mushroom,brinjal'  [Optional]
#         subscription      - 'free' or 'pro'                           [Optional]
#         startIndex        - pagination start index (default 0)        [Optional]
#         count             - number of results (default 10)            [Optional]
#     """

#     meal_type = request.args.get('mealType', '').strip()
#     preparation_time = request.args.get('preparationTime', '').strip()
#     food_type = request.args.get('foodType', '').strip()
#     mood = request.args.get('mood', '').strip()
#     cuisines_raw = request.args.get('cuisines', '').strip()
#     disliked_raw = request.args.get('disliked', '').strip()
#     subscription = request.args.get('subscription', 'free').strip()
#     start_index = request.args.get('startIndex', '0').strip()
#     count = request.args.get('count', '10').strip()

#     if not meal_type:
#         return jsonify({"error": "mealType is required"}), 400
#     if not preparation_time:
#         return jsonify({"error": "preparationTime is required"}), 400

#     try:
#         preparation_time = int(preparation_time)
#     except ValueError:
#         return jsonify({"error": "preparationTime must be an integer"}), 400

#     try:
#         start_index = int(start_index)
#         if start_index < 0:
#             return jsonify({"error": "startIndex must be a non-negative integer"}), 400
#     except ValueError:
#         return jsonify({"error": "startIndex must be an integer"}), 400

#     try:
#         count = int(count)
#         if count < 1:
#             return jsonify({"error": "count must be a positive integer"}), 400
#     except ValueError:
#         return jsonify({"error": "count must be an integer"}), 400

#     cuisines = [c.strip() for c in cuisines_raw.split(',') if c.strip()] if cuisines_raw else []
#     disliked = [d.strip() for d in disliked_raw.split(',') if d.strip()] if disliked_raw else []

#     # Fetch more from API since many will be filtered out (e.g., non-veg removed for vegetarian)
#     fetch_count = count * 10

#     try:
#         parent_names, raw_recipes = fetch_recipe_by_filter_for_values(
#             recipe_type=meal_type,
#             preparation_time=preparation_time,
#             food_type=food_type,
#             cuisines=cuisines,
#             disliked=disliked,
#             mood=mood,
#             start_index=start_index,
#             count=fetch_count
#         )

#         if not raw_recipes:
#             return jsonify({"error": "No matching recipes found for the given preferences"}), 404

#         # Limit final results based on subscription and requested count
#         max_results = count if subscription == 'pro' else min(count, 5)
#         raw_recipes = raw_recipes[:max_results]

#         recipes = []
#         for item in raw_recipes:
#             recipe_url = f"https://www.indiafoodnetwork.in{item.get('url', '')}"
#             ingredients = [i.get("heading", "") for i in item.get("ingredient", [])]
#             steps = [
#                 s.get("description", "")
#                 for s in sorted(item.get("cookingstep", []), key=lambda x: x.get("uid", 0))
#             ]
#             recipes.append({
#                 "Dish Name":       item.get("heading", ""),
#                 "parent_name":     item.get("parent_name", ""),
#                 "YouTube Link":    item.get("scraped_youtube_link", ""),
#                 "Ingredients":     ingredients,
#                 "Steps to Cook":   steps,
#                 "Story":           item.get("story", ""),
#                 "Thumbnail Image": item.get("thumbImage", ""),
#                 "Recipe URL":      recipe_url,
#             })

#         return jsonify({
#             "mealType":           meal_type,
#             "preparationTime":    preparation_time,
#             "foodType":           food_type,
#             "mood":               mood,
#             "cuisines":           cuisines,
#             "disliked":           disliked,
#             "subscription":       subscription,
#             "start_index":        start_index,
#             "count":              len(recipes),
#             "parent_names":       parent_names,
#             "recipes":            recipes
#         }), 200

#     except requests.exceptions.HTTPError as e:
#         return jsonify({"error": f"Upstream API error: {str(e)}"}), 502
#     except Exception as e:
#         return jsonify({"error": f"Failed to fetch recipes: {str(e)}"}), 500

@app.route('/recipe_by_values', methods=['GET'])
def recipe_by_values():
    """
    Find recipes from the local 'recipes' table in Postgres (DB_URL).

    Query params (all optional unless noted):
        mealType         - 'breakfast' | 'lunch' | 'snack' | 'dinner' | 'dessert' [Required]
        preparationTime  - int, max acceptable prep time in minutes              [Required]
        foodType         - e.g. 'vegetarian', 'vegan', 'non-vegetarian'          [Optional]
        cuisines         - comma-separated, e.g. 'north indian,italian'          [Optional]
        disliked         - comma-separated terms to exclude from titles          [Optional]
        cookTime         - int, max acceptable cook time                         [Optional]
        servings         - int, minimum servings required                        [Optional]
        subscription     - 'free' or 'pro' (free capped at 5)                    [Optional]
        startIndex       - pagination offset (default 0)                         [Optional]
        count            - page size (default 10)                                [Optional]
    """
    meal_type        = request.args.get('mealType', '').strip()
    preparation_time = request.args.get('preparationTime', '').strip()
    food_type        = request.args.get('foodType', '').strip()
    cuisines_raw     = request.args.get('cuisines', '').strip()
    disliked_raw     = request.args.get('disliked', '').strip()
    cook_time_raw    = request.args.get('cookTime', '').strip()
    servings_raw     = request.args.get('servings', '').strip()
    subscription     = request.args.get('subscription', 'free').strip()
    start_index      = request.args.get('startIndex', '0').strip()
    count            = request.args.get('count', '10').strip()

    if not meal_type:
        return jsonify({"error": "mealType is required"}), 400
    if not preparation_time:
        return jsonify({"error": "preparationTime is required"}), 400

    def _to_int(value, field, default=0):
        if value in ("", None):
            return default
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"{field} must be an integer")

    try:
        preparation_time  = _to_int(preparation_time, 'preparationTime')
        cook_time_minutes = _to_int(cook_time_raw, 'cookTime')
        servings          = _to_int(servings_raw, 'servings')
        start_index       = _to_int(start_index, 'startIndex', default=0)
        count             = _to_int(count, 'count', default=10)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    if start_index < 0:
        return jsonify({"error": "startIndex must be a non-negative integer"}), 400
    if count < 1:
        return jsonify({"error": "count must be a positive integer"}), 400

    cuisines = [c.strip() for c in cuisines_raw.split(',') if c.strip()] if cuisines_raw else []
    disliked = [d.strip() for d in disliked_raw.split(',') if d.strip()] if disliked_raw else []

    # Cap free-tier results at 5
    effective_count = count if subscription == 'pro' else min(count, 5)

    try:
        recipes = fetch_recipes_flat_from_db(
            meal_type=meal_type,
            cuisines=cuisines,
            disliked=disliked,
            diet=food_type,
            prep_time_minutes=preparation_time,
            cook_time_minutes=cook_time_minutes,
            servings=servings,
            start_index=start_index,
            count=effective_count,
        )
    except Exception as e:
        return jsonify({"error": f"Failed to fetch recipes from DB: {str(e)}"}), 500

    if not recipes:
        return jsonify({"error": "No matching recipes found for the given preferences"}), 404

    return jsonify({
        "mealType":        meal_type,
        "preparationTime": preparation_time,
        "foodType":        food_type,
        "cuisines":        cuisines,
        "disliked":        disliked,
        "subscription":    subscription,
        "start_index":     start_index,
        "count":           len(recipes),
        "recipes":         recipes,
    }), 200


# @app.route('/recipe_for_all', methods=['POST'])
# def recipe_for_all():
#     """
#     Find recipes across one or all meal types using AI-based filtering.

#     Request body (JSON):
#         food_type       - e.g. 'vegetarian', 'non-vegetarian', 'vegan'   [Optional]
#         house_hold_size - integer                                        [Optional]
#         meals           - 'breakfast' | 'lunch' | 'snack' | 'dinner' | 'all' [Required]
#         cooking_time    - integer in minutes (0 = any)                   [Optional]
#         cuisines        - comma-separated string, e.g. 'north indian,south indian' [Optional]
#         disliked        - comma-separated string, e.g. 'mushroom,brinjal' [Optional]
#         cooking_style   - e.g. 'something_new', 'comfort', 'healthy'     [Optional]
#         subscription    - 'free' or 'pro'                                [Optional]

#     Behaviour:
#         - If meals == 'all' -> hits the IFN API for each of
#           [breakfast, lunch, snack, dinner] with count=20 and returns
#           parent_names grouped per meal type.
#         - Otherwise -> hits only for the given meal type with count=20.
#     """

#     try:
#         data = request.get_json(force=True, silent=True) or {}
#     except Exception:
#         return jsonify({"error": "Invalid JSON body"}), 400

#     food_type = str(data.get('food_type', '') or '').strip()
#     meals = str(data.get('meals', '') or '').strip().lower()
#     cooking_time_raw = data.get('cooking_time', 0)
#     cuisines_raw = str(data.get('cuisines', '') or '').strip()
#     disliked_raw = str(data.get('disliked', '') or '').strip()
#     cooking_style = str(data.get('cooking_style', '') or '').strip()
#     subscription = str(data.get('subscription', 'free') or 'free').strip()

#     if not meals:
#         return jsonify({"error": "meals is required"}), 400

#     # cooking_time -> preparation_time (int)
#     try:
#         preparation_time = int(cooking_time_raw) if cooking_time_raw not in ("", None) else 0
#     except (TypeError, ValueError):
#         return jsonify({"error": "cooking_time must be an integer"}), 400

#     # Parse comma-separated lists
#     cuisines = [c.strip() for c in cuisines_raw.split(',') if c.strip()] if cuisines_raw else []
#     disliked = [d.strip() for d in disliked_raw.split(',') if d.strip()] if disliked_raw else []

#     # Map cooking_style -> mood. 'something_new' is not really a mood, so
#     # we treat it as "no specific mood" and let the upstream pick variety.
#     mood = "" if cooking_style.lower() in ("", "something_new") else cooking_style

#     # Decide which meal types to fetch
#     valid_meals = ["breakfast", "lunch", "snack", "dinner"]
#     if meals == "all":
#         meal_types_to_fetch = valid_meals
#     elif meals in valid_meals:
#         meal_types_to_fetch = [meals]
#     else:
#         return jsonify({
#             "error": f"Invalid meals value. Must be one of {valid_meals + ['all']}"
#         }), 400

#     # Per-request fetch count from upstream API
#     fetch_count = 20

#     response_payload = {}

#     for meal_type in meal_types_to_fetch:
#         try:
#             print(f"\n========== Fetching meal_type='{meal_type}' ==========")
#             parent_names, raw_recipes = fetch_recipe_by_filter_for_values(
#                 recipe_type=meal_type,
#                 preparation_time=preparation_time,
#                 food_type=food_type,
#                 cuisines=cuisines,
#                 disliked=disliked,
#                 mood=mood,
#                 start_index=0,
#                 count=fetch_count
#             )
#         except requests.exceptions.HTTPError as e:
#             return jsonify({
#                 "error": f"Upstream API error while fetching {meal_type}: {str(e)}"
#             }), 502
#         except Exception as e:
#             return jsonify({
#                 "error": f"Failed to fetch recipes for {meal_type}: {str(e)}"
#             }), 500

#         # Build the list from raw_recipes. Prefer parent_name; if it's
#         # missing/empty on an item, fall back to heading (the dish name).
#         # For each unique meal name, also attach thumbImage, recipe_url,
#         # and YouTube Link from the same upstream item.
#         seen = set()
#         unique_meals = []
#         for item in (raw_recipes or []):
#             name = (item.get("parent_name") or "").strip()
#             if not name:
#                 name = (item.get("heading") or "").strip()
#             if not name or name in seen:
#                 continue
#             seen.add(name)

#             # Build full recipe URL (upstream returns a relative path)
#             relative_url = (item.get("url") or "").strip()
#             recipe_url = f"https://www.indiafoodnetwork.in{relative_url}" if relative_url else ""

#             unique_meals.append({
#                 "name":         name,
#                 "thumbImage":   item.get("thumbImage", "") or "",
#                 "recipe_url":   recipe_url,
#                 "YouTube Link": item.get("scraped_youtube_link", "") or "",
#             })

#         print(f"[RESULT] {meal_type}: {len(unique_meals)} meals")
#         response_payload[f"{meal_type}_names"] = unique_meals

#     return jsonify({
#         "food_type":       food_type,
#         "house_hold_size": data.get('house_hold_size'),
#         "meals":           meals,
#         "cooking_time":    preparation_time,
#         "cuisines":        cuisines,
#         "disliked":        disliked,
#         "cooking_style":   cooking_style,
#         "subscription":    subscription,
#         **response_payload
#     }), 200


@app.route('/recipe_for_all', methods=['POST'])
def recipe_for_all():
    """
    Find recipe titles from the local `recipes` table in Postgres (DB_URL),
    grouped by meal_type: breakfast, lunch, snack, dinner, dessert.

    Request body (JSON) — all optional unless noted:
        meal_type          - 'breakfast' | 'lunch' | 'snack' | 'dinner' | 'dessert' | 'all'
        cuisine            - e.g. 'north indian', 'italian'
        diet               - e.g. 'vegetarian', 'vegan', 'non-vegetarian'
        prep_time_minutes  - int, max acceptable prep time
        cook_time_minutes  - int, max acceptable cook time
        servings           - int, minimum servings required
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400

    meal_type = str(data.get('meal_type', '') or '').strip().lower()
    cuisine   = str(data.get('cuisine', '') or '').strip()
    diet      = str(data.get('diet', '') or '').strip()

    def _to_int(val, field):
        if val in ("", None):
            return 0
        try:
            return int(val)
        except (TypeError, ValueError):
            raise ValueError(f"{field} must be an integer")

    try:
        prep_time_minutes = _to_int(data.get('prep_time_minutes'), 'prep_time_minutes')
        cook_time_minutes = _to_int(data.get('cook_time_minutes'), 'cook_time_minutes')
        servings          = _to_int(data.get('servings'), 'servings')
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    valid_meals = ["breakfast", "lunch", "snack", "dinner", "dessert"]
    if meal_type and meal_type != "all" and meal_type not in valid_meals:
        return jsonify({
            "error": f"Invalid meal_type. Must be one of {valid_meals + ['all']}"
        }), 400

    try:
        grouped_titles = fetch_recipes_from_db_by_filters(
            meal_type=meal_type,
            cuisine=cuisine,
            diet=diet,
            prep_time_minutes=prep_time_minutes,
            cook_time_minutes=cook_time_minutes,
            servings=servings,
        )
    except Exception as e:
        return jsonify({"error": f"Failed to fetch recipes from DB: {str(e)}"}), 500

    return jsonify({
        "filters": {
            "meal_type":         meal_type or "all",
            "cuisine":           cuisine,
            "diet":              diet,
            "prep_time_minutes": prep_time_minutes,
            "cook_time_minutes": cook_time_minutes,
            "servings":          servings,
        },
        "breakfast": grouped_titles.get("breakfast", []),
        "lunch":     grouped_titles.get("lunch", []),
        "snack":     grouped_titles.get("snack", []),
        "dinner":    grouped_titles.get("dinner", []),
        "dessert":   grouped_titles.get("dessert", []),
    }), 200

@app.route('/youtube/channel-videos', methods=['GET'])
def get_channel_videos():
    try:
        youtube_service = YouTubeService()
        videos = youtube_service.fetch_all_channel_videos_with_details()

        return jsonify({
            "message": "Videos fetched and saved to database",
            "total_videos": len(videos),
            "data": videos
        })

    except Exception as e:
        return jsonify({"error": str(e), "type": type(e).__name__}), 500  # ← show error type too



if __name__ == '__main__':
    import uvicorn
    app.run(debug=True, host="0.0.0.0", port=5000)