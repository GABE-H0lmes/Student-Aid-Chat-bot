from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from google import genai
from google.genai import types
from dotenv import load_dotenv
import datetime
import os
import json
import re  # Added for YouTube URL pattern matching

load_dotenv()

# Initialize the Gemini Client
try:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
except Exception as e:
    print(f"CRITICAL: Gemini Client failed to initialize. Check your .env file. Error: {e}")

# Use the exact working path to your manifest
MANIFEST_PATH = r"F:\Coding\vs_proj\chatBot\gemini_chat\datasets and course examples\courseinfo.json"

def load_courses():
    if not os.path.exists(MANIFEST_PATH):
        print(f"ERROR: Manifest file not found at {MANIFEST_PATH}")
        return {"courses": []}
    with open(MANIFEST_PATH, 'r', encoding="utf-8") as file:
        return json.load(file)

def find_course_by_id(course_id, manifest):
    """Finds the course using the exact ID sent by the frontend button click."""
    if not course_id:
        return None
    for course in manifest.get("courses", []):
        if course.get("course_id") == course_id:
            return course
    return None

def find_course_by_keywords(student_prompt, manifest):
    prompt_lower = student_prompt.lower()
    for course in manifest.get("courses", []):
        for keyword in course.get("keywords", []):
            if keyword.lower() in prompt_lower:
                return course
    return None

def get_course_info(course_path):
    if os.path.exists(course_path):
        with open(course_path, 'r', encoding="utf-8") as file:
            return file.read()
    else:
        return f"Error: Course text data file not found at path: {course_path}"
    
def get_current_time():
    return datetime.datetime.now().strftime("%I:%M %p on %A, %B %d, %Y")

#Video ID & Transcript Fetching Helper Functions
def extract_youtube_id(url):
    """Extracts the 11-character video ID from common YouTube URL formats."""
    if not url:
        return None
    pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_youtube_transcript(video_id):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        # 1. Instantiate the API object
        yt_api = YouTubeTranscriptApi()
        
        # 2. Use .fetch() instead of .get_transcript()
        transcript_list = yt_api.fetch(video_id)
        
        # 3. Access text as an attribute (.text) instead of a dictionary key (['text'])
        return " ".join([item.text for item in transcript_list])
        
    except Exception as e:
        return f"[Could not automatically retrieve transcript for this video. Details: {str(e)}]"
# Load the manifest into memory at startup
manifest = load_courses()

app = Flask(__name__)
CORS(app) 

# Setup a folder to save uploaded images
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'images')
os.makedirs(UPLOAD_FOLDER, exist_ok=True) 
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

BASE_SYSTEM_INSTRUCTION = """
You are a precise, patient, and encouraging AI Teaching Assistant.
Your primary goal is to help students learn how to solve problems on their own using the provided dataset.

COURSE GUIDANCE DATA:
{course_guidance}

STRICT RULES:
1. GREETINGS: You may respond to general pleasantries (hi, hello, thanks) politely without needing course data.
2. Rely ONLY on the information provided in the course dataset above.
3. TEACHING WITH EXAMPLES: Whenever you explain a concept, look at the "PRACTICE PROBLEMS & EXAMPLE BANK" for inspiration.
4. TUTOR LENS & SCOPE CONSTRAINT: Act as a patient, guiding tutor. Break down every step.
5. NO CHEATING / PROBLEM MIRRORING (CRITICAL): If a student inputs a specific math problem, create a brand-new, completely different example problem that uses the exact same mathematical concept, but with entirely different numbers. Show the steps for the new problem.
6. Always be encouraging, friendly, and supportive.
7. Try to be as short and clear as possible. Do not use information from the syllabus unless asked.
8. Make sure to use the database's format for examples.
9. USING IMAGES: If the course dataset includes an "Image Reference" URL, and that image is highly relevant to the student's current question, you MUST show it to them! To show an image, insert this exact HTML code into your response, replacing the URL: <br><img src='THE_IMAGE_URL' style='max-width: 100%; border-radius: 8px; margin-top: 10px;'><br>
10. STEP-BY-STEP EXAMPLE FORMATTING: You must present all example problems and equations using this exact layout:
    - Start with a single, short line explaining the intent (e.g., "To simplify the expression:")
    - Place expressions/equations on their own independent lines.
    - Write out action steps using clear numbered headings like: "Step 1: [Action Name]"
    - Under each step heading, write a brief, single-sentence instruction line.
    - If breaking down fractional components or multi-part terms, use clean list items formatted exactly like this:
      * **Numerator:** [Formula/Explanation]
      * **Denominator:** [Formula/Explanation]
    - End with a short concluding phrase confirming the final solution.
"""

