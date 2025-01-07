from IPython.display import Markdown
import textwrap
import os, json, re
import google.generativeai as genai
GOOGLE_API_KEY=os.getenv('GOOGLE_API_KEY')
genai.configure(api_key=GOOGLE_API_KEY)
llm  = genai.GenerativeModel('gemini-1.5-pro-latest')

def generate_food_or_ingredients_in_image(img):
    response = llm.generate_content([
        "Analyze image and provide list of what are main ingredients(Eg:- Colliflower) detected which we can use to cook in JSON format", 
        img
    ])

    if response.candidates:
    # Extract the text from the first candidate
        raw_text = response.candidates[0].content.parts[0].text
        
        # Parse JSON from the raw text
        try:
            # print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
            # print(raw_text)
            cleaned_text = clean_raw_text(raw_text)
            # print(cleaned_text)
            # print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
            parsed_result = json.loads(cleaned_text)
            # print(parsed_result)
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