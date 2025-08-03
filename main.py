import os
import json
import random
import time
import schedule
import requests
from playwright.sync_api import sync_playwright
import hashlib

# Facebook Page credentials (Railway Variables)
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")

# File and directory paths
IMAGE_DIR = "generated"
COOKIES_PATH = "cookies.json"
POSTED_HASHES_FILE = "posted_hashes.json"
PROMPTS_FILE = "prompts.txt"

# Ensure the images directory exists
os.makedirs(IMAGE_DIR, exist_ok=True)

def load_posted_hashes():
    if os.path.exists(POSTED_HASHES_FILE):
        with open(POSTED_HASHES_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_posted_hashes(hashes):
    with open(POSTED_HASHES_FILE, "w") as f:
        json.dump(list(hashes), f)

posted_hashes = load_posted_hashes()

def random_prompt():
    if os.path.exists(PROMPTS_FILE):
        with open(PROMPTS_FILE, "r") as f:
            lines = [l.strip() for l in f if l.strip()]
            return random.choice(lines)
    return "a liminal dream hallway with red lights and fog"

def generate_image_and_caption():
    print("[DEBUG] Starting generate_image_and_caption")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        # Load your Gemini login cookies
        with open(COOKIES_PATH, "r") as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        print("[DEBUG] Cookies added")
        page = context.new_page()

        dst = None
        caption = None

        # ——— LIVE CHAT MODE ———
        try:
            print("[DEBUG] LIVE MODE: Navigate to chat UI")
            page.goto("https://gemini.google.com/app")
            page.keyboard.press("Escape")  # dismiss overlays
            print("[DEBUG] Waiting for prompt editor")
            page.wait_for_selector("div.ql-editor[contenteditable='true']", timeout=60000)
            editor = page.locator("div.ql-editor[contenteditable='true']")
            prompt = random_prompt()
            print(f"[DEBUG] Prompt: {prompt}")
            editor.click(force=True)
            editor.fill(prompt, force=True)
            editor.press("Enter")
            print("[DEBUG] Prompt sent, waiting for generated image")

            selector = "div.attachment-container.generated-images img.image"
            page.wait_for_selector(selector, timeout=60000)
            imgs = page.locator(selector)
            count = imgs.count()
            print(f"[DEBUG] Found {count} chat images")
            img_elem = imgs.nth(count - 1)
            src = img_elem.get_attribute("src")
            if not src:
                raise RuntimeError("No image src found in live chat")

            # Download via HTTP
            resp = requests.get(src, stream=True)
            resp.raise_for_status()
            filename = os.path.basename(src.split("?")[0])
            dst = os.path.join(IMAGE_DIR, filename)
            with open(dst, "wb") as f:
                for chunk in resp.iter_content(1024):
                    f.write(chunk)
            print(f"[DEBUG] LIVE MODE: Image downloaded to {dst}")

            # Get caption via chat
            editor.click(force=True)
            editor.fill("Write a short poetic mysterious caption for that image.", force=True)
            editor.press("Enter")
            print("[DEBUG] Waiting for caption")
            page.wait_for_timeout(7000)
            texts = page.locator("div").all_text_contents()
            caption = next((t.strip() for t in reversed(texts) if 10 < len(t.strip()) < 300), None)

        except Exception as live_err:
            print(f"[WARN] Live mode failed: {live_err}")

            # ——— HISTORY FALLBACK MODE ———
            try:
                print("[DEBUG] FALLBACK MODE: Navigate to history")
                page.goto("https://gemini.google.com/app/history")
                page.keyboard.press("Escape")
                selector = "div.attachment-container.generated-images img.image"
                page.wait_for_selector(selector, timeout=60000)
                hist_imgs = page.locator(selector)
                count = hist_imgs.count()
                print(f"[DEBUG] Found {count} history images")
                img_elem = hist_imgs.nth(0)
                src = img_elem.get_attribute("src")
                if not src:
                    raise RuntimeError("No image src in history")

                resp = requests.get(src, stream=True)
                resp.raise_for_status()
                filename = os.path.basename(src.split("?")[0])
                dst = os.path.join(IMAGE_DIR, filename)
                with open(dst, "wb") as f:
                    for chunk in resp.iter_content(1024):
                        f.write(chunk)
                print(f"[DEBUG] HISTORY MODE: Image downloaded to {dst}")

                # Fallback caption
                caption = "A place you’ve seen in dreams."

            except Exception as hist_err:
                print(f"[ERROR] History fallback failed: {hist_err}")

        finally:
            browser.close()

        if not dst:
            raise RuntimeError("❌ Failed to download image in both modes")
        if not caption:
            caption = "A place you’ve seen in dreams."
        print(f"[DEBUG] Caption: {caption}")
        return dst, caption

def hash_image(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def post_to_facebook(image_path, caption):
    print("[DEBUG] Posting to Facebook")
    with open(image_path, 'rb') as img:
        files = {'source': img}
        data = {'caption': caption, 'access_token': FB_PAGE_ACCESS_TOKEN}
        url = f"https://graph.facebook.com/{FB_PAGE_ID}/photos"
        r = requests.post(url, files=files, data=data)
    if r.status_code != 200:
        raise RuntimeError(f"Facebook post failed: {r.status_code} {r.text}")
    print("[DEBUG] Facebook post successful")

def run_once():
    print("[DEBUG] run_once start")
    try:
        img_path, caption = generate_image_and_caption()
        print("[DEBUG] Image and caption generated")
        img_hash = hash_image(img_path)
        if img_hash in posted_hashes:
            print("[DEBUG] Duplicate image—skipping")
        else:
            post_to_facebook(img_path, caption)
            posted_hashes.add(img_hash)
            save_posted_hashes(posted_hashes)
            os.remove(img_path)
            print("[DEBUG] Image deleted after post")
    except Exception as e:
        print(f"[ERROR] {e}")

def schedule_daily_posts():
    times = sorted(random.sample(range(24), random.randint(1, 4)))
    for hour in times:
        schedule.every().day.at(f"{hour:02}:00").do(run_once)
    print(f"[DEBUG] Scheduled post times: {times}")

# Initial run
if not posted_hashes:
    print("[DEBUG] First run test post")
    run_once()

schedule_daily_posts()
while True:
    schedule.run_pending()
    time.sleep(30)
