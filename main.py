import os
import random
import time
from datetime import datetime
import requests
from huggingface_hub import InferenceClient
from llama_cpp import Llama
from PIL import Image

# === Ensure 'models/' folder exists before anything ===
os.makedirs("models", exist_ok=True)

# === Config ===
CAPTIONS_MODEL_PATH = "models/nous-hermes-llama2.gguf"
CAPTIONS_MODEL_URL = "https://huggingface.co/TheBloke/Nous-Hermes-Llama2-GGUF/resolve/main/nous-hermes-llama2.Q4_K_M.gguf"

FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")

# === Download caption model if missing ===
if not os.path.exists(CAPTIONS_MODEL_PATH):
    print("[+] Downloading caption model...")
    r = requests.get(CAPTIONS_MODEL_URL, stream=True)
    with open(CAPTIONS_MODEL_PATH, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    print("[+] Model downloaded.")

# === Load Models ===
llm = Llama(model_path=CAPTIONS_MODEL_PATH)
client = InferenceClient("kandinsky-community/kandinsky-2-2")

def generate_caption():
    prompt = "Write a short, mysterious, poetic quote about loneliness, time, dreams or emptiness."
    response = llm(prompt, max_tokens=100)
    base_caption = response["choices"][0]["text"].strip()

    hashtags = [
        "#liminalspace", "#dreamcore", "#weirdcore", "#aesthetic", "#nostalgia",
        "#surreal", "#darkvibes", "#emptyplaces", "#moody", "#philosophy"
    ]
    selected = " ".join(random.sample(hashtags, 4))
    return f"{base_caption}\n\n{selected}"

def generate_image(prompt_text):
    for attempt in range(3):
        try:
            image = client.text_to_image(prompt_text, guidance_scale=4, height=768, width=768)
            image.save("post.jpg")
            return "post.jpg"
        except Exception as e:
            print(f"[!] Image generation failed (attempt {attempt+1}/3): {e}")
            time.sleep(5)
    raise RuntimeError("Image generation failed after 3 attempts.")

def post_to_facebook(image_path, caption):
    print(f"[+] Posting to Facebook: {caption}")
    with open(image_path, 'rb') as img:
        files = {'source': img}
        data = {
            'caption': caption,
            'access_token': FB_ACCESS_TOKEN
        }
        url = f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/photos"
        response = requests.post(url, files=files, data=data)
    print("[+] Response:", response.text)

def run_once():
    prompt = random.choice([
        "an empty liminal hallway at night, flickering lights",
        "a surreal abandoned room lit only by a TV glow",
        "dark misty parking garage, eerie and nostalgic",
        "empty school hallway with blue tint and silence",
        "foggy hotel corridor, trippy and mysterious"
    ])
    caption = generate_caption()
    image_path = generate_image(prompt)
    post_to_facebook(image_path, caption)

def main_loop():
    while True:
        run_once()
        wait_seconds = random.randint(6 * 3600, 18 * 3600)
        print(f"[+] Sleeping for {wait_seconds / 3600:.2f} hours...")
        time.sleep(wait_seconds)

# === Initial test post ===
print("[+] Running test post...")
run_once()

# === Start scheduled loop ===
main_loop()
