import os
import json
import re
import time
import schedule
import hashlib
import requests
from playwright.sync_api import sync_playwright

# ─── CONFIG ────────────────────────────────────────────────────
FB_PAGE_ID         = os.getenv("FB_PAGE_ID")
GEMINI_STORAGE     = "cookies.json"    # your saved Gemini session (cookies + localStorage)
FB_STORAGE         = "fb_storage.json" # your saved Facebook session (cookies + localStorage)
POSTED_HASHES_FILE = "posted_hashes.json"
IMAGE_DIR          = "generated"
# ───────────────────────────────────────────────────────────────

# Ensure directories and state file exist
os.makedirs(IMAGE_DIR, exist_ok=True)
if not os.path.exists(POSTED_HASHES_FILE):
    with open(POSTED_HASHES_FILE, "w") as f:
        json.dump([], f)

def load_posted_hashes():
    return set(json.load(open(POSTED_HASHES_FILE)))

def save_posted_hashes(hashes):
    with open(POSTED_HASHES_FILE, "w") as f:
        json.dump(list(hashes), f)

posted = load_posted_hashes()

def fetch_latest_image_from_history():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(storage_state=GEMINI_STORAGE)
        # Inject consent cookie to skip Google's consent page
        ctx.add_cookies([{
            "name":   "CONSENT",
            "value":  "YES+cb",
            "domain": ".google.com",
            "path":   "/",
            "secure": True,
            "sameSite": "Lax"
        }])
        page = ctx.new_page()
        page.goto("https://gemini.google.com/app/history", timeout=120000)
        page.wait_for_load_state("networkidle", timeout=120000)
        html = page.content()
        browser.close()

    # Extract all Google-hosted image URLs from the HTML
    urls = re.findall(r'https://lh3\.googleusercontent\.com/[^"\' >]+', html)
    if not urls:
        raise RuntimeError("No images found in Gemini history")
    latest = urls[0]

    # Download the image with requests, using Playwright cookies for authentication
    # (serialize cookies from ctx to requests.Session if needed)
    # Here we re-open Playwright to use its request context:
    with sync_playwright() as p2:
        browser2 = p2.chromium.launch(headless=True)
        ctx2 = browser2.new_context(storage_state=GEMINI_STORAGE)
        response = ctx2.request.get(latest)
        response.raise_for_status()
        data = response.body()
        browser2.close()

    filename = os.path.basename(latest.split("?",1)[0]) + ".png"
    dst = os.path.join(IMAGE_DIR, filename)
    with open(dst, "wb") as f:
        f.write(data)
    return dst, latest

def generate_caption(src_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(storage_state=GEMINI_STORAGE)
        page    = ctx.new_page()
        page.goto("https://gemini.google.com/app", timeout=60000)
        page.keyboard.press("Escape")
        editor = page.wait_for_selector("div.ql-editor[contenteditable='true']", timeout=60000)
        prompt = f"Write a short poetic mysterious caption for the image at {src_url}"
        editor.click(force=True)
        editor.fill(prompt, force=True)
        editor.press("Enter")
        page.wait_for_timeout(7000)
        texts = page.locator("div").all_text_contents()
        caption = next((t.strip() for t in texts if t.strip()!=prompt and 10 < len(t.strip()) < 300), None)
        browser.close()
        return caption or "A place you’ve seen in dreams."

def post_to_facebook_via_ui(image_path, caption):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(storage_state=FB_STORAGE)
        page    = ctx.new_page()
        page.goto(f"https://www.facebook.com/{FB_PAGE_ID}", timeout=60000)
        page.wait_for_selector("div[aria-label='Create a post']", timeout=60000)
        page.click("div[aria-label='Create a post']", force=True)
        page.wait_for_selector("input[type=file]", timeout=30000)
        page.set_input_files("input[type=file']", image_path)
        page.wait_for_selector("div[aria-label='Write a post']", timeout=30000)
        page.fill("div[aria-label='Write a post']", caption)
        page.click("div[aria-label='Post']", force=True)
        page.wait_for_timeout(5000)
        browser.close()

def run_once():
    try:
        img_path, src_url = fetch_latest_image_from_history()
    except Exception as e:
        print("[ERROR] fetching image:", e)
        return

    url_hash = hashlib.sha256(src_url.encode()).hexdigest()
    if url_hash in posted:
        print("[INFO] Already posted this image, skipping.")
        os.remove(img_path)
        return

    caption = generate_caption(src_url)
    print(f"[INFO] Posting to Facebook with caption: {caption}")
    try:
        post_to_facebook_via_ui(img_path, caption)
    except Exception as e:
        print("[ERROR] Facebook UI post failed:", e)
        os.remove(img_path)
        return

    posted.add(url_hash)
    save_posted_hashes(posted)
    os.remove(img_path)
    print("[INFO] Posted and cleaned up.")

def schedule_posts():
    hours = sorted(random.sample(range(24), random.randint(1,4)))
    for h in hours:
        schedule.every().day.at(f"{h:02}:00").do(run_once)
    print(f"[INFO] Scheduled at hours: {hours}")

if __name__ == "__main__":
    run_once()        # immediate run
    schedule_posts()
    while True:
        schedule.run_pending()
        time.sleep(30)
