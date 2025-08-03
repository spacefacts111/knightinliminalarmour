import os
import random
import requests
import time
from datetime import datetime, timedelta

# ---- AI image generation ----
from diffusers import StableDiffusionPipeline
import torch

# === ENV VARS ===
GDRIVE_FILE_ID = os.getenv("GDRIVE_FILE_ID")              # for GPT4All model if you ever switch back
PAGE_ID          = os.getenv("FB_PAGE_ID")
PAGE_TOKEN       = os.getenv("FB_PAGE_ACCESS_TOKEN")
IMAGES_DIR       = "images"
CAPTIONS_FILE    = "captions.txt"
POST_FLAG        = ".posted"

# ---- Hashtag pool ----
HASHTAGS = [
    "liminalspaces","moody","ethereal","dreamscape","nopeople",
    "hdr","cinematic","haunting","emptyworlds","surreal"
]

# === 1) Image pipeline (load once) ===
_pipe = None
def get_sd_pipe():
    global _pipe
    if _pipe is None:
        model_id = "runwayml/stable-diffusion-v1-5"
        device   = "cuda" if torch.cuda.is_available() else "cpu"
        _pipe = StableDiffusionPipeline.from_pretrained(model_id)
        _pipe = _pipe.to(device)
    return _pipe

# === 2) Generate a new liminal image ===
def generate_image():
    # ensure folder
    os.makedirs(IMAGES_DIR, exist_ok=True)

    # choose style
    style = random.choice(["moody", "light"])
    if style == "moody":
        prompt = "A dark, empty corridor under a neon moon, eerie shadows, liminal space, cinematic"
    else:
        prompt = "A bright, abandoned hallway with soft morning light, ethereal liminal space, high detail"

    pipe = get_sd_pipe()
    img   = pipe(prompt).images[0]

    # save with timestamp
    fname = f"{int(time.time())}.png"
    path  = os.path.join(IMAGES_DIR, fname)
    img.save(path)
    print(f"[+] Generated image ({style}): {path}")
    return path

# === 3) Caption from file ===
def generate_caption():
    if os.path.exists(CAPTIONS_FILE):
        lines = [l.strip() for l in open(CAPTIONS_FILE, encoding="utf-8") if l.strip()]
        return random.choice(lines)
    return "An empty hallway whispers secrets to the wandering soul."

# === 4) Build hashtags string ===
def generate_hashtags(n=5):
    return " ".join("#"+tag for tag in random.sample(HASHTAGS, k=n))

# === 5) Post to Facebook ===
def post_to_facebook(image_path, caption, hashtags):
    text = f"{caption}\n\n{hashtags}"
    print(f"[+] Posting image: {image_path}\n    Caption: {caption}\n    Tags: {hashtags}")
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
    open(POST_FLAG, "w").write("posted")

# === 7) One-off post ===
def run_once():
    img  = generate_image()
    cap  = generate_caption()
    tags = generate_hashtags()
    post_to_facebook(img, cap, tags)

# === 8) Scheduler ===
def schedule_posts():
    count = random.randint(1,4)
    print(f"[+] Scheduling {count} posts today.")
    for i in range(count):
        hours = random.randint(1,24)
        print(f"    ⏰ Waiting {hours}h until next post…")
        time.sleep(hours * 3600)
        run_once()

# === Main ===
if __name__ == "__main__":
    os.makedirs(IMAGES_DIR, exist_ok=True)

    # Skip duplicate first-run post on redeploy
    if not already_posted():
        run_once()
        mark_posted()
    else:
        print("[🛑] Initial post already made — skipping.")

    # Enter perpetual scheduler loop
    while True:
        schedule_posts()
