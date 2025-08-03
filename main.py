import json
import os
import random
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

POSTED_HASHES_FILE = "posted_hashes.json"
if not os.path.exists(POSTED_HASHES_FILE):
    with open(POSTED_HASHES_FILE, "w") as f:
        json.dump([], f)

def load_posted_hashes():
    with open(POSTED_HASHES_FILE, "r") as f:
        return json.load(f)

def save_posted_hashes(hashes):
    with open(POSTED_HASHES_FILE, "w") as f:
        json.dump(hashes, f)

# Gemini image + caption generator
def generate_image_and_caption(prompt="liminal space aesthetic, no people"):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        # ✅ Load Gemini cookies from local file
        with open("cookies.json", "r") as f:
            gemini_cookies = json.load(f)
        context.add_cookies(gemini_cookies)

        page = context.new_page()
        page.goto("https://gemini.google.com/app")

        if "accounts.google.com" in page.url:
            raise Exception("Gemini session expired. Update cookies.json")

        prompt_selectors = [
            'div.ql-editor[aria-label="Enter a prompt here"]',
            'rich-textarea[aria-label="Enter a prompt here"]',
            'div[contenteditable="true"][role="textbox"]',
        ]

        for sel in prompt_selectors:
            try:
                page.wait_for_selector(sel, timeout=10000)
                editor = page.locator(sel)
                editor.fill(prompt)
                editor.press("Enter")
                break
            except:
                continue
        else:
            raise Exception("Prompt box not found.")

        try:
            page.wait_for_selector("img.animate.loaded", timeout=120000)
            img_url = page.query_selector("img.animate.loaded").get_attribute("src")
            caption_elem = page.query_selector("div.model-response-text")
            caption = caption_elem.inner_text().strip() if caption_elem else "A liminal space."
        except PlaywrightTimeout:
            raise Exception("Image generation timed out.")

        browser.close()
        return img_url, caption

# Facebook poster via cookies
def post_to_facebook_with_cookies(img_url, caption):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        # ✅ Load Facebook cookies from fb_cookies.json
        with open("fb_cookies.json", "r") as f:
            fb_cookies = json.load(f)
        context.add_cookies(fb_cookies)

        page = context.new_page()
        page.goto("https://www.facebook.com/pages")
        page.wait_for_timeout(5000)

        # Go directly to Page
        page.goto(f"https://www.facebook.com/{os.getenv('FB_PAGE_ID')}")
        page.wait_for_timeout(5000)

        try:
            page.locator("text=Photo/video").click()
        except:
            raise Exception("Couldn't find post button. Facebook layout changed?")

        # Upload image
        with page.expect_file_chooser() as fc_info:
            page.locator("input[type='file']").click()
        chooser = fc_info.value
        chooser.set_files(download_image(img_url))

        page.wait_for_timeout(5000)

        # Write caption
        caption_box = page.locator("div[role='textbox']").first
        caption_box.fill(caption)

        # Post it
        page.locator("text=Post").last.click()
        page.wait_for_timeout(5000)
        browser.close()
        print("✅ Posted to Facebook with cookies!")

def download_image(url, filename="post.jpg"):
    import requests
    r = requests.get(url)
    with open(filename, "wb") as f:
        f.write(r.content)
    return filename

def run_once():
    posted = load_posted_hashes()
    try:
        img_url, caption = generate_image_and_caption()
        if img_url in posted:
            print("⚠️ Already posted this image.")
            return
        post_to_facebook_with_cookies(img_url, caption)
        posted.append(img_url)
        save_posted_hashes(posted)
    except Exception as e:
        print("❌", str(e))

def schedule_posts(n=4):
    hours = sorted(random.sample(range(24), n))
    print("[STEP] Scheduled at hours:", hours)

    while True:
        now = datetime.now().hour
        if now in hours:
            run_once()
            time.sleep(3600)
        else:
            time.sleep(300)

if __name__ == "__main__":
    run_once()
    schedule_posts(random.randint(1, 4))
