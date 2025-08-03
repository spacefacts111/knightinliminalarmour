import os
import json
import time
import schedule
import hashlib
from playwright.sync_api import sync_playwright

# ─── CONFIG ────────────────────────────────────────────────────
FB_PAGE_ID         = os.getenv("FB_PAGE_ID")
GEMINI_STORAGE     = "cookies.json"    # your Gemini session state
FB_STORAGE         = "fb_storage.json" # your Facebook session state
POSTED_HASHES_FILE = "posted_hashes.json"
PROMPTS_FILE       = "prompts.txt"
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

def random_prompt():
    if os.path.exists(PROMPTS_FILE):
        with open(PROMPTS_FILE) as f:
            lines = [l.strip() for l in f if l.strip()]
            if lines:
                return random.choice(lines)
    return "a liminal dream hallway with red lights and fog"

import random
posted = load_posted_hashes()

def generate_image_and_caption():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=GEMINI_STORAGE)
        page = context.new_page()

        # Intercept image response
        image_data = {"url": None, "body": None}
        def on_response(resp):
            url = resp.url
            if url.startswith("https://lh3.googleusercontent.com"):
                try:
                    image_data["body"] = resp.body()
                    image_data["url"]  = url
                except:
                    pass

        page.on("response", on_response)

        # Prompt Gemini
        page.goto("https://gemini.google.com/app", timeout=60000)
        page.wait_for_selector("div.ql-editor[contenteditable='true']", timeout=60000)
        editor = page.locator("div.ql-editor[contenteditable='true']")
        prompt = random_prompt()
        editor.click(force=True)
        editor.fill(prompt, force=True)
        editor.press("Enter")

        # Wait for the image response
        page.wait_for_timeout(8000)
        if not image_data["body"]:
            raise RuntimeError("No image response intercepted")

        # Save image
        url = image_data["url"]
        filename = os.path.basename(url.split("?",1)[0]) + ".png"
        path = os.path.join(IMAGE_DIR, filename)
        with open(path, "wb") as f:
            f.write(image_data["body"])

        # Generate caption
        editor.click(force=True)
        editor.fill("Write a short poetic mysterious caption for that image.", force=True)
        editor.press("Enter")
        page.wait_for_timeout(7000)
        texts = page.locator("div").all_text_contents()
        caption = next((t.strip() for t in reversed(texts)
                        if 10 < len(t.strip()) < 300), None) \
                  or "A place you’ve seen in dreams."

        browser.close()
        return path, caption

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
        img_path, caption = generate_image_and_caption()
    except Exception as e:
        print("[ERROR] image generation:", e)
        return

    h = hashlib.sha256(open(img_path, "rb").read()).hexdigest()
    if h in posted:
        os.remove(img_path)
        return

    try:
        post_to_facebook_via_ui(img_path, caption)
    except Exception as e:
        print("[ERROR] Facebook post:", e)
        os.remove(img_path)
        return

    posted.add(h)
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
