from flask import Flask, request, jsonify
import os, json
import asyncio
from dotenv import load_dotenv
from tools.detect_items import detect_items
from tools.tools import fetch_youtube_link, find_recipe_by_ingredients, fetch_recipe_data, store_all_recipe_data_in_pinecone,find_recipe_using_query, get_festival_recipes
from flask_cors import CORS  # Import CORS
from utils import get_festivals  # Import the new festival function

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
                "method": ["GET"],
                "description": "Find recipes using natural language queries like 'I want to make butter chicken'",
                "request_params_GET": {
                    "query": "Natural language recipe query (e.g., ?query=I want to make butter chicken) [Required]"
                },
                "request_body_POST": {
                    "query": "Natural language recipe query [Required]",
                    "max_results": "Maximum number of results to return (optional, default: 24)"
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
                "description": "Get Indian festivals happening in the current week",
                "request_params": {
                    "api_key": "Optional API key for enhanced results"
                },
                "response": {
                    "200": {
                        "example": {
                            "current_week": "Aug 19-25, 2025",
                            "festivals_count": 2,
                            "festivals": [
                                {
                                    "date": "2025-08-20",
                                    "name": "Raksha Bandhan"
                                }
                            ]
                        }
                    },
                    "500": {
                        "example": {
                            "error": "Failed to fetch festivals"
                        }
                    }
                }
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
    """Get a recipe suggestion based on user input ingredients"""
    user_ingredients = request.args.getlist('ingredients')
    if not user_ingredients:
        return jsonify({"error": "No ingredients provided"}), 400
    print(user_ingredients)
    # Run find_recipe_by_ingredients asynchronously
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
    """
    GET /festival-recipes?range=week|month|custom&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
    Returns festivals for the specified range and LLM-picked dishes with their recipes.
    """
    from datetime import datetime, timedelta
    import calendar, asyncio

    api_key = request.args.get('api_key')
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

    # Step 1: Fetch festivals
    festivals = get_festivals(api_key, start_date.date(), end_date.date())

    # Step 2: Use your existing function to get recipes
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    festival_recipes = loop.run_until_complete(get_festival_recipes(festivals))
    loop.close()

    # Format response to match your data structure
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



if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
