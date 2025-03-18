from fastapi import FastAPI, HTTPException, Depends, Response
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Dict
import asyncio
import logging
import os
import io
from aiohttp_socks import ProxyConnector
from stem import Signal
from stem.control import Controller
from playwright.async_api import async_playwright

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOR_PROXY = "socks5h://127.0.0.1:9050"
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


async def fetch_video_metadata(url: str) -> Dict:
    """Extracts metadata from a YouTube video using Playwright."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, proxy={"server": TOR_PROXY})
            page = await browser.new_page()
            await page.goto(url)
            title = await page.title()
            await browser.close()
        return {"title": title, "url": url}
    except Exception as e:
        logger.error(f"Metadata extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"Metadata extraction failed: {e}")


async def download_video(url: str):
    """Simulates a video download via Playwright."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, proxy={"server": TOR_PROXY})
            page = await browser.new_page()
            await page.goto(url)
            video_element = await page.query_selector("video")
            if not video_element:
                raise HTTPException(status_code=404, detail="Video not found")
            video_src = await video_element.get_attribute("src")
            await browser.close()

            if not video_src:
                raise HTTPException(status_code=500, detail="Failed to extract video source")

            return JSONResponse(content={"video_url": video_src})
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise HTTPException(status_code=500, detail=f"Download failed: {e}")


@app.get("/download_video")
async def download_video_endpoint(url: str):
    """Downloads a YouTube video."""
    return await download_video(url)


@app.get("/metadata")
async def metadata_endpoint(url: str):
    """Extracts metadata from a YouTube video."""
    return await fetch_video_metadata(url)


@app.get("/")
async def read_root():
    renew_tor_ip()
    return {"Hello": "kumar"}
