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

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Proxy settings (Replace with your actual proxy details)
PROXY_URL = "http://your-proxy-ip:port"

async def fetch_with_proxy(url: str) -> bytes:
    """Fetch data using a proxy."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, proxy=PROXY_URL) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=resp.status, detail="Failed to fetch data via proxy")
                return await resp.read()
    except Exception as e:
        logger.error(f"Proxy fetch error: {e}")
        raise HTTPException(status_code=500, detail="Proxy request failed")

async def get_youtube_thumbnail(url: str, quality: str = "high") -> StreamingResponse:
    """Extracts a thumbnail from a YouTube video using a proxy."""
    try:
        info_dict = await get_youtube_metadata(url)
        thumbnails = info_dict.get('thumbnails', [])
        if not thumbnails:
            raise HTTPException(status_code=404, detail="No thumbnails found")

        # Select the thumbnail based on quality
        if quality == "high":
            thumbnail_url = thumbnails[-1]['url']
        elif quality == "medium":
            thumbnail_url = thumbnails[len(thumbnails) // 2]['url']
        else:
            thumbnail_url = thumbnails[0]['url']

        image_bytes = await fetch_with_proxy(thumbnail_url)
        return StreamingResponse(io.BytesIO(image_bytes), media_type="image/jpeg")

    except Exception as e:
        logger.error(f"Thumbnail extraction error: {e}")
        raise HTTPException(status_code=500, detail="Thumbnail extraction failed")

async def get_youtube_subtitles(url: str, lang: str = "en", format: str = "vtt") -> Response:
    """Extracts subtitles from a YouTube video using a proxy."""
    ydl_opts = {
        'writesubtitles': False,
        'writeautomaticsub': False,
        'subtitleslangs': [lang],
        'subtitlesformat': format,
        'skip_download': True,
        'quiet': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)

            if 'subtitles' in info_dict and lang in info_dict['subtitles']:
                subtitle_url = info_dict['subtitles'][lang][0].get('url')
            elif 'automatic_captions' in info_dict and lang in info_dict['automatic_captions']:
                subtitle_url = info_dict['automatic_captions'][lang][0].get('url')
            else:
                raise HTTPException(status_code=404, detail="Subtitles not found")

        subtitle_content = await fetch_with_proxy(subtitle_url)
        return Response(subtitle_content, media_type=f"text/{format}")

    except Exception as e:
        logger.error(f"Subtitle extraction error: {e}")
        raise HTTPException(status_code=500, detail="Subtitle extraction failed")

@app.get("/thumbnail")
async def thumbnail_endpoint(url: str, valid_url: bool = Depends(validate_youtube_url), quality: str = "high"):
    """Extracts a thumbnail using a proxy."""
    return await get_youtube_thumbnail(url, quality)

@app.get("/subtitles")
async def subtitles_endpoint(url: str, valid_url: bool = Depends(validate_youtube_url), lang: str = "en", format: str = "vtt"):
    """Extracts subtitles using a proxy."""
    return await get_youtube_subtitles(url, lang, format)

@app.get("/")
async def read_root():
    """Root endpoint with proxy test message."""
    return {"message": "YouTube API with proxy enabled"}
