from IPython.display import Markdown
import textwrap
import os, json, re
import google.generativeai as genai
GOOGLE_API_KEY=os.getenv('GOOGLE_API_KEY')
genai.configure(api_key=GOOGLE_API_KEY)
llm  = genai.GenerativeModel('gemini-1.5-pro-latest')

def generate_food_or_ingredients_in_image(img):
    # response = llm.generate_content([
    #     "Analyze image and provide list of what are main ingredients(Eg:- Colliflower) detected which we can use to cook in JSON format", 
    #     img
    # ])
    response = llm.generate_content([
            "Analyze the image and provide a list of detected food ingredients in JSON format. "
            "The response **MUST** strictly follow this structure:\n"
            '{\n  "ingredients": ["Tomato Puree", "Jam", "Yogurt", "Chocolate Spread", "Pickle", "Milk", "Gochujang", "Butter", "Soy Sauce", "Pickles", "Orange", "Juice"]\n}'
            "\nOnly include actual food ingredients and nothing else."
            "\nEnsure the response contains no additional text, explanations, or formatting issues."
            "\nIf no valid ingredients are detected, return an empty list in the same format."
            "\nExample of an empty response:"
            '\n{\n  "ingredients": []\n}'
            "\nStrictly follow this format with no additional information."
            , img
        ])

    print("isme arha hai")

    if response.candidates:
    # Extract the text from the first candidate
        raw_text = response.candidates[0].content.parts[0].text
        print(raw_text)
        # Parse JSON from the raw text
        try:
            # print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
            # print(raw_text)
            cleaned_text = clean_raw_text(raw_text)
            # print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
            # print(cleaned_text)
            # print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
            parsed_result = json.loads(cleaned_text)
            print(parsed_result)
            
            # print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
            return parsed_result
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON from AI response: {str(e)}")
    else:
        return {"error": "No ingredients detected."}

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