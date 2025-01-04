import PIL.Image
from utils import generate_food_or_ingredients_in_image


def detect_items(image_path):
    img = PIL.Image.open(image_path)
    result = generate_food_or_ingredients_in_image(img)
    return result

