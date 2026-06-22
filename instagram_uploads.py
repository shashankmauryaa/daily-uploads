#!/usr/bin/env python3
import os
import requests
from mimetypes import guess_type
from time import sleep
import time
import httpx
import ast
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "Chrome/114.0.0.0 Safari/537.36"
}

IMAGE_DOWNLOAD_DIR = "ig_images"
VIDEO_DOWNLOAD_DIR = "ig_videos"
os.makedirs(IMAGE_DOWNLOAD_DIR, exist_ok=True)
os.makedirs(VIDEO_DOWNLOAD_DIR, exist_ok=True)

API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
PB_SSL_REJECT = os.getenv("PB_SSL_REJECT", "True").lower() in ["true", "1", "yes"]
API_MODEL = os.getenv("API_MODEL")
username = os.getenv("IG_USERNAME")
password = os.getenv("IG_PASSWORD")

SUBREDDIT_IMAGES = "KidsAreFuckingStupid"
SUBREDDIT_VIDEOS = "ChildrenFallingOver" # "stupidkidsgettinghurt"
LIMIT_PER_FETCH = 20
TARGET_POSTS = 1
TIMEFRAME = "day"
REQUEST_DELAY = 2

def is_image_url(url):
    image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp")
    if any(url.lower().endswith(ext) for ext in image_extensions):
        return True
    mime_type, _ = guess_type(url)
    return mime_type and mime_type.startswith("image")

def is_video_url(url):
    video_extensions = (".mp4", ".mov", ".avi", ".mkv", ".webm")
    if any(url.lower().endswith(ext) for ext in video_extensions):
        return True
    mime_type, _ = guess_type(url)
    return mime_type and mime_type.startswith("video")

def fetch_subreddit_best(subreddit, limit=LIMIT_PER_FETCH, timeframe=TIMEFRAME, after=None):
    url = f"https://www.reddit.com/r/{subreddit}/best.json"
    params = {"t": timeframe, "limit": limit}
    if after:
        params["after"] = after
    print(f"[INFO] Fetching best posts from r/{subreddit}...")
    response = requests.get(url, headers=HEADERS, params=params, timeout=20)
    response.raise_for_status()
    posts = response.json()["data"]["children"]
    after = response.json()["data"].get("after")
    return posts, after

