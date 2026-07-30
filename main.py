import os
import re
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp

app = FastAPI(title="Facebook Video Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

class ExtractRequest(BaseModel):
    url: str

def clean_filename(title: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", title)
    return cleaned.strip()[:80]

@app.get("/")
def home():
    return {"status": "success", "message": "Facebook Video Downloader API is Running"}

# ১. ওয়েবসাইট থেকে লিংক প্রসেস করার জন্য (POST Request)
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
            safe_title = clean_filename(title)
            
            # ৩টি আলাদা ফাইলের জন্য ইউনিক আইডি দেওয়া যেন টাইটেল মিলে গেলেও ওভাররাইট না হয়
            file_id = str(uuid.uuid4())[:8]

            # ৩টি কোয়ালিটির লিংক তৈরি (যা ইউজারদের জন্য প্রসেস হবে)
            return {
                "code": 0,
                "msg": "Success",
                "title": title,
                "links": {
                    "1080p": f"/get-file?url={url}&quality=1080p&name={safe_title}&id={file_id}",
                    "720p": f"/get-file?url={url}&quality=720p&name={safe_title}&id={file_id}",
                    "mp3": f"/get-file?url={url}&quality=mp3&name={safe_title}&id={file_id}"
                }
            }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ২. আসল ফাইল ডাউনলোড ও মার্জ করার রুট
@app.get("/get-file")
def get_file(url: str, quality: str, name: str, id: str):
    try:
        if quality == "mp3":
            filename = f"{name}_{id}.mp3"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            ydl_opts = {
                'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
                'outtmpl': filepath,
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
        elif quality == "720p":
            filename = f"{name}_{id}_720p.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            ydl_opts = {
                'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
                'outtmpl': filepath,
                'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
                'merge_output_format': 'mp4',
            }
        else: # 1080p
            filename = f"{name}_{id}_1080p.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            ydl_opts = {
                'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
                'outtmpl': filepath,
                'format': 'bestvideo[height>=1080]+bestaudio/bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if os.path.exists(filepath):
            return FileResponse(filepath, filename=filename, media_type="application/octet-stream")
        else:
            raise HTTPException(status_code=500, detail="File processing failed.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
