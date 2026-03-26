"""
Telegram Bot — IRCTC ticket booking (Normal + Tatkal).

Commands:
  /start   — welcome + keyboard
  /tatkal  — quick Tatkal booking prompt
  /normal  — quick Normal (General) booking prompt
  /help    — usage examples
  /status  — check a PNR

Natural-language messages:
  "Book tatkal NDLS to BCT 28/03/2026 3A for Raj Kumar 35 M"
  "Book normal ticket Delhi to Mumbai 30/03/2026 SL for Priya 28 F"
  "Book ticket NDLS to MAS 01/04/2026 3A Raj 30 M"  ← defaults to General
"""

import os
import httpx
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

load_dotenv()

BOOKING_API = os.getenv("BOOKING_API_URL", "http://booking-service:8080")
ALLOWED_IDS = set(
    int(i.strip()) for i in os.getenv("ALLOWED_TELEGRAM_IDS", "").split(",") if i.strip()
)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

QUOTA_EMOJI = {
    "TATKAL": "⚡ Tatkal",
    "PT": "💎 Premium Tatkal",
    "GN": "🎟 General",
    "LD": "👩 Ladies",
}


# ──────────────────────────────────────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────────────────────────────────────
def is_allowed(update: Update) -> bool:
    if not ALLOWED_IDS:
        return True
    return update.effective_user.id in ALLOWED_IDS


# ──────────────────────────────────────────────────────────────────────────────
# /start
# ──────────────────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("⚡ Tatkal Ticket"), KeyboardButton("🎟 Normal Ticket")],
        [KeyboardButton("📊 Check PNR"), KeyboardButton("❓ Help")],
    ]
    await update.message.reply_text(
        "👋 *Welcome to IRCTC Booking Bot!*\n\n"
        "I can book both *Normal* and *Tatkal* tickets for you.\n\n"
        "Just send a message like:\n"
        "• `Book tatkal NDLS to BCT 28/03 3A for Raj 35 M`\n"
        "• `Book normal ticket Delhi to Mumbai 30/03/2026 SL Priya 28 F`\n\n"
        "Or tap a button below to get started.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )


# ──────────────────────────────────────────────────────────────────────────────
# /tatkal — quick prompt
# ──────────────────────────────────────────────────────────────────────────────
async def tatkal_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ *Tatkal Booking*\n\n"
        "Send your booking details in one message:\n\n"
        "```\n"
        "Book tatkal [FROM] to [TO] [DD/MM/YYYY] [CLASS]\n"
        "Passengers: [Name] [Age] [M/F], ...\n"
        "```\n\n"
        "*Example:*\n"
        "`Book tatkal NDLS to BCT 28/03/2026 3A`\n"
        "`Passengers: Raj Kumar 35 M, Priya 30 F`\n\n"
        "⏰ Tatkal opens at *10:00 AM* (AC) / *11:00 AM* (Non-AC) IST, one day before travel.",
        parse_mode="Markdown",
    )


# ──────────────────────────────────────────────────────────────────────────────
# /normal — quick prompt
# ──────────────────────────────────────────────────────────────────────────────
async def normal_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎟 *Normal (General) Booking*\n\n"
        "Send your booking details in one message:\n\n"
        "```\n"
        "Book normal [FROM] to [TO] [DD/MM/YYYY] [CLASS]\n"
        "Passengers: [Name] [Age] [M/F], ...\n"
        "```\n\n"
        "*Example:*\n"
        "`Book normal ticket NDLS to BCT 02/04/2026 SL`\n"
        "`Passengers: Raj Kumar 35 Male lower berth`\n\n"
        "💡 If you don't mention tatkal or normal, I book *Normal (General)* by default.",
        parse_mode="Markdown",
    )


# ──────────────────────────────────────────────────────────────────────────────
# /help
# ──────────────────────────────────────────────────────────────────────────────
async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*📖 IRCTC Booking Bot — Help*\n\n"
        "*Tatkal booking:*\n"
        "`Book tatkal NDLS to BCT 28/03/2026 3A for Raj 35 M`\n\n"
        "*Normal (General) booking:*\n"
        "`Book normal NDLS to BCT 30/03/2026 SL for Raj 35 M, Priya 28 F`\n\n"
        "*No keyword → Normal by default:*\n"
        "`Book ticket Delhi to Mumbai 01/04/2026 2A John 40 Male`\n\n"
        "*With UPI payment:*\n"
        "`Book tatkal NDLS to BCT 28/03/2026 3A Raj 35 M pay via UPI myname@okicici`\n\n"
        "──────────────\n"
        "*Classes:* SL · 3A · 2A · 1A · CC · EC\n"
        "*Quota:* normal/general (GN) · tatkal · premium tatkal · ladies (LD)\n\n"
        "*Popular Stations:*\n"
        "Delhi=NDLS · Mumbai=BCT · Chennai=MAS\n"
        "Bangalore=SBC · Hyderabad=SC · Kolkata=HWH\n"
        "Pune=PUNE · Ahmedabad=ADI · Jaipur=JP\n\n"
        "*Payment:* Saved card on IRCTC (default) or UPI (GPay/PhonePe/Paytm)",
        parse_mode="Markdown",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main message handler
