import os
import random
import requests
import time
from datetime import datetime, timedelta
from gpt4all import GPT4All

GDRIVE_FILE_ID = os.getenv("GDRIVE_FILE_ID")
PAGE_ID = os.getenv("FB_PAGE_ID")
PAGE_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
CAPTIONS_MODEL = "ggml-gpt4all-j.bin"
IMAGES_DIR = "images"
POST_FLAG = ".posted"

# === Download GPT4All model from Google Drive ===
def ensure_model_exists():
    if not os.path.exists(CAPTIONS_MODEL):
        print("[+] Downloading GPT4All model from Google Drive...")
        os.system(f"gdown --id {GDRIVE_FILE_ID} -O {CAPTIONS_MODEL}")
        print("[+] Download complete.")

# === Generate caption using GPT4All ===
def generate_caption():
    ensure_model_exists()
    prompt = "Write a one-sentence mysterious, dark, poetic, relatable thought."
    model = GPT4All(CAPTIONS_MODEL)
    with model.chat_session():
        output = model.generate(prompt, max_tokens=50)
        return output.strip()

# === Create /images folder if missing ===
def ensure_image_folder():
    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR)
        print(f"[⚠️] Created empty /{IMAGES_DIR}/ folder. Please add some images before the next post.")

# === Pick random image from /images/ folder ===
def get_random_image():
    ensure_image_folder()
    files = [f for f in os.listdir(IMAGES_DIR) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    if not files:
        raise FileNotFoundError(f"No images found in /{IMAGES_DIR}/ folder.")
    return os.path.join(IMAGES_DIR, random.choice(files))

# === Upload image to Facebook ===
def post_to_facebook(image_path, caption):
    print(f"[+] Posting image: {image_path}")
    with open(image_path, "rb") as img:
        files = {"source": img}
        data = {"caption": caption, "access_token": PAGE_TOKEN}
        url = f"https://graph.facebook.com/{PAGE_ID}/photos"
        response = requests.post(url, files=files, data=data)
    if response.status_code == 200:
        print("[✅] Post successful:", response.json()["post_id"])
    else:
        print("[❌] Post failed:", response.text)

# === One-time post ===
def run_once():
    caption = generate_caption()
    image = get_random_image()
    post_to_facebook(image, caption)

# === Prevent auto-repost on Railway redeploy ===
def already_posted():
    return os.path.exists(POST_FLAG)

def mark_posted():
    with open(POST_FLAG, "w") as f:
        f.write("posted")

# === Schedule future posts randomly ===
def schedule_posts():
    daily_posts = random.randint(1, 4)
    print(f"[+] Scheduling {daily_posts} post(s) for today.")
    now = datetime.now()
    for i in range(daily_posts):
        hours_later = random.randint(1, 24)
        post_time = now + timedelta(hours=hours_later)
        print(f"    ⏰ Post {i+1} scheduled for {post_time.strftime('%H:%M')}")
        time.sleep((post_time - datetime.now()).total_seconds())
        run_once()

# === Main loop ===
if __name__ == "__main__":
    ensure_image_folder()

    if not already_posted():
        run_once()
        mark_posted()
    else:
        print("[🛑] Initial post already made — skipping first-run duplicate.")

    while True:
        schedule_posts()
