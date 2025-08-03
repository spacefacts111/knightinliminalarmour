import os
import json
import random
import time
import schedule
import hashlib
import requests
from playwright.sync_api import sync_playwright

# ─── CONFIG ────────────────────────────────────────────────────
FB_PAGE_ID         = os.getenv("FB_PAGE_ID")
GEMINI_STORAGE     = "cookies.json"      # your Gemini session state
FB_STORAGE         = "fb_storage.json"   # your Facebook session state
POSTED_HASHES_FILE = "posted_hashes.json"
IMAGE_DIR          = "generated"
# ───────────────────────────────────────────────────────────────

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
        page    = ctx.new_page()
        page.goto("https://gemini.google.com/app/history", timeout=60000)

        # Wait for any Google-hosted image in your history
        selector = "img[src^='https://lh3.googleusercontent.com']"
        print("[DEBUG] Waiting for history images by src pattern...")
        page.wait_for_selector(selector, timeout=60000)
        imgs = page.locator(selector)
        count = imgs.count()
        print(f"[DEBUG] Found {count} history images")
        if count == 0:
            raise RuntimeError("No images found in Gemini history")

        # Take the most recent (first) one
        img = imgs.nth(0)
        src = img.get_attribute("src")
        if not src:
            raise RuntimeError("Could not extract image URL")

        # Download via authenticated Playwright request
        resp = ctx.request.get(src)
        resp.raise_for_status()
        fname = os.path.basename(src.split("?",1)[0]) + ".png"
        dst   = os.path.join(IMAGE_DIR, fname)
        with open(dst, "wb") as f:
            f.write(resp.body())

        browser.close()
        print(f"[DEBUG] Downloaded history image to {dst}")
        return dst, src

def generate_caption_for_image(src_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(storage_state=GEMINI_STORAGE)
        page    = ctx.new_page()
        page.goto("https://gemini.google.com/app", timeout=60000)
        page.keyboard.press("Escape")

        # Wait for the chat editor
        editor = page.wait_for_selector("div.ql-editor[contenteditable='true']", timeout=60000)
        prompt = f"Write a short poetic mysterious caption for the image at {src_url}"
        print(f"[DEBUG] Caption prompt: {prompt}")
        editor.click(force=True)
        editor.fill(prompt, force=True)
        editor.press("Enter")

        page.wait_for_timeout(7000)
        texts = page.locator("div").all_text_contents()
        caption = next(
            (t.strip() for t in texts if t.strip() != prompt and 10 < len(t.strip()) < 300),
            None
        )
        browser.close()
        return caption or "A place you’ve seen in dreams."

def post_to_facebook_via_ui(image_path, caption):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(storage_state=FB_STORAGE)
        page    = ctx.new_page()
        page.goto(f"https://www.facebook.com/{FB_PAGE_ID}", timeout=60000)

        # Open the composer
        page.wait_for_selector("div[aria-label='Create a post']", timeout=60000)
        page.click("div[aria-label='Create a post']", force=True)

        # Upload and caption
        page.wait_for_selector("input[type=file]", timeout=30000)
        page.set_input_files("input[type=file']", image_path)
        page.wait_for_selector("div[aria-label='Write a post']", timeout=30000)
        page.fill("div[aria-label='Write a post']", caption)

        # Post it
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

    caption = generate_caption_for_image(src_url)
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
    run_once()        # run once immediately
    schedule_posts()
    while True:
        schedule.run_pending()
        time.sleep(30)
