#!/usr/bin/env python3
import os
import requests
from mimetypes import guess_type
from time import sleep
import time
import httpx
import ast
from dotenv import load_dotenv
from openai import OpenAI
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()

# ---------------- Configuration ----------------

HEADERS = {"User-Agent": "script:daily-uploads-bot:v1.0 (by /u/shashank_uploader)"}
VIDEO_DOWNLOAD_DIR = "videos"
os.makedirs(VIDEO_DOWNLOAD_DIR, exist_ok=True)

SUBREDDIT = "GymMemes"
LIMIT_PER_FETCH = 20
TARGET_VIDEOS = 2
TIMEFRAME = "week"
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

import re
import html
import subprocess

def fetch_subreddit_best(subreddit, limit=LIMIT_PER_FETCH, timeframe=TIMEFRAME, after=None):
    url = f"https://old.reddit.com/r/{subreddit}/top/?sort=top&t={timeframe}&limit={limit}"
    if after:
        url += f"&after={after}&count={limit}"
    
    print(f"[INFO] Fetching top posts from r/{subreddit} via curl HTML scraping...")
    
    # We use curl because python 'requests' has a known TLS fingerprint that Reddit often blocks (403)
    curl_cmd = [
        "curl", "-s", url,
        "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "-H", "Accept-Language: en-US,en;q=0.9"
    ]
    
    result = subprocess.run(curl_cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout:
        print("[ERROR] Failed to fetch HTML via curl")
        return [], None
        
    page_html = result.stdout
    
    # Extract posts using regex
    # Match standard reddit 'thing' divs to get data-url and title
    pattern = r'<div class="[^"]*?thing[^"]*?"[ \n]+.*?data-url="(.*?)".*?data-event-action="title".*?>(.*?)</a>'
    matches = re.findall(pattern, page_html, re.DOTALL)
    
    # Try to extract the 'next' page id
    next_page_match = re.search(r'class="next-button".*?href="[^"]*?after=([^"&]+)', page_html)
    next_after = next_page_match.group(1) if next_page_match else None
    
    posts = []
    for media_url, title in matches:
        title = html.unescape(title)
        
        # Handle relative URLs
        if media_url.startswith("/"):
            media_url = "https://www.reddit.com" + media_url
            
        # Re-construct a dictionary matching the old JSON format
        posts.append({
            "data": {
                "title": title,
                "url": media_url,
                "url_overridden_by_dest": media_url
            }
        })
        
    return posts, next_after

def download_video(url):
    from urllib.parse import urlparse
    import subprocess
    base_url = url if url.endswith("/") else url + "/"
    if "v.redd.it" in url:
        download_url = base_url + "DASH_720.mp4"
    else:
        download_url = url
    
    filename = os.path.basename(urlparse(url).path).split("?")[0]
    local_filename = os.path.join(VIDEO_DOWNLOAD_DIR, f"{filename}.mp4")
    
    if os.path.exists(local_filename):
        print(f"[SKIP] Already downloaded video: {local_filename}")
        return local_filename
        
    print(f"[DOWNLOAD] Downloading video from {download_url} using curl")
    try:
        curl_cmd = [
            "curl", "-s", "-L", download_url,
            "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "-o", local_filename
        ]
        result = subprocess.run(curl_cmd)
        if result.returncode == 0 and os.path.exists(local_filename) and os.path.getsize(local_filename) > 0:
            print(f"[SUCCESS] Saved video to {local_filename}")
            return local_filename
        else:
            print(f"[ERROR] Failed to download video {download_url}: curl returned {result.returncode}")
            if os.path.exists(local_filename):
                os.remove(local_filename)
            return None
    except Exception as e:
        print(f"[ERROR] Exception during video download {download_url}: {e}")
        if os.path.exists(local_filename):
            os.remove(local_filename)
        return None

# ---------------- Hashtag Generator ----------------

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
    # Credentials and API imports moved to the top of the file

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
            media_url = d.get("url_overridden_by_dest") or d.get("url")
            if not media_url or (not is_video_url(media_url) and "v.redd.it" not in media_url):
                print(f"[SKIP] Not a video URL or unsupported: {media_url}")
                continue

            media_path = None
            if downloaded_videos < TARGET_VIDEOS:
                media_path = download_video(media_url)
                if media_path:
                    downloaded_videos += 1

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
