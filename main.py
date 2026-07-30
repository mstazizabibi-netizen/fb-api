import os
import re
import uuid
import shutil
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp

app = FastAPI(title="Facebook Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "/tmp/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

class ExtractRequest(BaseModel):
    url: str

def clean_filename(title: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", title)
    return cleaned.strip()[:50]

def cleanup_file(filepath: str):
    """ডাউনলোড শেষ হলে ফাইল ডিলিট করার ব্যাকগ্রাউন্ড টাস্ক"""
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception:
            pass

@app.get("/")
def home():
    return {"status": "success", "message": "API is online"}

@app.post("/api/extract")
def extract_fb_video(data: ExtractRequest):
    url = data.url
    
    ydl_opts = {
        'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Facebook Video')
            thumbnail = info.get('thumbnail', '')
            safe_title = clean_filename(title)
            file_id = str(uuid.uuid4())[:6]

            return {
                "status": "success",
                "title": title,
                "thumbnail": thumbnail,
                "button_labels": {
                    "1080p_hd": "Download 1080p HD Video",
                    "sd": "Download 720p SD Video",
                    "audio_mp3": "Download Audio Only (MP3)"
                },
                "links": {
                    "1080p_hd": f"/get-file?url={url}&quality=1080p&name={safe_title}&id={file_id}",
                    "sd": f"/get-file?url={url}&quality=720p&name={safe_title}&id={file_id}",
                    "audio_mp3": f"/get-file?url={url}&quality=mp3&name={safe_title}&id={file_id}"
                }
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/get-file")
def get_file(url: str, quality: str, name: str, id: str, background_tasks: BackgroundTasks):
    try:
        # ফাইল নাম ঠিক রাখা
        if quality == "mp3":
            filename = f"{name}_{id}.mp3"
        elif quality == "720p":
            filename = f"{name}_{id}_720p.mp4"
        else:
            filename = f"{name}_{id}_1080p.mp4"

        filepath = os.path.join(DOWNLOAD_DIR, filename)

        # Config for yt-dlp
        ydl_opts = {
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'outtmpl': filepath,
            'quiet': True,
            'no_warnings': True,
        }

        if quality == "mp3":
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128', # মেমোরি চাপ কমাতে ১২৮ কেবিপিএস
                }],
            })
        elif quality == "720p":
            ydl_opts.update({
                'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
                'merge_output_format': 'mp4',
            })
        else: # 1080p
            ydl_opts.update({
                'format': 'bestvideo[height>=1080]+bestaudio/bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
            })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if os.path.exists(filepath):
            # ফাইল ইউজারকে পাঠানোর পর ব্যাকগ্রাউন্ডে মুছে ফেলার ব্যবস্থা (Memory/Disk Full ক্র্যাশ আটকাবে)
            background_tasks.add_task(cleanup_file, filepath)
            return FileResponse(filepath, filename=filename, media_type="application/octet-stream")
        else:
            raise HTTPException(status_code=500, detail="Processing failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
