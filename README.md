# IRCTC Tatkal Booking Bot

Automated train ticket booking via **Telegram** using **n8n** + **Playwright**.

Send a message on Telegram → Bot books your Tatkal ticket on IRCTC → Notifies you with PNR.

## Architecture

```
Telegram Message
       │
       ▼
   n8n Workflow  (parse → confirm → trigger)
       │
       ▼
 Booking Service  (FastAPI + Playwright)
       │
       ├── Login to IRCTC
       ├── Search trains (source → dest, date, class)
       ├── Select Tatkal quota + fill passengers
       ├── Payment: GPay UPI or Saved Card
       └── Extract PNR → notify Telegram
```

## Quick Start

### 1. Prerequisites

- Docker + Docker Compose
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- IRCTC account with saved card (or UPI ID)
- Groq API key (free at [console.groq.com](https://console.groq.com))

### 2. Setup

```bash
git clone https://github.com/guruprakashpro/irctc-booking-bot
cd irctc-booking-bot

# Copy environment file and fill in your details
cp .env.example .env
nano .env
```

Fill in `.env`:
```
IRCTC_USERNAME=your_irctc_username
IRCTC_PASSWORD=your_irctc_password
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
IRCTC_CVV=123
UPI_ID=yourname@okicici
GROQ_API_KEY=gsk_...
ALLOWED_TELEGRAM_IDS=your_telegram_user_id
```

> Get your Telegram user ID: message [@userinfobot](https://t.me/userinfobot)

### 3. Start Services

```bash
docker-compose up -d
```

- **n8n**: http://localhost:5678 (admin / admin123)
- **Booking API**: http://localhost:8080

### 4. Setup n8n Workflow

1. Open http://localhost:5678
2. Go to **Workflows → Import**
3. Import `n8n-workflows/telegram-irctc-booking.json`
4. Add your Telegram Bot credentials in n8n
5. Activate the workflow

### 5. Start Telegram Bot (alternative to n8n)

```bash
cd booking-service
pip install -r requirements.txt
python telegram_bot.py
```

---

## How to Book

Send a message to your bot:

```
Book tatkal from Delhi to Mumbai on 28/03/2026 3A for Raj Kumar 35 M
```

```
Book tatkal NDLS to BCT 28/03/2026 class 3A passengers: John 30 M, Jane 28 F
```

```
Book train 12951 from New Delhi to Mumbai Central 29/03/2026 2A tatkal
passenger 1: Arjun Sharma 32 Male lower berth
passenger 2: Meera Sharma 30 Female
pay via UPI myname@okicici
```

The bot will:
1. Parse your message → show booking summary
2. Wait for your confirmation (YES/NO)
3. Open IRCTC, login, search trains
4. Fill passenger details, select Tatkal
5. Complete payment (GPay UPI or saved card)
6. Send you the PNR number

---

## Payment Methods

### Saved Card (Default)
- Uses the first saved card on your IRCTC account
- Enter CVV in `.env` as `IRCTC_CVV`

### GPay / UPI
Add to your message: `pay via UPI yourname@okicici`

- Bot enters UPI ID on IRCTC payment page
- A payment request is sent to your GPay/PhonePe/Paytm app
- **You must approve it within 2 minutes**

---

## Station Codes

| City | Code |
|------|------|
| New Delhi | NDLS |
| Mumbai Central | BCT |
| Chennai Central | MAS |
| Bangalore | SBC |
| Hyderabad / Secunderabad | SC |
| Kolkata / Howrah | HWH |
| Pune | PUNE |
| Ahmedabad | ADI |
| Jaipur | JP |
| Lucknow | LKO |

---

## API Reference

### Parse message
```bash
curl -X POST http://localhost:8080/parse \
  -H "Content-Type: application/json" \
  -d '{"message": "Book tatkal NDLS to BCT 28/03/2026 3A for Raj 35 M"}'
```

### Book directly
```bash
curl -X POST http://localhost:8080/book \
  -H "Content-Type: application/json" \
  -d '{
    "source": "NDLS",
    "destination": "BCT",
    "journey_date": "28/03/2026",
    "travel_class": "3A",
    "quota": "TATKAL",
    "payment_method": "SAVED_CARD",
    "passengers": [{"name": "Raj Kumar", "age": 35, "gender": "M"}]
  }'
```

### Check job status
```bash
curl http://localhost:8080/job/{job_id}
```

---

## Important Notes

⚠️ **CAPTCHA**: IRCTC shows CAPTCHA at login. The bot pauses 30 seconds.
For production, integrate [2captcha](https://2captcha.com) (`TWOCAPTCHA_API_KEY` in `.env`).

⚠️ **Tatkal Timing**: Tatkal opens at 10:00 AM (AC) and 11:00 AM (non-AC) IST, one day before travel. Schedule your message accordingly.

⚠️ **Security**: Never share your `.env` file. The IRCTC password is stored only in your local `.env`.

⚠️ **Terms of Service**: Automated booking on IRCTC is against their ToS. Use responsibly for personal bookings only.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Workflow automation | n8n |
| Message interface | Telegram Bot API |
| Web automation | Playwright (Chromium) |
| API server | FastAPI |
| Message parsing | Groq LLM (llama-3.3-70b) |
| Containerization | Docker Compose |
