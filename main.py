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
# the prompt box you provided:
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
    print(f"[STEP] {len(h)} loaded")
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
            c = random.choice(lines)
            print(f"[STEP] Prompt: {c!r}")
            return c
    d = "a liminal dream hallway with red lights and fog"
    print(f"[STEP] Default prompt: {d!r}")
    return d

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

        print("[STEP] Wait for container")
        page.wait_for_selector(GEMINI_CONTAINER_SEL, timeout=120000)

        print("[STEP] Extract image URL")
        src = page.evaluate(f'''
            () => {{
                const c = document.querySelector("{GEMINI_CONTAINER_SEL}");
                if (!c) return null;
                const imgs = Array.from(c.querySelectorAll("img"));
                return imgs.find(i=>i.src.includes("googleusercontent.com"))?.src || null;
            }}
        ''')
        if not src:
            raise RuntimeError("No image found")

        print(f"[STEP] URL: {src}")
        resp = ctx.request.get(src)
        resp.raise_for_status()
        data = resp.body()

        fn = os.path.basename(src.split("?",1)[0]) + ".png"
        dst = os.path.join(IMAGE_DIR, fn)
        print(f"[STEP] Save image → {dst}")
        with open(dst, "wb") as f:
            f.write(data)

        print("[STEP] Request caption")
        editor.click(force=True)
        editor.fill("Write a short poetic mysterious caption for that image.", force=True)
        editor.press("Enter")
        page.wait_for_timeout(7000)

        print("[STEP] Scrape caption")
        texts = page.locator("div").all_text_contents()
        cap = next((t.strip() for t in reversed(texts)
                    if t.strip()!=prompt and 10<len(t.strip())<300),
                   None) or "A place you’ve seen in dreams."
        print(f"[STEP] Caption: {cap!r}")

        browser.close()
        print("[STEP] Done generate")
        return dst, cap

def post_to_facebook_via_ui(img, caption):
    print("[STEP] post_to_facebook_via_ui")
    with sync_playwright() as p:
        print("[STEP] Launch FB browser")
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(storage_state=FB_STORAGE)
        page    = ctx.new_page()

        print(f"[STEP] Go to /{FB_PAGE_ID}")
        page.goto(f"https://www.facebook.com/{FB_PAGE_ID}", timeout=60000)

        print("[STEP] Click Create a post")
        page.wait_for_selector("div[aria-label='Create a post']", timeout=60000)
        page.click("div[aria-label='Create a post']", force=True)

        print("[STEP] Upload image")
        page.wait_for_selector("input[type=file']", timeout=30000)
        page.set_input_files("input[type=file']", img)

        print("[STEP] Fill caption")
        page.wait_for_selector("div[aria-label='Write a post']", timeout=30000)
        page.fill("div[aria-label='Write a post']", caption)

        print("[STEP] Submit")
        page.click("div[aria-label='Post']", force=True)
        page.wait_for_timeout(5000)

        browser.close()
        print("[STEP] FB post done")

def run_once():
    print("[STEP] run_once")
    try:
        img, cap = generate_image_and_caption()
    except Exception as e:
        print(f"[ERROR] gen failed: {e}")
        return

    h = hashlib.sha256(open(img,"rb").read()).hexdigest()
    print(f"[STEP] hash {h}")
    if h in posted:
        print("[STEP] duplicate → skip")
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
    print("[STEP] schedule_posts")
    hours = sorted(random.sample(range(24), random.randint(1,4)))
    for h in hours:
        schedule.every().day.at(f"{h:02}:00").do(run_once)
    print(f"[STEP] scheduled at {hours}")

if __name__=="__main__":
    run_once()
    schedule_posts()
    while True:
        schedule.run_pending()
        time.sleep(30)
