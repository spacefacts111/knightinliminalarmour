import os
import sys
import random
import requests
import time
from datetime import datetime, timedelta

# === DEBUG: Check DeepAI key presence ===
DEEPAI_API_KEY = os.getenv("DEEPAI_API_KEY", "")
print(f"[🧪] DEEPAI_API_KEY present? {bool(DEEPAI_API_KEY)} (length={len(DEEPAI_API_KEY)})", file=sys.stderr)
if not DEEPAI_API_KEY:
    raise RuntimeError("❌ DEEPAI_API_KEY is missing or empty! Check your Railway Variables.")

# === ENV VARS ===
PAGE_ID        = os.getenv("FB_PAGE_ID")
PAGE_TOKEN     = os.getenv("FB_PAGE_ACCESS_TOKEN")
IMAGES_DIR     = "images"
CAPTIONS_FILE  = "captions.txt"
POST_FLAG      = ".posted"

# === Hashtag pool ===
HASHTAGS = [
    "liminalspaces","moody","ethereal","dreamscape","nopeople",
    "hdr","cinematic","haunting","emptyworlds","surreal"
]

# === 1) Clean up images older than 3 hours ===
def clean_old_images():
    now    = time.time()
    cutoff = now - 3 * 3600  # 3 hours
    for fname in os.listdir(IMAGES_DIR):
        path = os.path.join(IMAGES_DIR, fname)
        if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
            os.remove(path)
            print(f"[🗑️] Deleted old image: {path}")

# === 2) Generate a new liminal space image via DeepAI ===
def generate_image():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    clean_old_images()

    style = random.choice(["moody", "light"])
    if style == "moody":
        prompt = "A dark, empty corridor under a neon moon, eerie shadows, liminal space, cinematic"
    else:
        prompt = "A bright, abandoned hallway with soft morning light, ethereal liminal space, high detail"

    print(f"[+] Generating image ({style}) via DeepAI…")
    resp = requests.post(
        "https://api.deepai.org/api/text2img",
        data={"text": prompt},
        headers={"api-key": DEEPAI_API_KEY}
    )
    if resp.status_code == 401:
        raise RuntimeError("❌ DeepAI returned 401 Unauthorized: your DEEPAI_API_KEY is likely invalid.")
    resp.raise_for_status()

    img_url = resp.json().get("output_url")
    if not img_url:
        raise RuntimeError(f"DeepAI error: {resp.text}")

    img_data = requests.get(img_url).content
    fname    = f"{int(time.time())}.png"
    path     = os.path.join(IMAGES_DIR, fname)
    with open(path, "wb") as f:
        f.write(img_data)
    print(f"[✅] Image saved: {path}")
    return path

# === 3) Pick a caption from file or fallback ===
def generate_caption():
    if os.path.exists(CAPTIONS_FILE):
        lines = [l.strip() for l in open(CAPTIONS_FILE, encoding="utf-8") if l.strip()]
        return random.choice(lines)
    return "An empty hallway whispers secrets to the wandering soul."

# === 4) Build a hashtag string ===
def generate_hashtags(n=5):
    return " ".join("#"+tag for tag in random.sample(HASHTAGS, k=n))

# === 5) Post to Facebook ===
def post_to_facebook(image_path, caption, hashtags):
    text = f"{caption}\n\n{hashtags}"
    print(f"[+] Posting {image_path}\n    Caption: {caption}\n    Tags: {hashtags}")
    with open(image_path, "rb") as img:
        files = {"source": img}
        data  = {"caption": text, "access_token": PAGE_TOKEN}
        url   = f"https://graph.facebook.com/{PAGE_ID}/photos"
        resp  = requests.post(url, files=files, data=data)
    if resp.ok:
        print("[✅] Posted:", resp.json().get("post_id"))
    else:
        print("[❌] Post failed:", resp.text)

# === 6) First-run guard ===
def already_posted():
    return os.path.exists(POST_FLAG)

def mark_posted():
    with open(POST_FLAG, "w") as f:
        f.write("posted")

# === 7) Single post cycle ===
def run_once():
    img_path = generate_image()
    cap      = generate_caption()
    tags     = generate_hashtags()
    post_to_facebook(img_path, cap, tags)

# === 8) Scheduler ===
def schedule_posts():
    count = random.randint(1,4)
    print(f"[+] Scheduling {count} posts today.")
    for _ in range(count):
        hours = random.randint(1,24)
        print(f"    ⏰ Sleeping {hours}h…")
        time.sleep(hours * 3600)
        run_once()

# === Main entrypoint ===
if __name__ == "__main__":
    os.makedirs(IMAGES_DIR, exist_ok=True)

    if not already_posted():
        run_once()
        mark_posted()
    else:
        print("[🛑] Initial post already made — skipping.")

    while True:
        schedule_posts()
