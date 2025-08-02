import os
import random
import requests
import time
from datetime import datetime, timedelta
import torch
from diffusers import StableDiffusionPipeline
from gpt4all import GPT4All

# ─── Railway env vars ─────────────────────────────────────────────────────────────
FB_APP_ID     = os.getenv("FB_APP_ID")
FB_APP_SECRET = os.getenv("FB_APP_SECRET")
FB_USER_TOKEN = os.getenv("FB_USER_TOKEN")
FB_PAGE_ID    = os.getenv("FB_PAGE_ID")

# ─── Liminal prompts ──────────────────────────────────────────────────────────────
PROMPTS = [
    "a liminal space, abandoned hallway, dreamlike, eerie atmosphere, vaporwave colors, no people",
    "empty school at night, fluorescent lights, surreal, analog horror, dark shadows, no humans",
    "dreamy hotel corridor with glowing orange lights, mysterious and peaceful, empty and endless",
    "liminal landscape, empty parking lot at sunset, nostalgic and surreal, atmospheric",
    "dark forest clearing, foggy, mystical light, no people, cinematic shadows"
]

# ─── Generate image ───────────────────────────────────────────────────────────────
def generate_image():
    pipe = StableDiffusionPipeline.from_pretrained(
        "runwayml/stable-diffusion-v1-5",
        torch_dtype=torch.float16,
        revision="fp16"
    ).to("cuda" if torch.cuda.is_available() else "cpu")
    prompt = random.choice(PROMPTS)
    img = pipe(prompt, guidance_scale=7.5).images[0]
    fname = f"liminal_{datetime.now():%Y%m%d%H%M%S}.png"
    img.save(fname)
    return fname

# ─── Generate caption ─────────────────────────────────────────────────────────────
def generate_caption():
    model = GPT4All("ggml-gpt4all-j.bin")
    text = model.generate(
        "Write a mysterious, philosophical, relatable caption for a liminal space photo:",
        max_tokens=50
    )
    return text.strip()

# ─── Refresh & fetch Page token ──────────────────────────────────────────────────
def get_page_access_token():
    # short-lived → long-lived user token
    r = requests.get(
        "https://graph.facebook.com/v18.0/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": FB_APP_ID,
            "client_secret": FB_APP_SECRET,
            "fb_exchange_token": FB_USER_TOKEN
        }
    ).json()
    user_token = r["access_token"]
    # fetch page token
    pages = requests.get(
        "https://graph.facebook.com/v18.0/me/accounts",
        params={"access_token": user_token}
    ).json()["data"]
    for p in pages:
        if p["id"] == FB_PAGE_ID:
            return p["access_token"]
    raise RuntimeError("Page token not found")

# ─── Post image to Facebook Page ─────────────────────────────────────────────────
def post_image(token, img_path, caption):
    files = {"source": open(img_path, "rb")}
    data  = {"caption": caption, "access_token": token}
    resp  = requests.post(f"https://graph.facebook.com/{FB_PAGE_ID}/photos", files=files, data=data)
    return resp.ok

# ─── Schedule logic ───────────────────────────────────────────────────────────────
def get_schedule():
    first = not os.path.exists("._ran_once")
    if first:
        open("._ran_once", "w").close()
        # immediate test post
        return [datetime.now()]
    # pick 1–4 random times over next 24h
    times = []
    now = datetime.now()
    for _ in range(random.randint(1, 4)):
        offset = timedelta(seconds=random.randint(0, 86400))
        times.append(now + offset)
    return sorted(times)

# ─── Main loop ───────────────────────────────────────────────────────────────────
def run():
    token = get_page_access_token()
    for post_time in get_schedule():
        wait = (post_time - datetime.now()).total_seconds()
        if wait > 0:
            time.sleep(wait)
        img     = generate_image()
        caption = generate_caption()
        ok      = post_image(token, img, caption)
        print(f"[{datetime.now()}] Posted: {ok}")

if __name__ == "__main__":
    run()