# ──────────────────────────────────────────────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return

    text = update.message.text.strip()

    # Handle keyboard button taps
    if text == "⚡ Tatkal Ticket":
        await tatkal_cmd(update, ctx)
        return
    if text == "🎟 Normal Ticket":
        await normal_cmd(update, ctx)
        return
    if text == "❓ Help":
        await help_cmd(update, ctx)
        return
    if text == "📊 Check PNR":
        await update.message.reply_text(
            "Send your PNR number:\n`/status 1234567890`", parse_mode="Markdown"
        )
        return

    # Must look like a booking request
    booking_keywords = ["book", "tatkal", "tatkaal", "train", "ticket", "irctc", "normal ticket", "general ticket"]
    if not any(kw in text.lower() for kw in booking_keywords):
        await update.message.reply_text(
            "I only handle train bookings.\n"
            "Start with *book*, *tatkal*, or *normal ticket*.\n\n"
            "Type /help for examples.",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text("🔍 Parsing your booking request...")

    # Step 1: Parse the natural-language message
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(f"{BOOKING_API}/parse", json={"message": text})
            resp.raise_for_status()
            req_data = resp.json()
        except Exception as e:
            await update.message.reply_text(
                f"❌ Could not understand your request.\n`{e}`\n\nType /help for examples.",
                parse_mode="Markdown",
            )
            return

    # Quota label for display
    quota = req_data.get("quota", "GN")
    quota_label = QUOTA_EMOJI.get(quota, quota)

    # Passenger list
    pax_lines = "\n".join(
        f"  {i+1}. {p['name']} ({p['age']}/{p['gender']})"
        f"{' — ' + p.get('berth_preference','') if p.get('berth_preference','') not in ('', 'NO PREFERENCE') else ''}"
        for i, p in enumerate(req_data.get("passengers", []))
    )

    # Payment label
    pay = req_data.get("payment_method", "SAVED_CARD")
    pay_label = f"💳 Saved Card" if pay == "SAVED_CARD" else f"📱 UPI ({req_data.get('upi_id', '')})"

    confirm_text = (
        f"📋 *Booking Summary:*\n\n"
        f"🚉 *Route:* {req_data['source']} → {req_data['destination']}\n"
        f"📅 *Date:* {req_data['journey_date']}\n"
        f"🎫 *Class:* {req_data.get('travel_class', '3A')} | *Quota:* {quota_label}\n"
        f"💳 *Payment:* {pay_label}\n"
        f"👥 *Passengers ({len(req_data.get('passengers', []))}):\n*{pax_lines}\n\n"
        f"{'⚡ *Tatkal charges apply.*' if quota == 'TATKAL' else '🎟 *General quota — no extra charges.*'}\n\n"
        f"Confirm booking?"
    )

    # Inline Yes / No buttons
    inline_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, Book Now", callback_data="confirm_yes"),
            InlineKeyboardButton("❌ Cancel", callback_data="confirm_no"),
        ]
    ])

    await update.message.reply_text(confirm_text, parse_mode="Markdown", reply_markup=inline_kb)

    # Store pending booking
    ctx.user_data["pending_booking"] = req_data
    ctx.user_data["pending_chat_id"] = str(update.effective_chat.id)


# ──────────────────────────────────────────────────────────────────────────────
# Inline button callback (Yes / No)
# ──────────────────────────────────────────────────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pending = ctx.user_data.get("pending_booking")
    if not pending:
        await query.edit_message_text("⚠️ Session expired. Please send your booking request again.")
        return

    if query.data == "confirm_no":
        ctx.user_data.pop("pending_booking", None)
        await query.edit_message_text("❌ Booking cancelled.")
        return

    if query.data != "confirm_yes":
        return

    ctx.user_data.pop("pending_booking", None)
    pending["telegram_chat_id"] = str(update.effective_chat.id)

    quota = pending.get("quota", "GN")
    quota_label = QUOTA_EMOJI.get(quota, quota)

    await query.edit_message_text(
        f"⏳ *{quota_label} booking started!*\n\n"
        f"Route: {pending['source']} → {pending['destination']} | {pending['journey_date']}\n\n"
        f"This takes 2-5 minutes. I'll send your PNR when done.\n"
        f"{'⚠️ Approve UPI payment on your GPay/PhonePe app within 2 minutes.' if pending.get('payment_method') == 'UPI' else ''}",
        parse_mode="Markdown",
    )

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(f"{BOOKING_API}/book", json=pending)
            resp.raise_for_status()
            job = resp.json()
            await update.effective_chat.send_message(
                f"🎯 Job `{job['job_id']}` queued. I'll notify you with the PNR!",
                parse_mode="Markdown",
            )
        except Exception as e:
            await update.effective_chat.send_message(f"❌ Failed to start booking: `{e}`", parse_mode="Markdown")


# ──────────────────────────────────────────────────────────────────────────────
# /status <PNR>
# ──────────────────────────────────────────────────────────────────────────────
async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Usage: `/status 1234567890`\n\nOr check at: https://www.irctc.co.in/nget/pnr-enquiry",
            parse_mode="Markdown",
        )
        return
    pnr = args[0].strip()
    await update.message.reply_text(
        f"🔍 Check PNR `{pnr}` at:\nhttps://www.irctc.co.in/nget/pnr-enquiry\n\n"
        f"Or SMS: `PNR {pnr}` to *139*",
        parse_mode="Markdown",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("tatkal", tatkal_cmd))
    app.add_handler(CommandHandler("normal", normal_cmd))
    app.add_handler(CommandHandler("status", status_cmd))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(handle_callback, pattern="^confirm_"))

    # General text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"✅ IRCTC Telegram Bot started (API: {BOOKING_API})")
    print("Listening for messages...")
    app.run_polling(poll_interval=2)


if __name__ == "__main__":
    main()
