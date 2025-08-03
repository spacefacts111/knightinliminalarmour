import os
import sys
import random
import requests
import time
from datetime import datetime, timedelta

# ── DEBUG & ENV VARS ────────────────────────────────────────────────────────
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
if not REPLICATE_API_TOKEN:
    print("❌ REPLICATE_API_TOKEN missing!", file=sys.stderr)
    sys.exit(1)

PAGE_ID     = os.getenv("FB_PAGE_ID")
PAGE_TOKEN  = os.getenv("FB_PAGE_ACCESS_TOKEN")
IMAGES_DIR  = "images"
CAPTIONS_FILE = "captions.txt"
POST_FLAG   = ".posted"

# ── Hashtags ───────────────────────────────────────────────────────────────
HASHTAGS = [
    "liminalspaces","moody","ethereal","dreamscape","nopeople",
    "hdr","cinematic","haunting","emptyworlds","surreal"
]

# ── Cleanup images older than 3 hours ────────────────────────────────────────
def clean_old_images():
    now    = time.time()
    cutoff = now - 3*3600
    for f in os.listdir(IMAGES_DIR):
        path = os.path.join(IMAGES_DIR, f)
        if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
            os.remove(path)
            print(f"[🗑️] Deleted old image: {path}")

# ── Generate / download image via Replicate ────────────────────────────────
def generate_image():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    clean_old_images()

    style = random.choice(["moody", "light"])
    prompt = (
        "A dark, empty corridor under a neon moon, eerie shadows, liminal space, cinematic"
        if style=="moody"
        else
        "A bright, abandoned hallway with soft morning light, ethereal liminal space, high detail"
    )
    print(f"[+] Generating {style} image via Replicate…")

    # 1) fetch latest model version ID
    mdl = requests.get(
        "https://api.replicate.com/v1/models/stability-ai/stable-diffusion",
        headers={"Authorization": f"Token {REPLICATE_API_TOKEN}"}
    ).json()
    version = mdl["latest_version"]["id"]

    # 2) submit prediction
    pred = requests.post(
        "https://api.replicate.com/v1/predictions",
        headers={
            "Authorization": f"Token {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json"
        },
        json={"version": version, "input": {"prompt": prompt}}
    ).json()

    # 3) poll until done
    while pred["status"] not in ("succeeded","failed"):
        time.sleep(1)
        pred = requests.get(
            f"https://api.replicate.com/v1/predictions/{pred['id']}",
            headers={"Authorization": f"Token {REPLICATE_API_TOKEN}"}
        ).json()

    if pred["status"] == "failed":
        raise RuntimeError("Replicate generation failed: " + pred.get("error",""))

    # 4) download the output image
    img_url = pred["output"][0]
    img_data = requests.get(img_url).content
    filename = f"{int(time.time())}.png"
    path = os.path.join(IMAGES_DIR, filename)
    with open(path, "wb") as f:
        f.write(img_data)
    print(f"[✅] Generated image saved: {path}")
    return path

# ── Caption & hashtags ────────────────────────────────────────────────────
def generate_caption():
    if os.path.exists(CAPTIONS_FILE):
        lines = [l.strip() for l in open(CAPTIONS_FILE, encoding="utf-8") if l.strip()]
        return random.choice(lines)
    return "An empty hallway whispers secrets to the wandering soul."

def generate_hashtags(n=5):
    return " ".join("#"+tag for tag in random.sample(HASHTAGS, k=n))

# ── Facebook posting ──────────────────────────────────────────────────────
def post_to_facebook(image_path, caption, hashtags):
    text = f"{caption}\n\n{hashtags}"
    print(f"[+] Posting {image_path}\n    \"{caption}\"\n    {hashtags}")
    with open(image_path, "rb") as img:
        resp = requests.post(
            f"https://graph.facebook.com/{PAGE_ID}/photos",
            files={"source": img},
            data={"caption": text, "access_token": PAGE_TOKEN}
        )
    if resp.ok:
        print("[✅] Posted:", resp.json().get("post_id"))
    else:
        print("[❌] Post failed:", resp.text)

# ── First-run guard & scheduler ────────────────────────────────────────────
def already_posted():
    return os.path.exists(POST_FLAG)
def mark_posted():
    open(POST_FLAG,"w").write("posted")

def run_once():
    img  = generate_image()
    cap  = generate_caption()
    tags = generate_hashtags()
    post_to_facebook(img, cap, tags)

def schedule_posts():
    count = random.randint(1,4)
    print(f"[+] Scheduling {count} post(s) today.")
    for _ in range(count):
        hrs = random.randint(1,24)
        print(f"    ⏰ Sleeping {hrs}h…")
        time.sleep(hrs*3600)
        run_once()

if __name__ == "__main__":
    os.makedirs(IMAGES_DIR, exist_ok=True)

    if not already_posted():
        run_once()
        mark_posted()
    else:
        print("[🛑] Initial post done—skipping duplicate.")

    while True:
        schedule_posts()
