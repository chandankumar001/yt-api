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
        'source_address': '0.0.0.0',
        'socket_timeout': 15,
        'ffmpeg_location': '/usr/bin/ffmpeg',
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

async def download_audio(url: str, bitrate: str = "128k"):
    """Downloads the audio from a YouTube video and converts it to MP3."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'extract_audio': True,
        'audio_format': 'mp3',
        'audio_quality': bitrate,
        'outtmpl': '%(title)s-%(id)s.%(ext)s',
        'noplaylist': True,
        'nocheckcertificate': True,
        'quiet': True,
        'source_address': '0.0.0.0',
        'socket_timeout': 15,
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

            return StreamingResponse(iterfile(), media_type="audio/mp3", headers={"Content-Disposition": f"attachment;filename={video_title}.mp3"})

    except Exception as e:
        logger.error(f"Audio download error: {e}")
        raise HTTPException(status_code=500, detail=f"Audio download failed: {e}")

async def search_youtube(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """Searches YouTube for videos using yt-dlp."""
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'entries': max_results,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.cache.store = False
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            if 'entries' in info:
                videos = []
                for entry in info['entries']:
                    videos.append({
                        'url': f"https://www.youtube.com/watch?v={entry['id']}",
                        'title': entry.get('title', 'N/A'),
                        'channel': entry.get('channel', 'N/A'),
                    })
                return videos
            else:
                return []
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")

async def get_youtube_metadata(url: str) -> Dict:
    """Extracts metadata from a YouTube video."""
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            return info_dict
    except Exception as e:
        logger.error(f"Metadata extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"Metadata extraction failed: {e}")

async def get_youtube_thumbnail(url: str, quality: str = "high") -> StreamingResponse:
    """Extracts a thumbnail from a YouTube video."""
    try:
        info_dict = await get_youtube_metadata(url)
        thumbnails = info_dict.get('thumbnails', [])
        if not thumbnails:
            raise HTTPException(status_code=404, detail="No thumbnails found")

        # Select the thumbnail based on quality
        if quality == "high":
            thumbnail_url = thumbnails[-1]['url']  # Last thumbnail is usually the highest quality
        elif quality == "medium":
            thumbnail_url = thumbnails[len(thumbnails) // 2]['url']
        else:
            thumbnail_url = thumbnails[0]['url']

        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail_url) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=500, detail="Failed to download thumbnail")
                image_bytes = await resp.read()
                return StreamingResponse(io.BytesIO(image_bytes), media_type="image/jpeg")  # Assuming JPEG, adjust if necessary

    except Exception as e:
        logger.error(f"Thumbnail extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"Thumbnail extraction failed: {e}")

async def get_youtube_subtitles(url: str, lang: str = "en", format: str = "vtt") -> Response:
    """Extracts subtitles from a YouTube video."""
    ydl_opts = {
        'writesubtitles': False,
        'writeautomaticsub': False,
        'subtitleslangs': [lang],
        'subtitlesformat': format,
        'skip_download': True,
        'quiet': True,
        'nocheckcertificate': True,
        'source_address': '0.0.0.0',
        'socket_timeout': 15,
        'encoding': 'utf-8'
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            if 'subtitles' in info_dict and lang in info_dict['subtitles']:
                subtitle_info = info_dict['subtitles'][lang]
                # Get the first subtitle URL
                subtitle_url = subtitle_info[0].get('url') if subtitle_info else None
                if subtitle_url:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(subtitle_url) as response:
                            if response.status == 200:
                                subtitle_content = await response.text()
                                return Response(subtitle_content, media_type=f"text/{format}", headers={"Content-Disposition": f"attachment;filename=subtitles.{lang}.{format}"})
                            else:
                                raise HTTPException(status_code=response.status, detail="Failed to download subtitles")
                else:
                    raise HTTPException(status_code=404, detail="No subtitle URL found")
            elif 'automatic_captions' in info_dict and lang in info_dict['automatic_captions']:
                subtitle_info = info_dict['automatic_captions'][lang]
                subtitle_url = subtitle_info[0].get('url') if subtitle_info else None
                async with aiohttp.ClientSession() as session:
                    async with session.get(subtitle_url) as response:
                        if response.status == 200:
                            subtitle_content = await response.text()
                            return Response(subtitle_content, media_type=f"text/{format}", headers={"Content-Disposition": f"attachment;filename=subtitles.{lang}.{format}"})
                        else:
                            raise HTTPException(status_code=response.status, detail="Failed to download automatic subtitles")
            else:
                raise HTTPException(status_code=404, detail="Subtitles not found")
    except Exception as e:
        logger.error(f"Subtitle extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"Subtitle extraction failed: {e}")

@app.get("/subtitles")
async def subtitles_endpoint(url: str, valid_url: bool = Depends(validate_youtube_url), lang: str = "en", format: str = "vtt"):
    """Extracts subtitles from a YouTube video."""
    return await get_youtube_subtitles(url, lang, format)

@app.get("/audio")
async def audio_endpoint(url: str, valid_url: bool = Depends(validate_youtube_url), format: str = "mp3", bitrate: str = "128k"):
    """Extracts audio from a YouTube video."""
    return await download_audio(url, format, bitrate)

@app.get("/thumbnail")
async def thumbnail_endpoint(url: str, valid_url: bool = Depends(validate_youtube_url), quality: str = "high"):
    """Extracts a thumbnail from a YouTube video."""
    return await get_youtube_thumbnail(url, quality)

@app.get("/metadata")
async def metadata_endpoint(url: str, valid_url: bool = Depends(validate_youtube_url)):
    """Extracts metadata from a YouTube video."""
    return await get_youtube_metadata(url)

@app.get("/search")
async def search_endpoint(query: str):
    """Searches YouTube for videos."""
    return await search_youtube(query)

@app.get("/download_audio")
async def download_audio_endpoint(url: str, valid_url: bool = Depends(validate_youtube_url), bitrate: str = "128k"):
    """Downloads the audio from a YouTube video."""
    return await download_audio(url, bitrate)

@app.get("/download_video")
async def download_video_endpoint(url: str, valid_url: bool = Depends(validate_youtube_url)):
    """Downloads a YouTube video."""
    return await download_video(url)

@app.get("/")
async def read_root():
    return {"Hello": "World"}