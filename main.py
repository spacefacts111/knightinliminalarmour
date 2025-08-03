import os
import json
import random
import time
import schedule
import hashlib
from playwright.sync_api import sync_playwright

# Environment variables
FB_PAGE_ID = os.getenv("FB_PAGE_ID")

# Paths
IMAGE_DIR = "generated"
GEMINI_STORAGE = "cookies.json"
FB_STORAGE = "fb_storage.json"
POSTED_HASHES = "posted_hashes.json"
PROMPTS_FILE = "prompts.txt"

# Ensure image directory exists
os.makedirs(IMAGE_DIR, exist_ok=True)

def load_posted_hashes():
    if os.path.exists(POSTED_HASHES):
        with open(POSTED_HASHES) as f:
            return set(json.load(f))
    return set()

def save_posted_hashes(hashes):
    with open(POSTED_HASHES, "w") as f:
        json.dump(list(hashes), f)

posted_hashes = load_posted_hashes()

def random_prompt():
    if os.path.exists(PROMPTS_FILE):
        with open(PROMPTS_FILE) as f:
            lines = [l.strip() for l in f if l.strip()]
            return random.choice(lines)
    return "a liminal dream hallway with red lights and fog"

def generate_image_and_caption():
    print("[DEBUG] Generating image + caption")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Gemini context with saved session
        gem_context = browser.new_context(storage_state=GEMINI_STORAGE)
        gem_page = gem_context.new_page()
        gem_page.goto("https://gemini.google.com/app", timeout=120000)
        gem_page.keyboard.press("Escape")

        # Handle possible consent redirect
        if "consent.google.com" in gem_page.url:
            print("[DEBUG] Consent page detected, accepting")
            gem_page.wait_for_selector("button#introAgreeButton, button:text('I agree')", timeout=30000)
            gem_page.click("button#introAgreeButton, button:text('I agree')", force=True)
            gem_page.wait_for_navigation(timeout=60000)
            print("[DEBUG] Now at:", gem_page.url)

        # Wait for the prompt editor using multiple possible selectors
        gem_page.wait_for_selector(
            "div.ql-editor[data-placeholder='Ask Gemini'], "
            "input-area-v2 .ql-editor, "
            "rich-textarea .ql-editor",
            timeout=120000
        )
        # Grab whichever editor appears first
        editor = gem_page.locator(
            "div.ql-editor[data-placeholder='Ask Gemini'], "
            "input-area-v2 .ql-editor, "
            "rich-textarea .ql-editor"
        ).first

        prompt = random_prompt()
        print(f"[DEBUG] Prompt: {prompt}")
        editor.click(force=True)
        editor.fill(prompt, force=True)
        editor.press("Enter")

        # Wait for the generated image
        selector = "div.attachment-container.generated-images img.image"
        gem_page.wait_for_selector(selector, timeout=120000)
        img_elem = gem_page.locator(selector).nth(-1)
        src = img_elem.get_attribute("src")
        print(f"[DEBUG] Image URL: {src}")

        # Download via authenticated request
        response = gem_context.request.get(src)
        data = response.body()
        filename = os.path.basename(src.split('?')[0]) + ".png"
        dst = os.path.join(IMAGE_DIR, filename)
        with open(dst, "wb") as f:
            f.write(data)
        print(f"[DEBUG] Image saved to {dst}")

        # Ask for caption
        editor.click(force=True)
        editor.fill("Write a short poetic mysterious caption for that image.", force=True)
        editor.press("Enter")
        gem_page.wait_for_timeout(7000)
        texts = gem_page.locator("div").all_text_contents()
        caption = next((t.strip() for t in reversed(texts) if 10 < len(t.strip()) < 300), None)
        if not caption:
            caption = "A place you’ve seen in dreams."
        print(f"[DEBUG] Caption: {caption}")

        browser.close()
        return dst, caption

def post_via_ui(image_path, caption):
    print("[DEBUG] Posting via Facebook UI")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        fb_context = browser.new_context(storage_state=FB_STORAGE)
        page = fb_context.new_page()
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
    dst, caption = generate_image_and_caption()
    h = hashlib.sha256(open(dst, 'rb').read()).hexdigest()
    if h in posted_hashes:
        os.remove(dst)
        print("[DEBUG] Duplicate image, skipping")
        return
    post_via_ui(dst, caption)
    posted_hashes.add(h)
    save_posted_hashes(posted_hashes)
    os.remove(dst)
    print("[DEBUG] Image posted and cleaned up")

def schedule_posts():
    hours = sorted(random.sample(range(24), random.randint(1,4)))
    for h in hours:
        schedule.every().day.at(f"{h:02}:00").do(run_once)
    print(f"[DEBUG] Scheduled posts at: {hours}")

if __name__ == "__main__":
    run_once()
    schedule_posts()
    while True:
        schedule.run_pending()
        time.sleep(30)
