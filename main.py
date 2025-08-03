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
# your top-level container:
GEMINI_CONTAINER_SEL = 'infinite-scroller[data-test-id="chat-history-container"]'
# the prompt editor:
GEMINI_EDITOR_SEL    = 'rich-textarea .ql-editor'
# ────────────────────────────────────────────────────────────────

# ensure directories & state file
os.makedirs(IMAGE_DIR, exist_ok=True)
if not os.path.exists(POSTED_HASHES_FILE):
    with open(POSTED_HASHES_FILE, "w") as f:
        json.dump([], f)

def load_posted_hashes():
    print("[STEP] Loading posted hashes")
    h = set(json.load(open(POSTED_HASHES_FILE)))
    print(f"[STEP] {len(h)} hashes loaded")
    return h

def save_posted_hashes(hashes):
    print(f"[STEP] Saving {len(hashes)} hashes")
    with open(POSTED_HASHES_FILE, "w") as f:
        json.dump(list(hashes), f)

def random_prompt():
    print("[STEP] Selecting prompt")
    if os.path.exists(PROMPTS_FILE):
        lines = [l.strip() for l in open(PROMPTS_FILE) if l.strip()]
        if lines:
            choice = random.choice(lines)
            print(f"[STEP] Prompt chosen: {choice!r}")
            return choice
    default = "a liminal dream hallway with red lights and fog"
    print(f"[STEP] Using default prompt: {default!r}")
    return default

posted = load_posted_hashes()

def generate_image_and_caption():
    print("[STEP] generate_image_and_caption")
    with sync_playwright() as p:
        print("[STEP] Launch browser")
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(storage_state=GEMINI_STORAGE)
        page    = ctx.new_page()

        print("[STEP] Go to Gemini")
        page.goto("https://gemini.google.com/app", timeout=120000)

        print("[STEP] Wait for editor")
        try:
            editor = page.wait_for_selector(GEMINI_EDITOR_SEL, timeout=120000)
        except TimeoutError:
            raise RuntimeError("Editor never appeared")

        prompt = random_prompt()
        print(f"[STEP] Type prompt: {prompt!r}")
        editor.click(force=True)
        editor.fill(prompt, force=True)
        editor.press("Enter")

        print("[STEP] Waiting for container to render images")
        page.wait_for_selector(GEMINI_CONTAINER_SEL, timeout=120000)

        print("[STEP] Dumping container HTML for debug:")
        html_snippet = page.evaluate(f'''
            () => document.querySelector("{GEMINI_CONTAINER_SEL}")?.innerHTML
        ''') or ""
        print(html_snippet[:500].replace("\\n", " ") + ("..." if len(html_snippet) > 500 else ""))

        print("[STEP] Looking for <img.image.animate.loaded>")
        src = page.evaluate(f'''
            () => {{
                const c = document.querySelector("{GEMINI_CONTAINER_SEL}");
                if (!c) return null;
                const img = c.querySelector("img.image.animate.loaded");
                return img?.src || null;
            }}
        ''')
        if not src:
            raise RuntimeError("Couldn’t find any <img.image.animate.loaded> inside container")

        print(f"[STEP] Image URL found: {src}")
        resp = ctx.request.get(src)
        resp.raise_for_status()
        data = resp.body()

        filename = os.path.basename(src.split("?",1)[0]) + ".png"
        dst = os.path.join(IMAGE_DIR, filename)
        print(f"[STEP] Saving image to {dst}")
        with open(dst, "wb") as f:
            f.write(data)

        print("[STEP] Prompting for caption")
        editor.click(force=True)
        editor.fill("Write a short poetic mysterious caption for that image.", force=True)
        editor.press("Enter")
        page.wait_for_timeout(7000)

        print("[STEP] Extracting caption text")
        texts = page.locator("div").all_text_contents()
        caption = next(
            (t.strip() for t in reversed(texts)
             if t.strip() != prompt and 10 < len(t.strip()) < 300),
            None
        ) or "A place you’ve seen in dreams."
        print(f"[STEP] Caption: {caption!r}")

        browser.close()
        print("[STEP] Generation complete")
        return dst, caption

def post_to_facebook_via_ui(image_path, caption):
    print("[STEP] post_to_facebook_via_ui")
    with sync_playwright() as p:
        print("[STEP] Launch FB browser")
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(storage_state=FB_STORAGE)
        page    = ctx.new_page()

        print(f"[STEP] Navigate to Facebook Page {FB_PAGE_ID}")
        page.goto(f"https://www.facebook.com/{FB_PAGE_ID}", timeout=60000)

        print("[STEP] Open post composer")
        page.wait_for_selector("div[aria-label='Create a post']", timeout=60000)
        page.click("div[aria-label='Create a post']", force=True)

        print("[STEP] Uploading image")
        page.wait_for_selector("input[type=file']", timeout=30000)
        page.set_input_files("input[type=file']", image_path)

        print("[STEP] Filling caption")
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
        img, cap = generate_image_and_caption()
    except Exception as e:
        print(f"[ERROR] Generation failed: {e}")
        return

    h = hashlib.sha256(open(img, "rb").read()).hexdigest()
    print(f"[STEP] Image hash: {h}")
    if h in posted:
        print("[STEP] Duplicate detected, skipping")
        os.remove(img)
        return

    try:
        post_to_facebook_via_ui(img, cap)
    except Exception as e:
        print(f"[ERROR] Facebook post failed: {e}")
        os.remove(img)
        return

    posted.add(h)
    save_posted_hashes(posted)
    os.remove(img)
    print("[STEP] run_once complete")

def schedule_posts():
    print("[STEP] Scheduling posts")
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
