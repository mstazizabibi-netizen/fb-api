import os
import re
import uuid
import urllib.request
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
    expose_headers=["Content-Disposition"]
)

class VideoRequest(BaseModel):
    url: str

COOKIES_PATH = "cookies.txt"

def delete_file(filepath: str):
    if os.path.exists(filepath):
        os.remove(filepath)

def get_mb(bytes_size):
    if bytes_size and bytes_size > 0:
        return f" ({round(bytes_size / (1024 * 1024), 1)} MB)"
    return " (Size Unknown)"

def is_facebook_url(url: str) -> bool:
    fb_regex = r"(https?://)?(www\.|web\.|m\.|mobile\.)?(facebook\.com|fb\.watch|fb\.gg)/.+"
    return bool(re.match(fb_regex, url))

def sanitize_filename(title: str) -> str:
    # Ensure no illegal characters cause issues with file saving
    clean = re.sub(r'[\\/*?:"<>|]', "", title)
    return clean.strip() or "Facebook_Video"

def get_size_from_url(url: str):
    if not url: return 0
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Range': 'bytes=0-0'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            content_range = resp.headers.get('Content-Range')
            if content_range:
                return int(content_range.split('/')[-1])
            return int(resp.headers.get('Content-Length', 0))
    except:
        return 0

# 1. Endpoint to extract video information
@app.post("/api/extract")
def extract_video_info(req: VideoRequest, request: Request):
    if not is_facebook_url(req.url):
        return {"code": 1, "msg": "Only Facebook videos are supported!"}

    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
    }
    
    if os.path.exists(COOKIES_PATH):
        ydl_opts['cookiefile'] = COOKIES_PATH

    base_url = str(request.base_url).rstrip("/")
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            
        formats = info.get('formats', [])
        duration = info.get('duration', 0)
        
        hd_video_size = 0
        sd_size = 0
        audio_size = 0

        # Audio Size Calculation
        best_audio = max(
            [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none'],
            key=lambda x: x.get('abr') or 0,
            default=None
        )
        if best_audio:
            audio_size = best_audio.get('filesize') or best_audio.get('filesize_approx') or 0
            if not audio_size and best_audio.get('tbr') and duration:
                audio_size = int((best_audio.get('tbr') * 1024 / 8) * duration)
            if not audio_size and best_audio.get('url'):
                audio_size = get_size_from_url(best_audio.get('url'))

        # HD Size Calculation (1080p/720p+ - including audio)
        hd_formats = [f for f in formats if (f.get('height') or 0) >= 720]
        if hd_formats:
            best_hd = max(hd_formats, key=lambda x: x.get('height', 0))
            hd_video_size = best_hd.get('filesize') or best_hd.get('filesize_approx') or 0
            if not hd_video_size and best_hd.get('tbr') and duration:
                hd_video_size = int((best_hd.get('tbr') * 1024 / 8) * duration)
            if not hd_video_size and best_hd.get('url'):
                hd_video_size = get_size_from_url(best_hd.get('url'))
            
            if best_hd.get('acodec') == 'none':
                total_hd_size = hd_video_size + audio_size
            else:
                total_hd_size = hd_video_size
        else:
            total_hd_size = 0

        # SD Size Calculation (<= 720p)
        sd_formats = [f for f in formats if f.get('height') and f.get('height') <= 720 and f.get('acodec') != 'none']
        if sd_formats:
            best_sd = max(sd_formats, key=lambda x: x.get('height', 0))
            sd_size = best_sd.get('filesize') or best_sd.get('filesize_approx') or 0
            if not sd_size and best_sd.get('tbr') and duration:
                sd_size = int((best_sd.get('tbr') * 1024 / 8) * duration)
            if not sd_size and best_sd.get('url'):
                sd_size = get_size_from_url(best_sd.get('url'))

        title = info.get('title', 'Facebook Video')

        return {
            "code": 0,
            "msg": "success",
            "data": {
                "title": title,
                "cover": info.get('thumbnail', 'https://placehold.co/400x400?text=Facebook+Video'),
                "play": f"{base_url}/api/download_hd?url={req.url}", 
                "hd_label": "DOWNLOAD 1080p HD VIDEO" + get_mb(total_hd_size),
                "wmplay": f"{base_url}/api/download_sd?url={req.url}",
                "sd_label": "DOWNLOAD 720p SD VIDEO" + get_mb(sd_size),
                "music": f"{base_url}/api/download_audio?url={req.url}",
                "music_label": "DOWNLOAD MP3 AUDIO" + get_mb(audio_size),
            }
        }
    except Exception as e:
        return {"code": 1, "msg": str(e)}

# 2. Download and merge 1080p HD video
@app.get("/api/download_hd")
def download_hd_video(url: str, background_tasks: BackgroundTasks):
    if not is_facebook_url(url):
        raise HTTPException(status_code=400, detail="Only Facebook links allowed")

    unique_id = uuid.uuid4().hex
    output_filepath = f"hd_{unique_id}.mp4"

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': output_filepath,
        'merge_output_format': 'mp4',
        'quiet': True,
    }
    if os.path.exists(COOKIES_PATH):
        ydl_opts['cookiefile'] = COOKIES_PATH

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = sanitize_filename(info.get('title', 'Facebook_1080p_Video'))

        if os.path.exists(output_filepath):
            background_tasks.add_task(delete_file, output_filepath)
            return FileResponse(
                path=output_filepath, 
                media_type='video/mp4', 
                filename=f"{video_title}.mp4"
            )
        else:
            raise HTTPException(status_code=500, detail="HD Video file processing failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. Download 720p SD video directly
@app.get("/api/download_sd")
def download_sd_video(url: str, background_tasks: BackgroundTasks):
    if not is_facebook_url(url):
        raise HTTPException(status_code=400, detail="Only Facebook links allowed")

    unique_id = uuid.uuid4().hex
    output_filepath = f"sd_{unique_id}.mp4"

    ydl_opts = {
        'format': 'best[height<=720]/best',
        'outtmpl': output_filepath,
        'quiet': True,
    }
    if os.path.exists(COOKIES_PATH):
        ydl_opts['cookiefile'] = COOKIES_PATH

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = sanitize_filename(info.get('title', 'Facebook_720p_Video'))

        if os.path.exists(output_filepath):
            background_tasks.add_task(delete_file, output_filepath)
            return FileResponse(
                path=output_filepath, 
                media_type='video/mp4', 
                filename=f"{video_title}.mp4"
            )
        else:
            raise HTTPException(status_code=500, detail="SD Video download failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 4. Convert and download MP3 Audio
@app.get("/api/download_audio")
def download_audio_only(url: str, background_tasks: BackgroundTasks):
    if not is_facebook_url(url):
        raise HTTPException(status_code=400, detail="Only Facebook links allowed")

    unique_id = uuid.uuid4().hex
    temp_filepath = f"audio_{unique_id}"
    final_mp3_path = f"{temp_filepath}.mp3"

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': temp_filepath,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
    }
    if os.path.exists(COOKIES_PATH):
        ydl_opts['cookiefile'] = COOKIES_PATH

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            audio_title = sanitize_filename(info.get('title', 'Facebook_Audio'))

        if os.path.exists(final_mp3_path):
            background_tasks.add_task(delete_file, final_mp3_path)
            return FileResponse(
                path=final_mp3_path, 
                media_type='audio/mpeg', 
                filename=f"{audio_title}.mp3"
            )
        else:
            raise HTTPException(status_code=500, detail="Audio conversion failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
