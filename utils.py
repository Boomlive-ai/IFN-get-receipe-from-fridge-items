from IPython.display import Markdown
import textwrap
import os, json, re
import base64
from openai import OpenAI
from PIL import Image
import io

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