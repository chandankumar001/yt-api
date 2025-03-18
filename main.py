from fastapi import FastAPI, HTTPException, Depends, Response
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Optional, List, Dict
from urllib.parse import urlparse, parse_qs
import yt_dlp
import asyncio
import logging
import os
import aiohttp
import io
from aiohttp_socks import ProxyConnector
from aiohttp_socks import ProxyConnector

from stem import Signal
from stem.control import Controller

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOR_PROXY = "socks5://yt-ehc17od84-chandankumars-projects-69f89b93.vercel.app/:9050"
TOR_CONTROL_PORT = 9051

def renew_tor_ip():
    """Requests a new identity from the Tor network."""
    try:
        with Controller.from_port(port=TOR_CONTROL_PORT) as controller:
            controller.authenticate()
            controller.signal(Signal.NEWNYM)
            logger.info("Tor IP changed successfully.")
    except Exception as e:
        logger.error(f"Failed to renew Tor circuit: {e}")


async def validate_youtube_url(url: str):
    """Validates if the given URL is a valid YouTube URL."""
    try:
        parsed_url = urlparse(url)
        if parsed_url.netloc not in ("www.youtube.com", "youtube.com", "m.youtube.com", "youtu.be"):
            raise HTTPException(status_code=400, detail="Invalid YouTube URL")

        if "youtube.com" in parsed_url.netloc:
            query_params = parse_qs(parsed_url.query)
            if "v" not in query_params:
                raise HTTPException(status_code=400, detail="Invalid YouTube URL: Missing video ID")
        elif "youtu.be" in parsed_url.netloc:
            if not parsed_url.path:
                raise HTTPException(status_code=400, detail="Invalid YouTube URL: Missing video ID")
        return True
    except Exception as e:
        logger.error(f"URL validation error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid YouTube URL: {e}")

async def download_video(url: str):
    """Downloads the YouTube video in the highest available resolution."""
    ydl_opts = {
        'format': 'bestvideo*+bestaudio/best',
        'outtmpl': '%(title)s-%(id)s.%(ext)s',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'nocheckcertificate': True,
        'quiet': True,
        'proxy': TOR_PROXY,
        'source_address': '0.0.0.0',
        'socket_timeout': 15,
        'ffmpeg_location': '/opt/homebrew/bin/ffmpeg',  # Uses system-wide ffmpeg


    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            video_title = info_dict.get('title', None)
            file_name = ydl.prepare_filename(info_dict)

            ydl.download([url])

            async def iterfile():
                with open(file_name, mode="rb") as file_like:
                    yield file_like.read()

            return StreamingResponse(iterfile(), media_type="video/mp4", headers={"Content-Disposition": f"attachment;filename={video_title}.mp4"})

    except Exception as e:
        logger.error(f"Download error: {e}")
        raise HTTPException(status_code=500, detail=f"Download failed: {e}")

async def get_youtube_metadata(url: str) -> Dict:
    """Extracts metadata from a YouTube video."""
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'proxy': TOR_PROXY,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            return info_dict
    except Exception as e:
        logger.error(f"Metadata extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"Metadata extraction failed: {e}")

async def get_youtube_thumbnail(url: str, quality: str = "high") -> StreamingResponse:
    """Extracts a thumbnail from a YouTube video using Tor."""
    try:
        info_dict = await get_youtube_metadata(url)
        thumbnails = info_dict.get('thumbnails', [])
        if not thumbnails:
            raise HTTPException(status_code=404, detail="No thumbnails found")

        if quality == "high":
            thumbnail_url = thumbnails[-1]['url']
        elif quality == "medium":
            thumbnail_url = thumbnails[len(thumbnails) // 2]['url']
        else:
            thumbnail_url = thumbnails[0]['url']

        connector = ProxyConnector.from_url(TOR_PROXY)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(thumbnail_url) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=500, detail="Failed to download thumbnail")
                image_bytes = await resp.read()
                return StreamingResponse(io.BytesIO(image_bytes), media_type="image/jpeg")
    except Exception as e:
        logger.error(f"Thumbnail extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"Thumbnail extraction failed: {e}")

@app.get("/download_video")
async def download_video_endpoint(url: str, valid_url: bool = Depends(validate_youtube_url)):
    """Downloads a YouTube video."""
    renew_tor_ip()
    return await download_video(url)

@app.get("/metadata")
async def metadata_endpoint(url: str, valid_url: bool = Depends(validate_youtube_url)):
    """Extracts metadata from a YouTube video."""
    renew_tor_ip()
    return await get_youtube_metadata(url)

@app.get("/thumbnail")
async def thumbnail_endpoint(url: str, valid_url: bool = Depends(validate_youtube_url), quality: str = "high"):
    """Extracts a thumbnail from a YouTube video."""
    renew_tor_ip()
    return await get_youtube_thumbnail(url, quality)

@app.get("/")
async def read_root():
    renew_tor_ip()
    return {"Hello": "kumar"}

@app.get("/check_tor")
async def check_tor():
    renew_tor_ip()
    """Check if the request is going through the Tor network."""
    try:
        print("try")
        # connector = ProxyConnector.from_url(TOR_PROXY)
        connector = ProxyConnector.from_url(TOR_PROXY)
        print("connector=>",connector)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get("https://check.torproject.org/api/ip") as resp:
                
                if resp.status != 200:
                    raise HTTPException(status_code=500, detail="Failed to verify Tor connection")
                data = await resp.json()
                return JSONResponse(content={"Your IP": data.get("IP", "Unknown"), "Tor Status": data.get("IsTor", False)})
    except Exception as e:
        logger.error(f"Tor check error: {e}")
        raise HTTPException(status_code=500, detail=f"Tor check failed: {e}")