import os
import sys
import random
import requests
import time
from datetime import datetime

# ── ENV & DEBUG ─────────────────────────────────────────────────────────────
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
if not REPLICATE_API_TOKEN:
    print("❌ REPLICATE_API_TOKEN missing!", file=sys.stderr)
    sys.exit(1)

PAGE_ID       = os.getenv("FB_PAGE_ID")
PAGE_TOKEN    = os.getenv("FB_PAGE_ACCESS_TOKEN")
IMAGES_DIR    = "images"
CAPTIONS_FILE = "captions.txt"
POST_FLAG     = ".posted"

# ── Hashtag pool ────────────────────────────────────────────────────────────
HASHTAGS = [
    "liminalspaces","moody","ethereal","dreamscape","nopeople",
    "hdr","cinematic","haunting","emptyworlds","surreal"
]

# ── Cleanup images older than 3 hours ─────────────────────────────────────────
def clean_old_images():
    cutoff = time.time() - 3*3600
    for fname in os.listdir(IMAGES_DIR):
        path = os.path.join(IMAGES_DIR, fname)
        if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
            os.remove(path)
            print(f"[🗑️] Deleted old image: {path}")

# ── Generate & download image via Replicate ─────────────────────────────────
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

    # 1) fetch model metadata to get version ID
    mdl = requests.get(
        "https://api.replicate.com/v1/models/stability-ai/stable-diffusion",
        headers={"Authorization": f"Token {REPLICATE_API_TOKEN}"}
    ).json()
    version_id = mdl["latest_version"]["id"]

    # 2) submit prediction with version only
    post_resp = requests.post(
        "https://api.replicate.com/v1/predictions",
        headers={
            "Authorization": f"Token {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "version": version_id,
            "input": {"prompt": prompt}
        }
    )
    if not post_resp.ok:
        raise RuntimeError(f"❌ Replicate POST error {post_resp.status_code}: {post_resp.text}")
    pred = post_resp.json()

    # 3) poll until done
    get_url = pred.get("urls", {}).get("get")
    if not get_url:
        raise RuntimeError(f"❌ Missing poll URL in response: {pred}")
    while True:
        time.sleep(1)
        get_resp = requests.get(get_url, headers={"Authorization": f"Token {REPLICATE_API_TOKEN}"})
        if not get_resp.ok:
            raise RuntimeError(f"❌ Replicate GET error {get_resp.status_code}: {get_resp.text}")
        pred = get_resp.json()
        status = pred.get("status")
        if status in ("succeeded","failed"):
            break

    if status == "failed":
        raise RuntimeError("❌ Replicate generation failed: " + str(pred.get("error")))

    # 4) download the result
    output = pred.get("output")
    if not output or not isinstance(output, list):
        raise RuntimeError(f"❌ No output URL in response: {pred}")
    img_url  = output[0]
    img_data = requests.get(img_url).content
    fname    = f"{int(time.time())}.png"
    path     = os.path.join(IMAGES_DIR, fname)
    with open(path, "wb") as f:
        f.write(img_data)

    print(f"[✅] Generated image saved: {path}")
    return path

# ── Caption & hashtags ─────────────────────────────────────────────────────
def generate_caption():
    if os.path.exists(CAPTIONS_FILE):
        lines = [l.strip() for l in open(CAPTIONS_FILE, encoding="utf-8") if l.strip()]
        return random.choice(lines)
    return "An empty hallway whispers secrets to the wandering soul."

def generate_hashtags(n=5):
    return " ".join("#"+tag for tag in random.sample(HASHTAGS, k=n))

# ── Facebook posting ───────────────────────────────────────────────────────
def post_to_facebook(image_path, caption, hashtags):
    text = f"{caption}\n\n{hashtags}"
    print(f"[+] Posting {image_path}\n    Caption: {caption}\n    {hashtags}")
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

# ── First-run guard & scheduler ─────────────────────────────────────────────
def already_posted():
    return os.path.exists(POST_FLAG)
def mark_posted():
    with open(POST_FLAG, "w") as f:
        f.write("posted")

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

# ── Entrypoint ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(IMAGES_DIR, exist_ok=True)

    if not already_posted():
        run_once()
        mark_posted()
    else:
        print("[🛑] Initial post done—skipping duplicate.")

    while True:
        schedule_posts()
