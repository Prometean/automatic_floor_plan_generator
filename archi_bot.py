# Imports
import io
import os
import json
import openai
import logging
from PIL import Image
from flask import Flask, request, jsonify, send_from_directory

# Configure OpenAI API Key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Initialize Flask
app = Flask(__name__)

# Configure logging for debugging
logging.basicConfig(level=logging.DEBUG)

# Load Neufert standards from a JSON file
try:
    with open("neufert_standards.json", "r") as f:
        NEUFERT_STANDARDS = json.load(f)
except FileNotFoundError:
    logging.error("The 'neufert_standards.json' file is missing.")
    NEUFERT_STANDARDS = {}

def validate_with_neufert(design_data):
    """
    Validates architectural designs against Neufert standards.
    """
    results = {"errors": [], "warnings": [], "suggestions": []}

    if not NEUFERT_STANDARDS:
        results["errors"].append("Neufert standards data is unavailable.")
        return results

    # Validate door width
    if "door_width" in design_data:
        door_width = design_data["door_width"]
        standard = NEUFERT_STANDARDS.get("door_dimensions", {})
        if door_width < standard.get("min_width", 0):
            results["errors"].append(f"Door width ({door_width}m) is below the minimum standard ({standard['min_width']}m).")
            results["suggestions"].append(standard.get("recommendation", ""))
        elif door_width > standard.get("max_width", float('inf')):
            results["warnings"].append(f"Door width ({door_width}m) exceeds the maximum standard ({standard['max_width']}m).")

    # Validate room size
    if "room_size" in design_data:
        room_size = design_data["room_size"]
        standard = NEUFERT_STANDARDS.get("room_size", {})
        if room_size < standard.get("min_area", 0):
            results["errors"].append(f"Room size ({room_size}m²) is below the minimum standard ({standard['min_area']}m²).")
            results["suggestions"].append(standard.get("recommendation", ""))

    return results

@app.route('/')
def serve_index():
    """Serves the main HTML file."""
    return send_from_directory('.', 'index.html')

@app.route('/generate', methods=['POST'])
def generate():
    """
    Generates an architectural design with space distribution following Neufert standards.
    """
    data = request.json
    material = data.get('material', 'wooden')
    location = data.get('location', 'Dominican Republic')
    spaces = data.get('spaces', 'kitchen, living room, and bedrooms')
    family_size = data.get('family_size', 'small family')

    try:
        # Generate textual description
        text_prompt = f"Generate a detailed description of a {material} house designed for the {location}. Include spaces like {spaces}, adhering to Neufert standards."
        response_text = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an architectural assistant specialized in Neufert standards."},
                {"role": "user", "content": text_prompt}
            ],
            temperature=0.7,
            max_tokens=750
        ).choices[0].message.content.strip()

        # Generate architectural rendering
        image_prompt = (
            f"A tropical {material} house designed for a {location} with an exterior rendering and a superimposed layout of interior spaces. "
            f"The house features labeled rooms such as {spaces}, with clear tags identifying each area. "
            f"The design adheres to Neufert standards and emphasizes an ergonomic layout for a {family_size}. "
            f"Transparent walls reveal the space distribution, and the layout is overlaid as a schematic plan. "
            f"Include a secondary, smaller floor plan in the corner for reference."
        )

        image_response = openai.Image.create(
            prompt=image_prompt,
            n=2,
            size="1024x1024"
        )
        image_url = image_response['data'][0]['url']

        return jsonify({
            'text': response_text,
            'image_url': image_url
        })

    except openai.error.OpenAIError as e:
        logging.error(f"OpenAI API error: {e}")
        return jsonify({'error': f'OpenAI API error: {str(e)}'}), 500

    except Exception as e:
        logging.error(f"Internal error: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@app.route('/upload', methods=['POST'])
def upload_image():
    """
    Refines an architectural sketch and generates a detailed version with Neufert validation.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No image provided'}), 400

    try:
        # Process uploaded image
        file = request.files['file']
        image = Image.open(file.stream)

        # Ensure image is in PNG format
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        image.save("debug_image.png", format="PNG")

        # Generate mask from the sketch
        gray_image = image.convert("L")  # Convert to grayscale
        threshold = 200  # Adjust this based on sketch contrast
        binary_mask = gray_image.point(lambda x: 0 if x < threshold else 255, 'L')
        binary_mask.save("debug_mask.png", format="PNG")  # Save for debugging

        # Convert image and mask to bytes
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()

        mask_byte_arr = io.BytesIO()
        binary_mask.save(mask_byte_arr, format='PNG')
        mask_byte_arr = mask_byte_arr.getvalue()

        # Refinement prompt
        refine_prompt = (
            "Enhance this architectural sketch to include detailed labels and a clear interior layout "
            "with spaces like bedrooms, kitchen, and living room. Follow Neufert standards for design "
            "and ensure the sketch is realistic, suitable for a tropical climate in the Dominican Republic."
        )

        # Request refinement from OpenAI API
        response = openai.Image.create_edit(
            image=img_byte_arr,
            mask=mask_byte_arr,
            prompt=refine_prompt,
            n=4,
            size="1024x1024"
        )

        # Extract the refined image URL
        refined_image_url = response['data'][0]['url']

        # Validate design against Neufert standards
        design_data = {
            "door_width": 0.8,  # Example
            "room_size": 9.0    # Example
        }
        validation_results = validate_with_neufert(design_data)

        return jsonify({
            'refined_image_url': refined_image_url,
            'neufert_validation': validation_results
        })

    except openai.error.OpenAIError as e:
        logging.error(f"OpenAI API error: {e}")
        return jsonify({'error': f'OpenAI API error: {str(e)}'}), 500

    except Exception as e:
        logging.error(f"Internal error: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(debug=True)
