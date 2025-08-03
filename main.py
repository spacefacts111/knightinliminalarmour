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

def log(step):
    print(f"[STEP] {step}")

def load_posted_hashes():
    log("Loading posted hashes...")
    with open(POSTED_HASHES_FILE, "r") as f:
        return json.load(f)

def save_posted_hashes(hashes):
    with open(POSTED_HASHES_FILE, "w") as f:
        json.dump(hashes, f)

def generate_image_and_caption(prompt="liminal space aesthetic, no people"):
    log("Starting Gemini image + caption generation...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        log("Loading Gemini cookies...")
        with open("cookies.json", "r") as f:
            gemini_cookies = json.load(f)
        context.add_cookies(gemini_cookies)

        page = context.new_page()
        log("Navigating to Gemini...")
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
                log(f"Prompt submitted using selector: {sel}")
                break
            except:
                continue
        else:
            raise Exception("Prompt box not found.")

        try:
            log("Waiting for image to generate...")
            page.wait_for_selector("img", timeout=120000)
            all_imgs = page.query_selector_all("img")

            valid_imgs = [
                img.get_attribute("src")
                for img in all_imgs
                if img.get_attribute("src") and "googleusercontent" in img.get_attribute("src")
            ]

            if not valid_imgs:
                raise Exception("Image appeared, but none had a usable src.")

            img_url = valid_imgs[0]
            log(f"Image URL retrieved: {img_url}")

            # Force Gemini caption load
            caption_elem = page.locator("div.model-response-text").first
            caption_elem.wait_for(timeout=10000)
            caption = caption_elem.inner_text().strip()

            if not caption:
                raise Exception("❌ Gemini generated no caption.")
            log(f"Caption retrieved: {caption}")

        except PlaywrightTimeout:
            raise Exception("❌ Image or caption timed out.")

        browser.close()
        return img_url, caption

def post_to_facebook_with_cookies(img_url, caption):
    log("Starting Facebook post using cookies...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        log("Loading Facebook cookies...")
        with open("fb_cookies.json", "r") as f:
            fb_cookies = json.load(f)
        context.add_cookies(fb_cookies)

        page = context.new_page()
        log("Opening Facebook pages...")
        page.goto("https://www.facebook.com/pages")
        page.wait_for_timeout(5000)

        page.goto(f"https://www.facebook.com/{os.getenv('FB_PAGE_ID')}")
        page.wait_for_timeout(5000)

        try:
            log("Clicking 'Photo/video' button...")
            # ✅ Corrected button logic
            page.locator("span:has-text('Photo/video')").click()
        except:
            raise Exception("Couldn't find 'Photo/video' button. Facebook layout may have changed.")

        log("Uploading image...")
        with page.expect_file_chooser() as fc_info:
            page.locator("input[type='file']").click()
        chooser = fc_info.value
        chooser.set_files(download_image(img_url))

        page.wait_for_timeout(5000)

        log("Filling in caption...")
        caption_box = page.locator("div[role='textbox']").first
        caption_box.fill(caption)

        log("Clicking 'Post' button...")
        page.locator("text=Post").last.click()
        page.wait_for_timeout(5000)

        browser.close()
        log("✅ Posted to Facebook with cookies!")

def download_image(url, filename="post.jpg"):
    import requests
    log("Downloading image from Gemini...")
    r = requests.get(url)
    with open(filename, "wb") as f:
        f.write(r.content)
    return filename

def run_once():
    log("Running once...")
    posted = load_posted_hashes()
    try:
        img_url, caption = generate_image_and_caption()
        if img_url in posted:
            log("⚠️ Already posted this image. Skipping.")
            return
        post_to_facebook_with_cookies(img_url, caption)
        posted.append(img_url)
        save_posted_hashes(posted)
    except Exception as e:
        print("❌", str(e))

def schedule_posts(n=4):
    hours = sorted(random.sample(range(24), n))
    log(f"Scheduled to post at hours: {hours}")

    while True:
        now = datetime.now().hour
        if now in hours:
            log(f"Posting time matched (hour {now})! Running post...")
            run_once()
            time.sleep(3600)
        else:
            time.sleep(300)

if __name__ == "__main__":
    log("Launching bot for the first time...")
    run_once()
    schedule_posts(random.randint(1, 4))
