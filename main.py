import os
import json
import time
import schedule
import hashlib
import random
from playwright.sync_api import sync_playwright, TimeoutError

# ─── CONFIG ────────────────────────────────────────────────────
FB_PAGE_ID         = os.getenv("FB_PAGE_ID")
GEMINI_STORAGE     = "cookies.json"
FB_STORAGE         = "fb_storage.json"
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
    print("[STEP] Loading posted hashes")
    hashes = set(json.load(open(POSTED_HASHES_FILE)))
    print(f"[STEP] Loaded {len(hashes)} hashes")
    return hashes

def save_posted_hashes(hashes):
    print(f"[STEP] Saving {len(hashes)} posted hashes")
    with open(POSTED_HASHES_FILE, "w") as f:
        json.dump(list(hashes), f)

def random_prompt():
    print("[STEP] Selecting random prompt")
    if os.path.exists(PROMPTS_FILE):
        with open(PROMPTS_FILE) as f:
            lines = [l.strip() for l in f if l.strip()]
        if lines:
            choice = random.choice(lines)
            print(f"[STEP] Prompt chosen: {choice!r}")
            return choice
    default = "a liminal dream hallway with red lights and fog"
    print(f"[STEP] No prompts.txt found, using default: {default!r}")
    return default

posted = load_posted_hashes()

def generate_image_and_caption():
    print("[STEP] Starting image + caption generation")
    with sync_playwright() as p:
        print("[STEP] Launching browser")
        browser = p.chromium.launch(headless=True)
        print("[STEP] Creating Gemini context")
        context = browser.new_context(storage_state=GEMINI_STORAGE)
        page = context.new_page()

        print("[STEP] Intercepting responses for image bytes")
        image_data = {"url": None, "body": None}
        def on_response(resp):
            u = resp.url
            if u.startswith("https://lh3.googleusercontent.com"):
                try:
                    print(f"[STEP] Captured image response URL: {u}")
                    image_data["body"] = resp.body()
                    image_data["url"]  = u
                except:
                    pass
        page.on("response", on_response)

        print("[STEP] Navigating to Gemini chat")
        page.goto("https://gemini.google.com/app", timeout=120000)

        print("[STEP] Waiting for prompt editor")
        try:
            editor = page.wait_for_selector(
                "div.ql-editor[contenteditable='true'], div[aria-label='Enter a prompt here']",
                timeout=120000
            )
        except TimeoutError:
            raise RuntimeError("Prompt editor never appeared")

        prompt = random_prompt()
        print("[STEP] Filling prompt into editor")
        editor.click(force=True)
        editor.fill(prompt, force=True)
        editor.press("Enter")

        print("[STEP] Waiting for image response")
        page.wait_for_timeout(8000)
        if not image_data["body"]:
            raise RuntimeError("No image intercepted from Gemini")

        url = image_data["url"]
        print(f"[STEP] Image URL: {url}")
        filename = os.path.basename(url.split("?",1)[0]) + ".png"
        path = os.path.join(IMAGE_DIR, filename)
        print(f"[STEP] Saving image to {path}")
        with open(path, "wb") as f:
            f.write(image_data["body"])

        print("[STEP] Prompting for caption")
        editor.click(force=True)
        editor.fill("Write a short poetic mysterious caption for that image.", force=True)
        editor.press("Enter")
        page.wait_for_timeout(7000)

        print("[STEP] Extracting caption text")
        texts = page.locator("div").all_text_contents()
        caption = next(
            (t.strip() for t in reversed(texts)
             if t.strip() and t.strip() != prompt and 10 < len(t.strip()) < 300),
            None
        ) or "A place you’ve seen in dreams."
        print(f"[STEP] Caption extracted: {caption!r}")

        browser.close()
        print("[STEP] Generation complete")
        return path, caption

def post_to_facebook_via_ui(image_path, caption):
    print("[STEP] Starting Facebook UI post")
    with sync_playwright() as p:
        print("[STEP] Launching browser for Facebook")
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(storage_state=FB_STORAGE)
        page    = ctx.new_page()

        print(f"[STEP] Navigating to Facebook Page {FB_PAGE_ID}")
        page.goto(f"https://www.facebook.com/{FB_PAGE_ID}", timeout=60000)

        print("[STEP] Opening post composer")
        page.wait_for_selector("div[aria-label='Create a post']", timeout=60000)
        page.click("div[aria-label='Create a post']", force=True)

        print("[STEP] Uploading image")
        page.wait_for_selector("input[type=file]", timeout=30000)
        page.set_input_files("input[type=file']", image_path)

        print("[STEP] Entering caption")
        page.wait_for_selector("div[aria-label='Write a post']", timeout=30000)
        page.fill("div[aria-label='Write a post']", caption)

        print("[STEP] Submitting post")
        page.click("div[aria-label='Post']", force=True)
        page.wait_for_timeout(5000)

        browser.close()
        print("[STEP] Facebook post complete")

def run_once():
    print("[STEP] run_once start")
    try:
        img_path, caption = generate_image_and_caption()
    except Exception as e:
        print(f"[ERROR] image generation failed: {e}")
        return

    h = hashlib.sha256(open(img_path, "rb").read()).hexdigest()
    print(f"[STEP] Image hash: {h}")
    if h in posted:
        os.remove(img_path)
        print("[STEP] Duplicate image detected, skipping post")
        return

    try:
        post_to_facebook_via_ui(img_path, caption)
    except Exception as e:
        print(f"[ERROR] Facebook post failed: {e}")
        os.remove(img_path)
        return

    posted.add(h)
    save_posted_hashes(posted)
    os.remove(img_path)
    print("[STEP] run_once complete: image posted and cleaned up")

def schedule_posts():
    print("[STEP] Scheduling daily posts")
    hours = sorted(random.sample(range(24), random.randint(1,4)))
    for h in hours:
        schedule.every().day.at(f"{h:02}:00").do(run_once)
    print(f"[STEP] Scheduled at hours: {hours}")

if __name__ == "__main__":
    run_once()
    schedule_posts()
    while True:
        schedule.run_pending()
        time.sleep(30)
