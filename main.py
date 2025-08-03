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

# Paths and constants
IMAGE_DIR = "generated"
DOWNLOADS_DIR = "downloads"
COOKIES_PATH = "cookies.json"
POSTED_HASHES_FILE = "posted_hashes.json"
PROMPTS_FILE = "prompts.txt"

# Ensure necessary directories exist
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

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
    print("[DEBUG] Starting generate_image_and_caption")
    with sync_playwright() as p:
        print("[DEBUG] Launching browser")
        browser = p.chromium.launch(headless=True)
        print("[DEBUG] Browser launched, creating context")
        # Only accept downloads here; we'll save them manually
        context = browser.new_context(accept_downloads=True)

        # Load cookies
        with open(COOKIES_PATH, "r") as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        print("[DEBUG] Cookies added")

        page = context.new_page()
        print("[DEBUG] Navigating to Gemini")
        page.goto("https://gemini.google.com/app")
        print("[DEBUG] Page URL after goto:", page.url)

        print("[DEBUG] Waiting for prompt editor")
        page.wait_for_selector("div.ql-editor[contenteditable='true']", timeout=60000)
        editor = page.locator("div.ql-editor[contenteditable='true']")
        prompt = random_prompt()
        print(f"[DEBUG] Prompt: {prompt}")
        editor.click()
        editor.fill(prompt)
        editor.press("Enter")
        print("[DEBUG] Prompt sent, waiting for image")
        page.wait_for_selector("img[alt='Generated image']", timeout=60000)

        print("[DEBUG] Image appeared, clicking")
        page.click("img[alt='Generated image']")
        print("[DEBUG] Waiting for download event")
        with page.expect_download(timeout=30000) as download_info:
            page.click("button:has-text('Download')")
        download = download_info.value

        # Save into your DOWNLOADS_DIR
        filename = download.suggested_filename
        dst_path = os.path.join(IMAGE_DIR, filename)
        download.save_as(dst_path)
        print("[DEBUG] Download saved to", dst_path)

        # Generate caption
        editor.click()
        editor.fill("Write a short poetic mysterious caption for that image.")
        editor.press("Enter")
        print("[DEBUG] Caption prompt sent")
        page.wait_for_timeout(7000)
        responses = page.locator("div").all_text_contents()
        caption = next((r.strip() for r in reversed(responses) if 10 < len(r.strip()) < 300), None)
        if not caption:
            caption = "A place you’ve seen in dreams."
        print("[DEBUG] Caption:", caption)

        browser.close()
        return dst_path, caption

def hash_image(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def post_to_facebook(image_path, caption):
    print("[DEBUG] Posting to Facebook")
    with open(image_path, 'rb') as img_file:
        files = {'source': img_file}
        data = {'caption': caption, 'access_token': FB_PAGE_ACCESS_TOKEN}
        url = f"https://graph.facebook.com/{FB_PAGE_ID}/photos"
        r = requests.post(url, files=files, data=data)
    if r.status_code != 200:
        raise RuntimeError(f"FB post failed: {r.status_code} {r.text}")
    print("[DEBUG] Facebook post successful")

def run_once():
    print("[DEBUG] run_once start")
    try:
        img_path, caption = generate_image_and_caption()
        print("[DEBUG] Image and caption generated")
        img_hash = hash_image(img_path)
        if img_hash in posted_hashes:
            print("[DEBUG] Already posted image, skipping")
        else:
            post_to_facebook(img_path, caption)
            posted_hashes.add(img_hash)
            save_posted_hashes(posted_hashes)
            os.remove(img_path)
            print("[DEBUG] Image deleted after post")
    except Exception as e:
        print(f"[ERROR] {e}")

def schedule_daily_posts():
    times = sorted(random.sample(range(24), random.randint(1,4)))
    for hour in times:
        schedule.every().day.at(f"{hour:02}:00").do(run_once)
    print("[DEBUG] Scheduled post times:", times)

# Initial run
if not posted_hashes:
    print("[DEBUG] First run test post")
    run_once()

schedule_daily_posts()
while True:
    schedule.run_pending()
    time.sleep(30)