def download_image(url):
    local_filename = os.path.join(IMAGE_DOWNLOAD_DIR, os.path.basename(url.split("?")[0]))
    if os.path.exists(local_filename):
        print(f"[SKIP] Already downloaded image: {local_filename}")
        return None
    print(f"[DOWNLOAD] Downloading image from {url}")
    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(local_filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(f"[SUCCESS] Saved image to {local_filename}")
        return local_filename
    except Exception as e:
        print(f"[ERROR] Failed to download image {url}: {e}")
        if os.path.exists(local_filename):
            os.remove(local_filename)
        return None

def download_video(url, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    base_url = url if url.endswith("/") else url + "/"
    video_url = base_url + "DASH_720.mp4"
    filename = os.path.basename(urlparse(url).path).split("?")[0]
    output_path = os.path.join(output_dir, f"{filename}.mp4")
    if os.path.exists(output_path):
        print(f"[SKIP] Already downloaded video: {output_path}")
        return None
    try:
        print(f"[DOWNLOAD] Downloading video stream from: {base_url}")
        with requests.get(video_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(f"[SUCCESS] Saved video to {output_path}")
        return output_path
    except Exception as e:
        print(f"[ERROR] Failed to download video {base_url}: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return None

def download_file(url, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    local_filename = os.path.join(output_dir, os.path.basename(url.split("?")[0]))
    if os.path.exists(local_filename):
        print(f"[SKIP] Already downloaded file: {local_filename}")
        return None
    print(f"[DOWNLOAD] Downloading file from {url}")
    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(local_filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(f"[SUCCESS] Saved file to {local_filename}")
        return local_filename
    except Exception as e:
        print(f"[ERROR] Failed to download file {url}: {e}")
        if os.path.exists(local_filename):
            os.remove(local_filename)
        return None

import httpx
from openai import OpenAI

class HashtagGeneratorClient:
    def __init__(self):
        self.client = OpenAI(
            base_url=API_URL,
            api_key=API_KEY,
            http_client=httpx.Client(verify=PB_SSL_REJECT),
        )

    def generate_hashtags(self, title: str) -> str:
        prompt = (
            f"You are a hashtag generator bot for an instagram account named {username}.\n"
            "Given a post title, respond ONLY with Python code defining two variables:\n"
            "title = \"...\"\n"
            "hashtags = [list of hashtag strings]\n"
            "Do not include any other text or explanation.\n"
            "You may use hashtags like: #memes #kids #dumb #cute\n\n"
            f"Post title: \"{title}\"\n"
            "Generate now."
        )
        try:
            response = self.client.completions.create(
                model=API_MODEL,
                prompt=prompt,
                max_tokens=200,
                temperature=0.7,
            )
            text = response.choices[0].text.strip()
            hashtags = self._extract_hashtags_from_code(text)
            if not hashtags:
                raise ValueError("No hashtags extracted")
            return " ".join(hashtags)
        except Exception as e:
            print(f"[!] Hashtag generation failed: {e}")
            return "#memes #kids #dumb #cute #shorts"

    def _extract_hashtags_from_code(self, code_text: str):
        try:
            module = ast.parse(code_text)
            for node in module.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "hashtags":
                            if isinstance(node.value, (ast.List, ast.Tuple)):
                                hashtags = []
                                for elt in node.value.elts:
                                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                        hashtags.append("#" + elt.value if not elt.value.startswith("#") else elt.value)
                                return hashtags
            return []
        except Exception as e:
            print(f"[!] Failed to parse hashtags from code: {e}")
            return []

from instagrapi import Client

def post_to_instagram_photo(image_path: str, caption: str):
    if not username or not password:
        print("[ERROR] Instagram credentials not found in environment variables.")
        return
    client = Client()
    try:
        print("[INFO] Logging into Instagram (photo)...")
        client.login(username, password)
        media = client.photo_upload(image_path, caption)
        print(f"[OK] Uploaded photo to Instagram: {media.pk}")
    except Exception as e:
        print(f"[ERROR] Instagram photo upload failed: {e}")

def post_to_instagram_video(video_path: str, caption: str):
    if not username or not password:
        print("[ERROR] Instagram credentials not found in environment variables.")
        return
    client = Client()
    try:
        print("[INFO] Logging into Instagram (video)...")
        client.login(username, password)
        media = client.video_upload(video_path, caption)
        print(f"[OK] Uploaded video to Instagram: {media.pk}")
    except Exception as e:
        print(f"[ERROR] Instagram video upload failed: {e}")

def main():
    while True:
        choice = input("Enter 'i' to post images, 'v' to post videos, or 'q' to quit: ").strip().lower()
        if choice == 'q':
            print("Exiting.")
            break
        elif choice not in ('i', 'v'):
            print("Invalid input. Please enter 'i', 'v', or 'q'.")
            continue

        target = TARGET_POSTS
        downloaded_count = 0
        after = None
        hashtag_client = HashtagGeneratorClient()

        subreddit = SUBREDDIT_IMAGES if choice == 'i' else SUBREDDIT_VIDEOS

        while downloaded_count < target:
            try:
                posts, after = fetch_subreddit_best(subreddit, LIMIT_PER_FETCH, TIMEFRAME, after)
            except Exception as e:
                print(f"[ERROR] Failed to fetch posts: {e}")
                break

            if not posts:
                print("[INFO] No more posts found.")
                break

            for post in posts:
                d = post["data"]
                media_url = d.get("url_overridden_by_dest") or d.get("url")

                if choice == 'i':
                    if not media_url or not is_image_url(media_url):
                        print(f"[SKIP] Not an image URL or unsupported: {media_url}")
                        continue
                    media_path = download_image(media_url)
                    if media_path:
                        downloaded_count += 1
                        hashtags = hashtag_client.generate_hashtags(d.get("title", ""))
                        caption = f"{d.get('title', '')}\n\n{hashtags}"
                        print(f"[INFO] Caption: {caption}")
                        print("[INFO] Uploading image to Instagram...")
                        post_to_instagram_photo(media_path, caption)
                        time.sleep(2)

                elif choice == 'v':
                    if not media_url or (not is_video_url(media_url) and "v.redd.it" not in media_url):
                        print(f"[SKIP] Not a video URL or unsupported: {media_url}")
                        continue

                    if "v.redd.it" in media_url:
                        media_path = download_video(media_url, VIDEO_DOWNLOAD_DIR)
                    else:
                        media_path = download_file(media_url, VIDEO_DOWNLOAD_DIR)

                    if media_path:
                        downloaded_count += 1
                        hashtags = hashtag_client.generate_hashtags(d.get("title", ""))
                        caption = f"{d.get('title', '')}\n\n{hashtags}"
                        print(f"[INFO] Caption: {caption}")
                        print("[INFO] Uploading video to Instagram...")
                        post_to_instagram_video(media_path, caption)
                        time.sleep(2)

                if downloaded_count >= target:
                    print(f"[DONE] Reached target of {target} posts.")
                    break

            if downloaded_count >= target or not after:
                if not after:
                    print("[INFO] Reached end of subreddit posts.")
                break

            print(f"[INFO] Sleeping {REQUEST_DELAY}s before next batch...")
            sleep(REQUEST_DELAY)

if __name__ == "__main__":
    main()
