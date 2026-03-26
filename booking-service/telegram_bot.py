"""
Telegram Bot — receives messages and triggers IRCTC booking.

Commands:
  /start  — welcome message
  /book   — start booking flow
  /status <PNR> — check PNR status
  /cancel — cancel pending booking

Or just send a natural-language message like:
  "Book tatkal from Delhi to Mumbai on 28/03/2026 3A for Raj Kumar 35 M"
"""

import os
import asyncio
import httpx
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

load_dotenv()

BOOKING_API = "http://booking-service:8080"
ALLOWED_IDS = set(
    int(i.strip()) for i in os.getenv("ALLOWED_TELEGRAM_IDS", "").split(",") if i.strip()
)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


def is_allowed(update: Update) -> bool:
    if not ALLOWED_IDS:
        return True   # No whitelist configured → allow all
    return update.effective_user.id in ALLOWED_IDS


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("🎫 Book Ticket"), KeyboardButton("📊 Check PNR")],
        [KeyboardButton("❓ Help")],
    ]
    await update.message.reply_text(
        "👋 Welcome to *IRCTC Booking Bot*!\n\n"
        "Send me a message like:\n"
        "`Book tatkal NDLS to BCT 28/03/2026 3A for Raj Kumar 35 M, Priya 30 F`\n\n"
        "Or use the buttons below.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*How to book a ticket:*\n\n"
        "Send a message like:\n"
        "`Book tatkal from Delhi to Mumbai on 28/03/2026`\n"
        "`Class: 3A, Passengers: John 30 M, Jane 28 F`\n\n"
        "*Station codes:*\n"
        "Delhi=NDLS, Mumbai=BCT, Chennai=MAS\n"
        "Bangalore=SBC, Hyderabad=SC, Kolkata=HWH\n\n"
        "*Classes:* SL, 3A, 2A, 1A, CC, EC\n"
        "*Quota:* TATKAL (default), GN, LD\n\n"
        "*Payment:* Uses your saved card on IRCTC by default.\n"
        "For UPI: add `pay via UPI yourname@okicici` to your message.",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return

    text = update.message.text.strip()

    # Skip keyboard buttons that don't contain booking info
    if text in ["🎫 Book Ticket", "❓ Help", "📊 Check PNR"]:
        if text == "❓ Help":
            await help_cmd(update, ctx)
        elif text == "🎫 Book Ticket":
            await update.message.reply_text(
                "Please send your booking details:\n"
                "`Book tatkal NDLS to BCT 28/03/2026 3A Raj Kumar 35 M`",
                parse_mode="Markdown",
            )
        return

    # Must look like a booking request
    keywords = ["book", "tatkal", "train", "ticket", "irctc"]
    if not any(kw in text.lower() for kw in keywords):
        await update.message.reply_text(
            "I only handle train bookings. Start with 'book' or 'tatkal'.\n"
            "Type /help for examples."
        )
        return

    await update.message.reply_text("🔍 Parsing your booking request...")

    # Step 1: Parse the message
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            parse_resp = await client.post(
                f"{BOOKING_API}/parse",
                json={"message": text},
            )
            parse_resp.raise_for_status()
            req_data = parse_resp.json()
        except Exception as e:
            await update.message.reply_text(
                f"❌ Could not understand your request.\n{e}\n\nType /help for examples."
            )
            return

    # Show parsed details for confirmation
    pax_lines = "\n".join(
        f"  {i+1}. {p['name']} ({p['age']}/{p['gender']})"
        for i, p in enumerate(req_data.get("passengers", []))
    )
    confirm_msg = (
        f"📋 *Booking Details:*\n"
        f"🚉 {req_data['source']} → {req_data['destination']}\n"
        f"📅 {req_data['journey_date']}\n"
        f"🎫 {req_data['travel_class']} | {req_data['quota']}\n"
        f"💳 Payment: {req_data['payment_method']}\n"
        f"👥 Passengers:\n{pax_lines}\n\n"
        f"Reply *YES* to confirm or *NO* to cancel."
    )
    await update.message.reply_text(confirm_msg, parse_mode="Markdown")

    # Store pending booking in context
    ctx.user_data["pending_booking"] = req_data
    ctx.user_data["pending_chat_id"] = str(update.effective_chat.id)


async def handle_confirmation(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    pending = ctx.user_data.get("pending_booking")

    if not pending:
        return

    if text in ["NO", "CANCEL", "NOPE"]:
        ctx.user_data.pop("pending_booking", None)
        await update.message.reply_text("❌ Booking cancelled.")
        return

    if text not in ["YES", "Y", "CONFIRM", "OK"]:
        return

    ctx.user_data.pop("pending_booking", None)
    chat_id = update.effective_chat.id
    pending["telegram_chat_id"] = str(chat_id)

    await update.message.reply_text(
        "⏳ Booking started! This may take 2-5 minutes.\n"
        "I'll send you the PNR once confirmed.\n\n"
        "⚠️ If CAPTCHA appears, the process pauses for 30s for auto-handling."
    )

    # Step 2: Trigger booking
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            book_resp = await client.post(f"{BOOKING_API}/book", json=pending)
            book_resp.raise_for_status()
            job = book_resp.json()
            await update.message.reply_text(
                f"🎯 Booking in progress (Job: `{job['job_id']}`)\n"
                f"I'll notify you when done.",
                parse_mode="Markdown",
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to start booking: {e}")


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))

    # Confirmation handler (YES/NO)
    app.add_handler(MessageHandler(
        filters.Regex(r"^(yes|no|confirm|cancel|y|n|ok|nope)$"),
        handle_confirmation,
    ))

    # General message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Telegram bot started. Listening for messages...")
    app.run_polling(poll_interval=2)


if __name__ == "__main__":
    main()