@app.route('/add_material', methods=['POST'])
def add_material():
    course_id = request.form.get('course_id')
    new_text = request.form.get('text', '')
    new_video = request.form.get('video', '')
    image_file = request.files.get('image')

    matched_course = find_course_by_id(course_id, manifest)
    if not matched_course:
        return jsonify({'error': 'Could not find that course ID.'}), 404

    file_path = matched_course.get('file_path')
    if not os.path.exists(file_path):
        return jsonify({'error': 'The .txt dataset file could not be found.'}), 404

    # Save the image if one was uploaded
    image_url = ""
    if image_file and image_file.filename != '':
        clean_filename = image_file.filename.replace(" ", "_")
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], clean_filename)
        image_file.save(save_path)
        image_url = f"http://127.0.0.1:5000/static/images/{clean_filename}"

    # Format the new data neatly
    current_time = get_current_time()
    formatted_addition = f"\n\n========================================================================\n"
    formatted_addition += f"NEW MATERIAL ADDED: {current_time}\n"
    formatted_addition += f"========================================================================\n"
    
    # --- UPDATED: Automatically pull transcript if a video link is added ---
    if new_video:
        formatted_addition += f"Video Reference: {new_video}\n"
        video_id = extract_youtube_id(new_video)
        if video_id:
            print(f"Fetching transcript text data for video ID: {video_id}")
            transcript_text = get_youtube_transcript(video_id)
            formatted_addition += f"Video Transcript Content:\n{transcript_text}\n"
        else:
            formatted_addition += f"Video Transcript Content:\n[Could not parse a valid YouTube video ID from the provided link]\n"
            
    if image_url:
        formatted_addition += f"Image Reference: {image_url}\n"
        
    if new_text:
        formatted_addition += f"\n{new_text}\n"

    try:
        with open(file_path, 'a', encoding="utf-8") as file:
            file.write(formatted_addition)
        return jsonify({'success': 'Data, images, and video transcripts successfully appended to dataset!'})
    except Exception as e:
        return jsonify({'error': f"Failed to save to file: {str(e)}"}), 500

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    if not data:
        return jsonify({'error': 'No JSON data received'}), 400
        
    student_query = data.get('message', '')
    course_id = data.get('course', '') 
    
    if not student_query:
        return jsonify({'error': 'No message provided'}), 400

    print(f"Received Query: '{student_query}' for Course ID: '{course_id}'")

    matched_course = find_course_by_id(course_id, manifest)
    
    if not matched_course:
        matched_course = find_course_by_keywords(student_query, manifest)
    
    if matched_course:
        course_info_file = matched_course.get("file_path", "") 
        course_guidance = get_course_info(course_info_file)
    else:
        course_guidance = "No specific course context found for this request."

    formatted_instruction = BASE_SYSTEM_INSTRUCTION.format(course_guidance=course_guidance)
    current_time = get_current_time()
    timestamped_query = f"[Current time: {current_time}]\nStudent: {student_query}"
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=timestamped_query,
            config=types.GenerateContentConfig(
                system_instruction=formatted_instruction,
                temperature=0.3
            )
        )
        return jsonify({'reply': response.text})
        
    except Exception as e:
        print(f"GEMINI API ERROR: {e}")
        return jsonify({'error': f"Gemini API Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)