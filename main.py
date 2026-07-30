import os
import uuid
import urllib.request
import re
import urllib.parse
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class VideoRequest(BaseModel):
    url: str

def delete_file(filepath: str):
    if os.path.exists(filepath):
        os.remove(filepath)

def get_mb(bytes_size):
    if bytes_size and bytes_size > 0:
        return f" ({round(bytes_size / (1024 * 1024), 1)} MB)"
    return " (Size Unknown)"

# এবার ১ বাইট ডেটা চেয়ে আসল সাইজ বের করার নিনজা টেকনিক!
def get_size_from_url(url: str):
    if not url: return 0
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Range': 'bytes=0-0'  # আমরা শুধু প্রথম বাইট চাচ্ছি
        }
        req = urllib.request.Request(url, headers=headers) # GET রিকোয়েস্ট যাবে
        with urllib.request.urlopen(req, timeout=5) as resp:
            # ফেসবুক বলবে: "bytes 0-0/4567890", আমরা শেষের আসল সাইজটা কেটে নেব
            content_range = resp.headers.get('Content-Range')
            if content_range:
                return int(content_range.split('/')[-1])
            return int(resp.headers.get('Content-Length', 0))
    except:
        return 0

# ১. শুধুমাত্র ডেটা এবং লিংক বের করার এন্ডপয়েন্ট
@app.post("/api/extract")
def extract_video_info(req: VideoRequest, request: Request):
    ydl_opts = {'quiet': True, 'noplaylist': True}
    base_url = str(request.base_url).rstrip("/")
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            
        formats = info.get('formats', [])
        sd_url, audio_url, hd_url = "", "", ""
        sd_size, audio_size, hd_video_size = 0, 0, 0
        
        duration = info.get('duration', 0)
        
        for f in formats:
            if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                if not audio_url or f.get('abr', 0) > 100:
                    audio_url = f.get('url')
                    current_size = f.get('filesize') or f.get('filesize_approx')
                    if current_size:
                        audio_size = current_size
                    elif f.get('tbr') and duration:
                        audio_size = int((f.get('tbr') * 1024 / 8) * duration)
                    
            if f.get('height') is not None and f.get('height') <= 720 and f.get('acodec') != 'none':
                sd_url = f.get('url')
                current_size = f.get('filesize') or f.get('filesize_approx')
                if current_size:
                    sd_size = current_size
                elif f.get('tbr') and duration:
                    sd_size = int((f.get('tbr') * 1024 / 8) * duration)
                
            if f.get('height') is not None and f.get('height') >= 720 and f.get('vcodec') != 'none':
                hd_url = f.get('url')
                current_size = f.get('filesize') or f.get('filesize_approx')
                if current_size:
                    hd_video_size = current_size
                elif f.get('tbr') and duration:
                    hd_video_size = int((f.get('tbr') * 1024 / 8) * duration)

        if sd_url and not sd_size:
            sd_size = get_size_from_url(sd_url)
        if audio_url and not audio_size:
            audio_size = get_size_from_url(audio_url)
        if hd_url and not hd_video_size:
            hd_video_size = get_size_from_url(hd_url)

        total_hd_size = hd_video_size + audio_size

        # --- নতুন যোগ করা অংশ (ফাইলের নাম ঠিক করার জন্য) ---
        raw_title = info.get('title', 'Facebook_Video')
        clean_title = re.sub(r'[\\/*?:"<>|]', "", raw_title).strip()
        if not clean_title:
            clean_title = "Facebook_Video"
        
        encoded_title = urllib.parse.quote(clean_title)
        encoded_url = urllib.parse.quote(req.url)
        # --------------------------------------------------

        return {
            "code": 0,
            "msg": "success",
            "data": {
                "title": info.get('title', 'Facebook Video'),
                "cover": info.get('thumbnail', 'https://placehold.co/400x400?text=Facebook+Video'),
                
                "play": f"{base_url}/api/download_hd?url={encoded_url}&title={encoded_title}_HD", 
                "hd_label": "DOWNLOAD HD VIDEO" + get_mb(total_hd_size),
                
                "wmplay": f"{base_url}/api/download_sd?url={encoded_url}&title={encoded_title}_SD",
                "sd_label": "DOWNLOAD SD VIDEO" + get_mb(sd_size),
                
                "music": f"{base_url}/api/download_audio?url={encoded_url}&title={encoded_title}_Audio",
                "music_label": "DOWNLOAD AUDIO ONLY" + get_mb(audio_size),
            }
        }
    except Exception as e:
        return {"code": 1, "msg": str(e)}

# ২. HD ভিডিও মার্জ করে ইউজারকে দেওয়ার এন্ডপয়েন্ট
@app.get("/api/download_hd")
def download_hd_video(url: str, background_tasks: BackgroundTasks, title: str = "Facebook_1080p_Video"):
    filename = f"HD_Video_{uuid.uuid4().hex}.mp4"
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': filename,
        'merge_output_format': 'mp4',
        'quiet': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        if os.path.exists(filename):
            background_tasks.add_task(delete_file, filename)
            # এখানে filename এ title বসানো হয়েছে
            return FileResponse(filename, media_type='video/mp4', filename=f"{title}.mp4")
        else:
            raise HTTPException(status_code=500, detail="Failed to merge HD video")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ৩. SD ভিডিও ডাউনলোড করার এন্ডপয়েন্ট
@app.get("/api/download_sd")
def download_sd_video(url: str, background_tasks: BackgroundTasks, title: str = "Facebook_720p_Video"):
    filename = f"SD_Video_{uuid.uuid4().hex}.mp4"
    ydl_opts = {
        'format': 'best[height<=720][ext=mp4]/best[ext=mp4]/best',
        'outtmpl': filename,
        'quiet': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        if os.path.exists(filename):
            background_tasks.add_task(delete_file, filename)
            # এখানে filename এ title বসানো হয়েছে
            return FileResponse(filename, media_type='video/mp4', filename=f"{title}.mp4")
        else:
            raise HTTPException(status_code=500, detail="Failed to download SD video")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ৪. শুধুমাত্র অডিও ডাউনলোড করার এন্ডপয়েন্ট
@app.get("/api/download_audio")
def download_audio_only(url: str, background_tasks: BackgroundTasks, title: str = "Facebook_Audio"):
    filename = f"Audio_{uuid.uuid4().hex}.m4a"
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': filename,
        'quiet': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        if os.path.exists(filename):
            background_tasks.add_task(delete_file, filename)
            # এখানে filename এ title বসানো হয়েছে
            return FileResponse(filename, media_type='audio/mp4', filename=f"{title}.m4a")
        else:
            raise HTTPException(status_code=500, detail="Failed to download audio")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
