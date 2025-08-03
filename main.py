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
# selectors
EDITOR_SEL           = 'div.ql-editor[aria-label="Enter a prompt here"]'
LIVE_IMG_SEL         = "img[src^='blob:']"
HIST_IMG_SEL         = "div.attachment-container.generated-images img.image"
# ────────────────────────────────────────────────────────────────

os.makedirs(IMAGE_DIR, exist_ok=True)
if not os.path.exists(POSTED_HASHES_FILE):
    with open(POSTED_HASHES_FILE, "w") as f:
        json.dump([], f)

def load_hashes():
    print("[STEP] Loading posted hashes")
    h = set(json.load(open(POSTED_HASHES_FILE)))
    print(f"[STEP] {len(h)} loaded")
    return h

def save_hashes(h):
    print(f"[STEP] Saving {len(h)} hashes")
    with open(POSTED_HASHES_FILE, "w") as f:
        json.dump(list(h), f)

def random_prompt():
    if os.path.exists(PROMPTS_FILE):
        lines = [l.strip() for l in open(PROMPTS_FILE) if l.strip()]
        if lines:
            choice = random.choice(lines)
            print(f"[STEP] Prompt chosen from list: {choice!r}")
            return choice
    default = "a liminal dream hallway with red lights and fog"
    print(f"[STEP] Using default prompt: {default!r}")
    return default

posted = load_hashes()

def generate_image_and_caption():
    print("[STEP] generate_image_and_caption")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(storage_state=GEMINI_STORAGE)
        page    = ctx.new_page()

        print("[STEP] Navigating to Gemini")
        page.goto("https://gemini.google.com/app", timeout=120000)

        # Live mode
        try:
            print("[STEP] LIVE MODE: waiting for editor")
            editor = page.wait_for_selector(EDITOR_SEL, timeout=120000)
            prompt = random_prompt()

            print(f"[STEP] LIVE MODE: typing prompt {prompt!r}")
            editor.click(force=True)
            editor.fill(prompt, force=True)
            editor.press("Enter")

            print("[STEP] LIVE MODE: waiting for blob img")
            page.wait_for_selector(LIVE_IMG_SEL, timeout=60000)
            src = page.query_selector(LIVE_IMG_SEL).get_attribute("src")
            print(f"[STEP] LIVE MODE: found blob src {src[:50]}...")

            # download blob via fetch
            data = page.evaluate("""src => fetch(src).then(r=>r.blob())
                                      .then(b=>new Response(b).arrayBuffer())""", src)
            dst = os.path.join(IMAGE_DIR, hashlib.sha256(src.encode()).hexdigest()[:8] + ".png")
            with open(dst, "wb") as f:
                f.write(bytes(data))
            print(f"[STEP] LIVE MODE: image saved to {dst}")

        except Exception as e:
            print(f"[WARN] Live mode failed: {e!r}")
            print("[STEP] FALLBACK MODE: navigating to history")
            page.goto("https://gemini.google.com/app", timeout=120000)
            page.wait_for_selector("infinite-scroller", timeout=120000)
            try:
                page.wait_for_selector(HIST_IMG_SEL, timeout=60000)
                img_el = page.query_selector_all(HIST_IMG_SEL)[-1]
                src = img_el.get_attribute("src")
                print(f"[STEP] HISTORY MODE: found history src {src[:50]}...")
                data = ctx.request.get(src).body()
                dst = os.path.join(IMAGE_DIR, hashlib.sha256(src.encode()).hexdigest()[:8] + ".png")
                with open(dst, "wb") as f:
                    f.write(data)
                print(f"[STEP] HISTORY MODE: image saved to {dst}")
            except Exception as e2:
                browser.close()
                raise RuntimeError(f"Both live and history modes failed: {e2!r}")

        # Caption
        print("[STEP] Generating caption")
        editor.click(force=True)
        editor.fill("Write a short poetic mysterious caption for that image.", force=True)
        editor.press("Enter")
        page.wait_for_timeout(7000)
        texts = page.locator("div").all_text_contents()
        caption = next(
            (t.strip() for t in reversed(texts)
             if t.strip() not in (prompt, "") and 10 < len(t.strip()) < 300),
            "A place you’ve seen in dreams."
        )
        print(f"[STEP] Caption: {caption!r}")

        browser.close()
        return dst, caption

def post_to_facebook(image_path, caption):
    print("[STEP] post_to_facebook")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(storage_state=FB_STORAGE)
        page    = ctx.new_page()

        print(f"[STEP] Navigating to Facebook Page {FB_PAGE_ID}")
        page.goto(f"https://www.facebook.com/{FB_PAGE_ID}", timeout=60000)

        print("[STEP] Opening composer")
        page.wait_for_selector("div[aria-label='Create a post']", timeout=60000)
        page.click("div[aria-label='Create a post']", force=True)

        print("[STEP] Uploading image")
        page.wait_for_selector("input[type=file']", timeout=30000)
        page.set_input_files("input[type=file']", image_path)

        print("[STEP] Filling caption")
        page.wait_for_selector("div[aria-label='Write a post']", timeout=30000)
        page.fill("div[aria-label='Write a post']", caption)

        print("[STEP] Posting")
        page.click("div[aria-label='Post']", force=True)
        page.wait_for_timeout(5000)

        browser.close()
        print("[STEP] FB post complete")

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
        post_to_facebook(img, cap)
    except Exception as e:
        print(f"[ERROR] FB post failed: {e}")
        os.remove(img)
        return

    posted.add(h)
    save_hashes(posted)
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
