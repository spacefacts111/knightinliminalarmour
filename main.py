import os
import json
import random
import time
import schedule
import hashlib
from playwright.sync_api import sync_playwright

# Environment variables
FB_PAGE_ID         = os.getenv("FB_PAGE_ID")
GEMINI_STORAGE     = "cookies.json"    # your Gemini session (cookies + storage)
FB_STORAGE         = "fb_storage.json" # your Facebook session (cookies + storage)
POSTED_HASHES_FILE = "posted_hashes.json"
IMAGE_DIR          = "generated"

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
        page    = ctx.new_page()
        page.goto("https://gemini.google.com/app/history", timeout=60000)
        page.wait_for_selector("div.attachment-container.generated-images", timeout=60000)

        # Extract all image URLs under the history panel
        srcs = page.evaluate("""
            () => {
                const panel = document.querySelector('div.attachment-container.generated-images');
                if (!panel) return [];
                return Array.from(panel.querySelectorAll('img'))
                    .map(img => img.src)
                    .filter(src => typeof src === 'string' && src.startsWith('https://'));
            }
        """)
        if not srcs:
            raise RuntimeError("No images found in Gemini history")
        latest = srcs[0]

        # Download via authenticated Playwright request
        resp = ctx.request.get(latest)
        resp.raise_for_status()
        filename = os.path.basename(latest.split("?",1)[0]) + ".png"
        path = os.path.join(IMAGE_DIR, filename)
        with open(path, "wb") as f:
            f.write(resp.body())

        browser.close()
        return path, latest

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
        caption = next((t.strip() for t in texts
                        if t.strip() != prompt and 10 < len(t.strip()) < 300), None)
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

        page.wait_for_selector("input[type=file']", timeout=30000)
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
    run_once()
    schedule_posts()
    while True:
        schedule.run_pending()
        time.sleep(30)
