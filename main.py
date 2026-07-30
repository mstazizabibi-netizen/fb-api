import os
import re
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp

app = FastAPI(title="Facebook Video Downloader API")

# CORS Middleware (সব ওয়েবসাইট থেকে অ্যাক্সেসের জন্য)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

class VideoRequest(BaseModel):
    url: str
    quality: str = "1080p"

def clean_filename(title: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", title)
    return cleaned.strip()[:100]

def remove_file(filepath: str):
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception as e:
            print(f"Error deleting file: {e}")

@app.get("/")
def home():
    return {"status": "success", "message": "Facebook Video Downloader API is Running"}

# ১. GET Method (সরাসরি ফাইল ডাউনলোডের জন্য)
@app.get("/download")
def download_fb_video_get(
    url: str = Query(..., description="Facebook Video URL"),
    quality: str = Query("1080p", description="Options: 1080p, 720p, mp3"),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    return process_download(url, quality, background_tasks)

# ২. POST Method (যাতে ৪০৫ / 405 এরর আর না আসে)
@app.post("/download")
def download_fb_video_post(
    data: VideoRequest,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    return process_download(data.url, data.quality, background_tasks)

# আসল প্রসেসিং ফাংশন
def process_download(url: str, quality: str, background_tasks: BackgroundTasks):
    try:
        ydl_opts = {
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'quiet': True,
            'no_warnings': True,
        }

        # ভিডিওর টাইটেল নেওয়া
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', 'facebook_video')
            safe_title = clean_filename(video_title)

        if quality == "mp3":
            output_filename = f"{safe_title}.mp3"
            filepath = os.path.join(DOWNLOAD_DIR, output_filename)
            ydl_opts.update({
                'format': 'bestaudio/best',
                'outtmpl': filepath,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        elif quality == "720p":
            output_filename = f"{safe_title}_720p.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, output_filename)
            ydl_opts.update({
                'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
                'outtmpl': filepath,
                'merge_output_format': 'mp4',
            })
        else:  # Default 1080p
            output_filename = f"{safe_title}_1080p.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, output_filename)
            ydl_opts.update({
                'format': 'bestvideo[height>=1080]+bestaudio/bestvideo+bestaudio/best',
                'outtmpl': filepath,
                'merge_output_format': 'mp4',
            })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if not os.path.exists(filepath):
             raise HTTPException(status_code=500, detail="Failed to process video.")

        background_tasks.add_task(remove_file, filepath)

        return FileResponse(
            path=filepath,
            filename=os.path.basename(filepath),
            media_type="application/octet-stream"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
