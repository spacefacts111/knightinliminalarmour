import os
import random
import time
import requests
from huggingface_hub import InferenceClient
from PIL import Image

# === Environment Variables ===
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")

# === Models (Cloud-based) ===
image_client = InferenceClient("kandinsky-community/kandinsky-2-2")

def generate_caption():
    prompt = "Write a short, poetic, mysterious quote about loneliness, time, dreams, or emptiness."
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {"inputs": prompt}

    for attempt in range(3):
        try:
            response = requests.post(
                "https://api-inference.huggingface.co/models/tiiuae/falcon-7b-instruct",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            text = response.json()[0]["generated_text"]
            break
        except Exception as e:
            print(f"[!] Caption generation failed (attempt {attempt+1}/3): {e}")
            time.sleep(5)
    else:
        raise RuntimeError("Caption generation failed after 3 attempts.")

    hashtags = [
        "#liminalspace", "#dreamcore", "#weirdcore", "#aesthetic", "#nostalgia",
        "#surreal", "#darkvibes", "#emptyplaces", "#moody", "#philosophy"
    ]
    return f"{text.strip()}\n\n{' '.join(random.sample(hashtags, 4))}"

def generate_image(prompt_text):
    for attempt in range(3):
        try:
            image = image_client.text_to_image(prompt_text, guidance_scale=4, height=768, width=768)
            image.save("post.jpg")
            return "post.jpg"
        except Exception as e:
            print(f"[!] Image generation failed (attempt {attempt+1}/3): {e}")
            time.sleep(5)
    raise RuntimeError("Image generation failed after 3 attempts.")

def post_to_facebook(image_path, caption):
    print(f"[+] Posting to Facebook: {caption}")
    with open(image_path, 'rb') as img:
        files = {'source': img}
        data = {
            'caption': caption,
            'access_token': FB_ACCESS_TOKEN
        }
        url = f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/photos"
        response = requests.post(url, files=files, data=data)
    print("[+] Facebook API Response:", response.text)

def run_once():
    prompt = random.choice([
        "a dark liminal hallway with flickering lights",
        "a surreal abandoned hotel lobby",
        "a foggy underground parking garage",
        "an empty dreamlike mall at midnight",
        "a trippy infinite stairwell, moody lighting"
    ])
    caption = generate_caption()
    image_path = generate_image(prompt)
    post_to_facebook(image_path, caption)

def main_loop():
    while True:
        run_once()
        wait_seconds = random.randint(6 * 3600, 18 * 3600)
        print(f"[+] Sleeping for {wait_seconds / 3600:.2f} hours...")
        time.sleep(wait_seconds)

# === Start Bot ===
print("[+] Running test post...")
run_once()
main_loop()
