"""
FastAPI service — IRCTC Booking Bot

Endpoints:
  POST /book       → trigger booking from n8n or direct API call
  POST /parse      → parse a natural-language message into BookingRequest
  GET  /status     → health check
  GET  /screenshots/{name} → serve screenshot for debugging

n8n calls /book with the structured JSON.
Telegram bot sends message → /parse → /book.
"""

import os
import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from models import BookingRequest, BookingStatus
from irctc_bot import IRCTCBot
from message_parser import parse_booking_message, format_booking_status

load_dotenv()

app = FastAPI(title="IRCTC Booking Bot", version="1.0.0")

ALLOWED_IDS = set(
    i.strip() for i in os.getenv("ALLOWED_TELEGRAM_IDS", "").split(",") if i.strip()
)

# In-memory job store (use Redis in prod)
jobs: dict[str, BookingStatus] = {}


@app.get("/status")
def health():
    return {"status": "ok", "service": "IRCTC Booking Bot"}


@app.post("/parse")
def parse_message(payload: dict) -> BookingRequest:
    """
    Parse a natural-language message into a structured BookingRequest.
    Input: {"message": "Book tatkal NDLS to BCT 28/03/2026 3A for Raj 35 M"}
    """
    message = payload.get("message", "")
    if not message:
        raise HTTPException(400, "message field is required")
    try:
        return parse_booking_message(message)
    except Exception as e:
        raise HTTPException(422, f"Could not parse booking request: {e}")


@app.post("/book")
async def book_ticket(req: BookingRequest, background_tasks: BackgroundTasks) -> dict:
    """
    Trigger IRCTC booking asynchronously.
    Returns job_id immediately; use /job/{job_id} to check result.
    """
    import uuid
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = BookingStatus(success=False, status="PROCESSING")

    background_tasks.add_task(_run_booking, job_id, req)

    return {
        "job_id": job_id,
        "message": "Booking started",
        "check_status": f"/job/{job_id}",
    }


@app.get("/job/{job_id}")
def get_job(job_id: str) -> BookingStatus:
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]


@app.post("/book-sync")
async def book_ticket_sync(req: BookingRequest) -> BookingStatus:
    """Synchronous booking — waits for completion (use for testing)."""
    bot = IRCTCBot()
    status = await bot.book(req)
    return status


@app.get("/screenshots/{filename}")
def get_screenshot(filename: str):
    path = Path("/app/screenshots") / filename
    if not path.exists():
        raise HTTPException(404, "Screenshot not found")
    return FileResponse(path)


async def _run_booking(job_id: str, req: BookingRequest):
    try:
        bot = IRCTCBot()
        status = await bot.book(req)
        jobs[job_id] = status

        # Send Telegram notification if chat_id provided
        if req.telegram_chat_id:
            await _notify_telegram(req.telegram_chat_id, format_booking_status(status, req))
    except Exception as e:
        jobs[job_id] = BookingStatus(
            success=False,
            status="FAILED",
            error=str(e),
        )


async def _notify_telegram(chat_id: str, message: str):
    import httpx
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
