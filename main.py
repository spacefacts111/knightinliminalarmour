import os
import json
import time
import schedule
import hashlib
import random
from playwright.sync_api import sync_playwright, TimeoutError

# ─── CONFIG ────────────────────────────────────────────────────
FB_PAGE_ID           = os.getenv("FB_PAGE_ID")
GEMINI_STORAGE       = "cookies.json"
FB_STORAGE           = "fb_storage.json"
POSTED_HASHES_FILE   = "posted_hashes.json"
PROMPTS_FILE         = "prompts.txt"
IMAGE_DIR            = "generated"
# Gemini selectors
GEMINI_CONTAINER_SEL = 'infinite-scroller[data-test-id="chat-history-container"]'
GEMINI_EDITOR_SEL    = 'div.ql-editor[aria-label="Enter a prompt here"]'
GEMINI_IMAGE_SEL     = 'img.image.animate.loaded'
GEMINI_DOWNLOAD_BTN  = 'mat-icon[fonticon="download"]'
# ────────────────────────────────────────────────────────────────

os.makedirs(IMAGE_DIR, exist_ok=True)
if not os.path.exists(POSTED_HASHES_FILE):
    with open(POSTED_HASHES_FILE, "w") as f:
        json.dump([], f)

def load_posted_hashes():
    print("[STEP] Loading posted hashes")
    h = set(json.load(open(POSTED_HASHES_FILE)))
    print(f"[STEP] {len(h)} loaded")
    return h

def save_posted_hashes(hashes):
    print(f"[STEP] Saving {len(hashes)} hashes")
    with open(POSTED_HASHES_FILE, "w") as f:
        json.dump(list(hashes), f)

def random_prompt():
    if os.path.exists(PROMPTS_FILE):
        lines = [l.strip() for l in open(PROMPTS_FILE) if l.strip()]
        if lines:
            return random.choice(lines)
    return "a liminal dream hallway with red lights and fog"

posted = load_posted_hashes()

def generate_image_and_caption():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(storage_state=GEMINI_STORAGE, accept_downloads=True)
        page    = ctx.new_page()

        page.goto("https://gemini.google.com/app", timeout=120000)

        # ——— wait for the exact prompt box
        print("[STEP] Waiting for Gemini prompt editor")
        try:
            editor = page.wait_for_selector(GEMINI_EDITOR_SEL, timeout=120000)
        except TimeoutError:
            raise RuntimeError("Gemini editor never appeared")

        prompt = random_prompt()
        print(f"[STEP] Typing prompt: {prompt!r}")
        editor.click(force=True)
        editor.fill(prompt, force=True)
        editor.press("Enter")

        # ——— wait for generated image & download it
        page.wait_for_selector(GEMINI_CONTAINER_SEL, timeout=120000)
        page.wait_for_selector(f"{GEMINI_CONTAINER_SEL} >> {GEMINI_IMAGE_SEL}", timeout=120000)

        print("[STEP] Waiting for download icon")
        try:
            page.wait_for_selector(GEMINI_DOWNLOAD_BTN, timeout=60000)
        except TimeoutError:
            raise RuntimeError("Download icon never appeared")

        print("[STEP] Clicking download icon")
        with page.expect_download(timeout=60000) as dl_info:
            page.click(GEMINI_DOWNLOAD_BTN, force=True)
        download = dl_info.value
        suggested = download.suggested_filename or "image.png"
        name      = hashlib.sha256(suggested.encode()).hexdigest()[:8] + os.path.splitext(suggested)[1]
        dst       = os.path.join(IMAGE_DIR, name)
        download.save_as(dst)
        print(f"[STEP] Image saved to {dst}")

        # ——— get a caption
        editor.click(force=True)
        editor.fill("Write a short poetic mysterious caption for that image.", force=True)
        editor.press("Enter")
        page.wait_for_timeout(7000)

        texts = page.locator("div").all_text_contents()
        caption = next(
            (t.strip() for t in reversed(texts)
             if t.strip() != prompt and 10 < len(t.strip()) < 300),
            "A place you’ve seen in dreams."
        )
        print(f"[STEP] Caption: {caption!r}")

        browser.close()
        return dst, caption

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
    print("[STEP] run_once start")
    try:
        img, cap = generate_image_and_caption()
    except Exception as e:
        print(f"[ERROR] Generation failed: {e}")
        return

    h = hashlib.sha256(open(img, "rb").read()).hexdigest()
    if h in posted:
        print("[STEP] Duplicate, skipping")
        os.remove(img)
        return

    try:
        post_to_facebook_via_ui(img, cap)
    except Exception as e:
        print(f"[ERROR] FB post failed: {e}")
        os.remove(img)
        return

    posted.add(h)
    save_posted_hashes(posted)
    os.remove(img)
    print("[STEP] run_once complete")

def schedule_posts():
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
