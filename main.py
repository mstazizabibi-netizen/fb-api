import os
import re
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
import yt_dlp

app = FastAPI(title="Facebook Video Downloader API")

# ডাউনলোড ফাইল সেভ করার ফোল্ডার
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# টাইটেল থেকে অবৈধ ক্যারেক্টার সরানোর ফাংশন (যা ফাইল নেমে সমস্যা করে)
def clean_filename(title: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", title)
    return cleaned.strip()[:100]  # ফাইল নেম খুব বড় না করার জন্য ১০০ ক্যারেক্টার লিমিট

# ফাইল ডাউনলোডের পর সার্ভার থেকে কেটে ফেলার কাজ (ক্লিনআপ)
def remove_file(filepath: str):
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception as e:
            print(f"Error deleting file: {e}")

@app.get("/")
def home():
    return {"status": "success", "message": "Facebook Video Downloader API is Running"}

@app.get("/download")
def download_fb_video(
    url: str = Query(..., description="Facebook Video/Reels URL"),
    quality: str = Query("1080p", description="Options: 1080p, 720p, mp3"),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    try:
        # Base yt-dlp Options
        ydl_opts = {
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'quiet': True,
            'no_warnings': True,
        }

        # ১. আগে ভিডিওর ইনফরমেশন (টাইটেলসহ) নেওয়া
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', 'facebook_video')
            safe_title = clean_filename(video_title)

        # ২. কোয়ালিটি অনুযায়ী ডাউনলোড কনফিগারেশন সেট করা
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

        elif quality == "1080p":
            output_filename = f"{safe_title}_1080p.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, output_filename)
            # 1080p না থাকলে সর্বোচ্চ রেজোলিউশন নেবে এবং FFmpeg দিয়ে ভিডিও+অডিও মার্জ করবে
            ydl_opts.update({
                'format': 'bestvideo[height>=1080]+bestaudio/bestvideo+bestaudio/best',
                'outtmpl': filepath,
                'merge_output_format': 'mp4',
            })

        elif quality == "720p":
            output_filename = f"{safe_title}_720p.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, output_filename)
            ydl_opts.update({
                'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
                'outtmpl': filepath,
                'merge_output_format': 'mp4',
            })
        else:
            raise HTTPException(status_code=400, detail="Invalid quality selection. Choose 1080p, 720p, or mp3.")

        # ৩. ফাইল ডাউনলোড ও মার্জ শুরু
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # ফাইল ডাউনলোড সফল হয়েছে কিনা চেক
        if not os.path.exists(filepath):
             raise HTTPException(status_code=500, detail="Failed to process and download video.")

        # ৪. ইউজারকে ফাইল রেসপন্স হিসেবে পাঠানো (ডাউনলোড শেষে ব্যাকগ্রাউন্ডে ফাইল মুছে দেবে)
        background_tasks.add_task(remove_file, filepath)

        return FileResponse(
            path=filepath,
            filename=os.path.basename(filepath),
            media_type="application/octet-stream"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
