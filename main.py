import os
import random
import time
import requests
from datetime import datetime, timedelta
from gpt4all import GPT4All

# CONFIG
PAGE_ID = os.getenv("FB_PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
CAPTIONS_MODEL = "ggml-gpt4all-j.bin"

# Setup: Download model if needed
if not os.path.exists(CAPTIONS_MODEL):
    import urllib.request
    print("Downloading GPT4All model...")
    url = "https://gpt4all.io/models/ggml-gpt4all-j.bin"
    urllib.request.urlretrieve(url, CAPTIONS_MODEL)

# Caption generation
def generate_caption():
    prompt = "Write a mysterious, dark, poetic caption that fits a surreal liminal space photo on Facebook. Avoid hashtags."
    model = GPT4All(CAPTIONS_MODEL)
    with model.chat_session():
        return model.generate(prompt, max_tokens=60).strip()

# Dummy image (Replace with real image gen later)
def generate_image():
    from PIL import Image
    img_path = "liminal_image.jpg"
    img = Image.new("RGB", (1024, 1024), (random.randint(20, 40), random.randint(20, 40), random.randint(20, 40)))
    img.save(img_path)
    return img_path

# Post to Facebook
def post_to_facebook(image_path, caption):
    url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/photos"
    files = {"source": open(image_path, "rb")}
    data = {
        "access_token": PAGE_ACCESS_TOKEN,
        "message": caption
    }
    response = requests.post(url, files=files, data=data)
    print("✅ POSTED:", response.json())

# MAIN BOT LOOP
def run_bot():
    print("🤖 Starting Facebook Liminal Bot")
    caption = generate_caption()
    image = generate_image()
    post_to_facebook(image, caption)

    print("⏳ Now scheduling 1–4 posts every 24h randomly.")
    while True:
        wait = random.randint(4, 16) * 3600  # wait 4 to 16 hours
        print(f"🕒 Waiting {wait//3600}h before next post...")
        time.sleep(wait)

        caption = generate_caption()
        image = generate_image()
        post_to_facebook(image, caption)

if __name__ == "__main__":
    run_bot()
