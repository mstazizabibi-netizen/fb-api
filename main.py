import os
import random
import logging
import asyncio
from typing import Literal, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
import yt_dlp

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("VideoDownloader")

app = FastAPI(title="Video Downloader API", version="2.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = Path("downloads").resolve()
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# কুকিজ ও প্রক্সি ফাইলের পাথ
COOKIES_FILE = "cookies.txt"
PROXIES_FILE = "proxies.txt"

app.mount("/static", StaticFiles(directory=DOWNLOAD_DIR), name="static")

class DownloadRequest(BaseModel):
    url: str
    quality: Literal["720p", "1080p"] = "1080p"


def get_random_proxy() -> Optional[str]:
    """proxies.txt ফাইলে প্রক্সি থাকলে একটি র‍্যান্ডম প্রক্সি রিটার্ন করবে, না থাকলে None দেবে"""
    if not os.path.exists(PROXIES_FILE) or os.path.getsize(PROXIES_FILE) == 0:
        return None
    try:
        with open(PROXIES_FILE, "r", encoding="utf-8") as f:
            proxies = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        if proxies:
            chosen_proxy = random.choice(proxies)
            logger.info(f"Loaded proxy: {chosen_proxy}")
            return chosen_proxy
        return None
    except Exception as e:
        logger.warning(f"Error reading proxies.txt: {e}")
        return None


def get_ydl_opts(quality: str, output_path_template: str, proxy: Optional[str] = None) -> dict:
    """yt-dlp সেটিংস কনফিগার করবে"""
    format_spec = "bestvideo[height<=720]+bestaudio/best[height<=720]/best" if quality == "720p" else "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
    
    ydl_opts = {
        'format': format_spec,
        'outtmpl': output_path_template,
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'overwrites': True,
        'concurrent_fragment_downloads': 5,
    }

    # 1. cookies.txt চেক করা
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
        ydl_opts['cookiefile'] = COOKIES_FILE
        logger.info("Using cookies.txt file for authentication.")

    # 2. proxy সংযুক্ত করা
    if proxy:
        ydl_opts['proxy'] = proxy

    return ydl_opts


def execute_download(url: str, quality: str, output_template: str, proxy: Optional[str]):
    """প্রক্সি দিয়ে চেষ্টা করবে, ফেল করলে স্বয়ংক্রিয়ভাবে নরমাল কানেকশনে ডাউনলোডে চলে যাবে"""
    if proxy:
        try:
            logger.info(f"Attempting download using Proxy: {proxy}")
            opts = get_ydl_opts(quality, output_template, proxy=proxy)
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=True)
        except Exception as e:
            logger.warning(f"Proxy failed ({e}). Falling back to Direct Connection...")

    # ডাইরেক্ট কানেকশন (No Proxy Fallback)
    logger.info("Executing download with Direct Connection...")
    opts = get_ydl_opts(quality, output_template, proxy=None)
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=True)


async def delete_file_after_delay(file_path: Path, delay_seconds: int = 1800):
    """ডাউনলোডের ৩০ মিনিট পর ফাইলটি সার্ভার থেকে ডিলিট করবে"""
    await asyncio.sleep(delay_seconds)
    try:
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Cleaned up file: {file_path.name}")
    except Exception:
        pass


@app.get("/")
def root():
    return {"status": "online", "message": "Downloader API is active."}


@app.post("/api/download")
async def download_video(payload: DownloadRequest, request: Request, background_tasks: BackgroundTasks):
    url = str(payload.url)
    quality = payload.quality

    output_template = str(DOWNLOAD_DIR / f"%(id)s_{quality}.%(ext)s")
    proxy = get_random_proxy()

    try:
        info = await run_in_threadpool(execute_download, url, quality, output_template, proxy)
        
        video_id = info.get("id", "unknown")
        video_title = info.get("title", "Video")
        thumbnail_url = info.get("thumbnail", "")
        
        expected_filename = f"{video_id}_{quality}.mp4"
        file_path = DOWNLOAD_DIR / expected_filename

        if not file_path.exists():
            matching_files = list(DOWNLOAD_DIR.glob(f"{video_id}_{quality}.*"))
            if matching_files:
                file_path = matching_files[0]
                expected_filename = file_path.name
            else:
                raise HTTPException(status_code=500, detail="File processing failed after download.")

        file_size_bytes = os.path.getsize(file_path)
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

        base_url = str(request.base_url).rstrip("/")
        download_url = f"{base_url}/static/{expected_filename}"

        background_tasks.add_task(delete_file_after_delay, file_path, 1800)

        return {
            "status": "success",
            "data": {
                "video_id": video_id,
                "title": video_title,
                "thumbnail": thumbnail_url,
                "requested_quality": quality,
                "filename": expected_filename,
                "file_size_mb": file_size_mb,
                "file_download_url": download_url
            }
        }

    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))