from flask import Flask, request, jsonify
import os
import asyncio
from dotenv import load_dotenv
from tools.detect_items import detect_items
from tools.tools import fetch_youtube_link, find_recipe_by_ingredients, fetch_recipe_data, store_all_recipe_data_in_pinecone
from flask_cors import CORS  # Import CORS

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
            print(detected_items)
            detected_ingredients = [item["name"] for item in detected_items["ingredients"]]
            print("**********************************************************************************")
            print(detected_ingredients)
            if not detected_ingredients:
                return jsonify({"error": "No ingredients detected"}), 400
            
            # Call find_recipe_by_ingredients asynchronously
            matched_recipes = await asyncio.to_thread(find_recipe_by_ingredients, detected_ingredients)

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
    
    # Run find_recipe_by_ingredients asynchronously
    matched_recipe = await asyncio.to_thread(find_recipe_by_ingredients, user_ingredients)

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
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
