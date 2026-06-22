#!/usr/bin/env python3
import os
import requests
from mimetypes import guess_type
from time import sleep
import time
import httpx
import ast
from dotenv import load_dotenv

load_dotenv()

# ---------------- Configuration ----------------

HEADERS = {"User-Agent": "reddit-video-downloader/1.0"}
VIDEO_DOWNLOAD_DIR = "videos"
os.makedirs(VIDEO_DOWNLOAD_DIR, exist_ok=True)

SUBREDDIT = "GymMemes"
LIMIT_PER_FETCH = 20
TARGET_VIDEOS = 2
TIMEFRAME = "hour"
REQUEST_DELAY = 2

# Load OpenAI-like API credentials from .env
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
PB_SSL_REJECT = os.getenv("PB_SSL_REJECT", "True").lower() in ["true", "1", "yes"]
API_MODEL = os.getenv("API_MODEL")

# ---------------- Helper Functions ----------------

def is_video_url(url):
    video_extensions = (".mp4", ".mov", ".avi", ".wmv", ".flv", ".mkv", ".webm", ".mpg", ".mpeg")
    if any(url.lower().endswith(ext) for ext in video_extensions):
        return True
    mime_type, _ = guess_type(url)
    return mime_type and mime_type.startswith("video")

def get_reddit_video_url(post_data):
    media = post_data.get("media")
    if media and "reddit_video" in media:
        reddit_video = media["reddit_video"]
        fallback_url = reddit_video.get("fallback_url")
        if fallback_url:
            return fallback_url
    return None

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

def download_video(url):
    local_filename = os.path.join(VIDEO_DOWNLOAD_DIR, os.path.basename(url.split("?")[0]))
    if os.path.exists(local_filename):
        print(f"[SKIP] Already downloaded video: {local_filename}")
        return None
    print(f"[DOWNLOAD] Downloading video from {url}")
    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(local_filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(f"[SUCCESS] Saved video to {local_filename}")
        return local_filename
    except Exception as e:
        print(f"[ERROR] Failed to download video {url}: {e}")
        if os.path.exists(local_filename):
            os.remove(local_filename)
        return None

# ---------------- Hashtag Generator ----------------

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
            "You are a hashtag generator bot.\n"
            "Given a post title, respond ONLY with Python code defining two variables:\n"
            "title = \"...\"\n"
            "hashtags = [list of hashtag strings]\n"
            "Do not include any other text or explanation.\n\n"
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
            return "#gym #fitness #memes #workout #shorts"

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

# ---------------- YouTube Upload ----------------

def post_to_youtube(video_path: str, title: str, description: str, tags: list[str] = None):
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        print("[ERROR] google-api-python-client and oauth2client are required for YouTube upload.")
        return

    creds = Credentials.from_authorized_user_file("youtube_token.json", ["https://www.googleapis.com/auth/youtube.upload"])
    youtube = build("youtube", "v3", credentials=creds)

    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title[:90],
                "description": description,
                "tags": tags,
            },
            "status": {"privacyStatus": "public"}
        },
        media_body=MediaFileUpload(video_path)
    )
    response = request.execute()
    print(f"[OK] Uploaded to YouTube Shorts: {response.get('id')}")

# ---------------- Main ----------------

def main():
    downloaded_videos = 0
    after = None
    hashtag_client = HashtagGeneratorClient()

    while downloaded_videos < TARGET_VIDEOS:
        try:
            posts, after = fetch_subreddit_best(SUBREDDIT, LIMIT_PER_FETCH, TIMEFRAME, after)
        except Exception as e:
            print(f"[ERROR] Failed to fetch posts: {e}")
            break

        if not posts:
            print("[INFO] No more posts found.")
            break

        for post in posts:
            d = post["data"]
            reddit_video_url = get_reddit_video_url(d)

            media_url = reddit_video_url or d.get("url_overridden_by_dest") or d.get("url")
            if not media_url or not is_video_url(media_url):
                print(f"[SKIP] Not a video URL or unsupported: {media_url}")
                continue

            media_path = None
            if reddit_video_url and downloaded_videos < TARGET_VIDEOS:
                media_path = download_video(reddit_video_url)
                if media_path:
                    downloaded_videos += 1
            elif is_video_url(media_url) and downloaded_videos < TARGET_VIDEOS:
                media_path = download_video(media_url)
                if media_path:
                    downloaded_videos += 1
            else:
                continue

            if media_path:
                hashtags = hashtag_client.generate_hashtags(d.get("title", ""))
                caption = f"{d.get('title','')}\n\n{hashtags}"
                print(f"[INFO] Caption: {caption}")
                tags = [tag.lstrip("#") for tag in hashtags.split()]

                print("[INFO] Uploading video to YouTube...")
                post_to_youtube(media_path, d.get("title", ""), caption, tags=tags)
                time.sleep(2)

            if downloaded_videos >= TARGET_VIDEOS:
                print(f"[DONE] Reached target of {TARGET_VIDEOS} videos.")
                return

        if not after:
            print("[INFO] Reached end of subreddit posts.")
            break

        print(f"[INFO] Sleeping {REQUEST_DELAY}s before next batch...")
        sleep(REQUEST_DELAY)

if __name__ == "__main__":
    main()
