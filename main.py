import os
import json
import random
import time
import schedule
import requests
import hashlib
from playwright.sync_api import sync_playwright

# Facebook credentials (Railway env vars)
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")

# Paths
IMAGE_DIR = "generated"
COOKIES_PATH = "cookies.json"
POSTED_HASHES_FILE = "posted_hashes.json"
PROMPTS_FILE = "prompts.txt"

os.makedirs(IMAGE_DIR, exist_ok=True)

def load_posted_hashes():
    if os.path.exists(POSTED_HASHES_FILE):
        return set(json.load(open(POSTED_HASHES_FILE)))
    return set()

def save_posted_hashes(hashes):
    json.dump(list(hashes), open(POSTED_HASHES_FILE, "w"))

posted = load_posted_hashes()

def random_prompt():
    if os.path.exists(PROMPTS_FILE):
        lines = [l.strip() for l in open(PROMPTS_FILE) if l.strip()]
        return random.choice(lines)
    return "a liminal dream hallway with red lights and fog"

def download_with_playwright(page, selector, dst):
    page.wait_for_selector(selector, timeout=60000)
    with page.expect_download(timeout=60000) as dl_info:
        page.click(selector, force=True)
    dl = dl_info.value
    dl.save_as(dst)
    return dst

def capture_screenshot(page, locator, dst):
    elm = page.locator(locator)
    page.wait_for_selector(locator, timeout=60000)
    elm.screenshot(path=dst)
    return dst

def generate_and_download():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        cookies = json.load(open(COOKIES_PATH))
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        # LIVE CHAT MODE
        page.goto("https://gemini.google.com/app")
        page.keyboard.press("Escape")
        page.wait_for_selector("div.ql-editor[contenteditable='true']", timeout=60000)
        editor = page.locator("div.ql-editor[contenteditable='true']")
        prompt = random_prompt()
        editor.click(force=True)
        editor.fill(prompt, force=True)
        editor.press("Enter")

        # wait for image thumbnail
        page.wait_for_selector("div.attachment-container.generated-images img.image", timeout=60000)
        # click it to open controls
        page.locator("div.attachment-container.generated-images img.image").nth(-1).click()

        # try download button
        filename = f"gemini_{int(time.time())}.png"
        dst = os.path.join(IMAGE_DIR, filename)
        try:
            dst = download_with_playwright(page,
                                           "button[data-test-id='download-generated-image-button']",
                                           dst)
        except Exception:
            # fallback to screenshot if download button fails
            dst = capture_screenshot(page,
                                     "div.attachment-container.generated-images",
                                     dst)

        # CAPTION
        editor.click(force=True)
        editor.fill("Write a short poetic mysterious caption for that image.", force=True)
        editor.press("Enter")
        page.wait_for_timeout(7000)
        texts = page.locator("div").all_text_contents()
        caption = next((t.strip() for t in reversed(texts) if 10 < len(t.strip()) < 300), None)
        if not caption:
            caption = "A place you’ve seen in dreams."

        browser.close()
        return dst, caption

def post_to_facebook(path, caption):
    with open(path, "rb") as img:
        files = {"source": img}
        data = {"caption": caption, "access_token": FB_PAGE_ACCESS_TOKEN}
        url = f"https://graph.facebook.com/{FB_PAGE_ID}/photos"
        r = requests.post(url, files=files, data=data)
        r.raise_for_status()

def run_once():
    try:
        img_path, caption = generate_and_download()
        h = hashlib.sha256(open(img_path, "rb").read()).hexdigest()
        if h in posted:
            print("Already posted, skipping")
            os.remove(img_path)
            return
        post_to_facebook(img_path, caption)
        posted.add(h)
        save_posted_hashes(posted)
        os.remove(img_path)
        print("Posted and cleaned up")
    except Exception as e:
        print("ERROR:", e)

def schedule_posts():
    hours = random.sample(range(24), random.randint(1,4))
    for h in hours:
        schedule.every().day.at(f"{h:02}:00").do(run_once)
    print("Scheduled at", hours)

if __name__=="__main__":
    if not posted:
        run_once()
    schedule_posts()
    while True:
        schedule.run_pending()
        time.sleep(30)
