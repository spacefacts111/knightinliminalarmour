import os
import json
import random
import time
import schedule
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright
from PIL import Image
import hashlib

FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")

IMAGE_DIR = "generated"
COOKIES_PATH = "cookies.json"
POSTED_HASHES_FILE = "posted_hashes.json"
PROMPTS_FILE = "prompts.txt"

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
            return random.choice(f.readlines()).strip()
    return "a liminal dream hallway with red lights and fog"

def generate_image_and_caption():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        with open(COOKIES_PATH, "r") as f:
            cookies = json.load(f)
        context.add_cookies(cookies)

        page = context.new_page()
        print("[🌐] Loading Gemini...")
        page.goto("https://gemini.google.com/app")
        page.wait_for_selector("textarea", timeout=45000)

        prompt = random_prompt()
        print(f"[🧠] Prompting Gemini: {prompt}")
        page.fill("textarea", prompt)
        page.press("textarea", "Enter")
        page.wait_for_timeout(10000)

        # Click the most recent image generated
        print("[🖼️] Waiting for generated image...")
        image_selector = "img[alt='Generated image']"
        page.wait_for_selector(image_selector, timeout=30000)
        images = page.locator(image_selector)
        if images.count() == 0:
            raise RuntimeError("❌ No image found.")
        images.nth(0).click()
        page.wait_for_timeout(2000)

        # Click the download button
        print("[⬇️] Downloading image...")
        page.wait_for_selector("button:has-text('Download')", timeout=10000)
        page.click("button:has-text('Download')")
        page.wait_for_timeout(5000)

        # Find downloaded image
        downloads = os.listdir(os.path.expanduser("~/Downloads"))
        images = [f for f in downloads if f.endswith(".png")]
        if not images:
            raise RuntimeError("❌ Image not downloaded")
        latest = max(images, key=lambda x: os.path.getctime(os.path.join(os.path.expanduser("~/Downloads"), x)))
        src_path = os.path.join(os.path.expanduser("~/Downloads"), latest)
        dst_path = os.path.join(IMAGE_DIR, latest)
        os.rename(src_path, dst_path)
        print(f"[✓] Image saved: {dst_path}")

        # Ask Gemini to generate a caption
        print("[💬] Asking for caption...")
        page.fill("textarea", "Write a short poetic mysterious caption for that image.")
        page.press("textarea", "Enter")
        page.wait_for_timeout(7000)

        responses = page.locator("div").all_text_contents()
        caption = next((r.strip() for r in reversed(responses) if 10 < len(r.strip()) < 300), None)
        if not caption:
            caption = "A place you’ve seen in dreams."

        print(f"[📝] Caption: {caption}")
        browser.close()
        return dst_path, caption

def hash_image(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def post_to_facebook(image_path, caption):
    print("[📤] Uploading to Facebook...")
    with open(image_path, 'rb') as img_file:
        files = {'source': img_file}
        data = {'caption': caption, 'access_token': FB_PAGE_ACCESS_TOKEN}
        url = f"https://graph.facebook.com/{FB_PAGE_ID}/photos"
        r = requests.post(url, files=files, data=data)
    if r.status_code != 200:
        raise RuntimeError(f"❌ FB post failed: {r.status_code} {r.text}")
    print("[✅] Posted successfully")

def run_once():
    try:
        img_path, caption = generate_image_and_caption()
        img_hash = hash_image(img_path)
        if img_hash in posted_hashes:
            print("[⏩] Already posted this image. Skipping.")
            return
        post_to_facebook(img_path, caption)
        posted_hashes.add(img_hash)
        save_posted_hashes(posted_hashes)
        os.remove(img_path)
        print("[🗑️] Image deleted.")
    except Exception as e:
        print(f"[!] Error: {e}")

def schedule_daily_posts():
    times = sorted(random.sample(range(24), random.randint(1, 4)))
    for hour in times:
        schedule.every().day.at(f"{hour:02}:00").do(run_once)
    print(f"📅 Scheduled post times: {times}")

if not posted_hashes:
    print("🚀 First run — test post starting now...")
    run_once()

schedule_daily_posts()

while True:
    schedule.run_pending()
    time.sleep(30)
