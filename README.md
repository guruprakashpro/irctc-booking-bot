# IRCTC Booking Bot (Normal + Tatkal)

Automated Indian train ticket booking via **Telegram** using **n8n + Playwright**.

Send a message on Telegram → Bot books your ticket on IRCTC → Sends you the PNR.

Supports both **Normal (General)** and **Tatkal** quota booking.

---

## How It Works

```
You (Telegram)
      │
      │  "Book tatkal NDLS to BCT 28/03/2026 3A for Raj 35 M"
      ▼
Telegram Servers
      │
      ▼
n8n Workflow  ──→  Booking Service (FastAPI)
                         │
                         ├── Groq LLM parses your message
                         ├── Playwright opens IRCTC in Chrome
                         ├── Logs in with your credentials
                         ├── Searches trains (source → dest, date, class, quota)
                         ├── Fills passenger details
                         ├── Payment: GPay UPI or Saved Card
                         └── Sends PNR back to your Telegram ✅
```

---

## Booking Types

| You say | Quota | Extra charge |
|---------|-------|-------------|
| `Book tatkal ...` | ⚡ Tatkal | Yes (Tatkal fare) |
| `Book normal ...` | 🎟 General | No |
| `Book ticket ...` *(no keyword)* | 🎟 General | No (default) |
| `Book premium tatkal ...` | 💎 Premium Tatkal | Yes (dynamic) |

---

## Free Deployment (Oracle Cloud — ₹0/month)

### What you need (all free)

| Item | Where to get |
|------|-------------|
| Oracle Cloud account | [cloud.oracle.com](https://cloud.oracle.com) — Always Free tier |
| Telegram Bot Token | Message [@BotFather](https://t.me/BotFather) on Telegram |
| Your Telegram user ID | Message [@userinfobot](https://t.me/userinfobot) on Telegram |
| Groq API key | [console.groq.com](https://console.groq.com) — Free |
| IRCTC account | [irctc.co.in](https://www.irctc.co.in) — add a saved card |

---

## Step 1 — Create Oracle Cloud Free VM

1. Go to [cloud.oracle.com](https://cloud.oracle.com) → **Start for free**
2. Sign up (credit card needed for verification — **you will NOT be charged**)
3. After login → **Compute → Instances → Create Instance**
4. Configure:

```
Name:        irctc-bot
Image:       Ubuntu 22.04 (click Change Image)
Shape:       Ampere A1 Flex (ARM) ← click Change Shape
             OCPU count: 4
             Memory:     24 GB
             (all Always Free)
Boot volume: 50 GB
```

5. Under **Add SSH keys** → paste your public SSH key
   - On Mac/Linux: `cat ~/.ssh/id_rsa.pub` (or generate: `ssh-keygen`)
6. Click **Create**
7. Wait 2 minutes → note the **Public IP address**

---

## Step 2 — Connect to Your VM

```bash
ssh ubuntu@YOUR_ORACLE_IP
```

---

## Step 3 — Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu
newgrp docker

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Verify
docker --version
docker compose version
```

---

## Step 4 — Open Firewall Ports

**A) In Oracle Cloud web console:**

Go to your instance → **Subnet → Default Security List → Add Ingress Rules**

Add these rules:

| Source CIDR | Port | Protocol |
|-------------|------|----------|
| 0.0.0.0/0 | 22 | TCP |
| 0.0.0.0/0 | 80 | TCP |
| 0.0.0.0/0 | 5678 | TCP |
| 0.0.0.0/0 | 8080 | TCP |

**B) In your VM terminal:**

```bash
sudo iptables -I INPUT -p tcp --dport 5678 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 8080 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT

# Save so rules survive reboot
sudo apt install iptables-persistent -y
sudo netfilter-persistent save
```

---

## Step 5 — Clone the Repo

```bash
git clone https://github.com/guruprakashpro/irctc-booking-bot.git
cd irctc-booking-bot
```

---

## Step 6 — Configure Your Credentials

```bash
cp .env.example .env
nano .env
```

Fill in every value:

```env
# ── IRCTC Login ───────────────────────────────
IRCTC_USERNAME=your_irctc_username
IRCTC_PASSWORD=your_irctc_password

# CVV of your saved card on IRCTC (3 digits)
IRCTC_CVV=123

# UPI ID for GPay/PhonePe payment (optional)
UPI_ID=yourname@okicici

# ── Telegram ──────────────────────────────────
# Get from @BotFather → /newbot
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHI...

# Get from @userinfobot — only this user can trigger bookings
ALLOWED_TELEGRAM_IDS=987654321

# ── Groq (free LLM for message parsing) ───────
# Get from console.groq.com
GROQ_API_KEY=gsk_xxxxxxxxxxxx

# ── Internal config (do not change) ───────────
BOOKING_API_URL=http://booking-service:8080
```

Save: `Ctrl+O` → Enter → `Ctrl+X`

---

## Step 7 — Start the Bot

```bash
# First time: builds Docker images + downloads Playwright/Chromium (~5-10 min)
docker compose up -d --build

# Check all services are running
docker compose ps
```

Expected output:
```
NAME               STATUS    PORTS
n8n                running   0.0.0.0:5678->5678/tcp
booking-service    running   0.0.0.0:8080->8080/tcp
```

Watch logs:
```bash
docker compose logs -f
```

---

## Step 8 — Set Up n8n Workflow

1. Open in browser: `http://YOUR_ORACLE_IP:5678`
2. Login: **admin** / **admin123**
3. Go to **Workflows → Import from file**
4. Upload: `n8n-workflows/telegram-irctc-booking.json`
5. Click on **Telegram Trigger** node → Add credentials → paste your **Bot Token**
6. Click **Activate** (toggle top-right) ✅

Test it: Send `/start` to your bot on Telegram. You should get a welcome message.

---

## Step 9 — Auto-restart on Reboot

```bash
sudo nano /etc/systemd/system/irctc-bot.service
```

Paste:
```ini
[Unit]
Description=IRCTC Booking Bot
After=docker.service
Requires=docker.service

[Service]
WorkingDirectory=/home/ubuntu/irctc-booking-bot
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=always
User=ubuntu

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable irctc-bot
sudo systemctl start irctc-bot
```

---

## Step 10 — Schedule Tatkal at 10 AM IST (Optional)

Tatkal opens at **10:00 AM IST** (AC classes) exactly one day before travel.

```bash
crontab -e
```

Add this line (10:00 AM IST = 04:30 UTC):
```bash
30 4 * * * curl -s -X POST http://localhost:8080/book \
  -H "Content-Type: application/json" \
  -d "{\"source\":\"NDLS\",\"destination\":\"BCT\",\"journey_date\":\"$(date -d tomorrow +%d/%m/%Y)\",\"travel_class\":\"3A\",\"quota\":\"TATKAL\",\"payment_method\":\"SAVED_CARD\",\"passengers\":[{\"name\":\"Your Name\",\"age\":30,\"gender\":\"M\"}]}" \
  >> /home/ubuntu/tatkal.log 2>&1
```

Change `NDLS`, `BCT`, `Your Name`, `age`, `gender` to your details.

---

## How to Book via Telegram

Send any of these messages to your bot:

**Tatkal booking:**
```
Book tatkal NDLS to BCT 28/03/2026 3A for Raj Kumar 35 M
```

**Normal (General) booking:**
```
Book normal ticket Delhi to Mumbai 30/03/2026 SL for Priya 28 F
```

**Multiple passengers:**
```
Book tatkal NDLS to BCT 28/03/2026 3A
Passengers: Raj Kumar 35 M lower berth, Priya 30 F upper berth
```

**With UPI payment:**
```
Book tatkal NDLS to BCT 28/03/2026 3A Raj 35 M pay via UPI myname@okicici
```

**With specific train number:**
```
Book tatkal train 12951 NDLS to BCT 28/03/2026 3A Raj 35 M
```

Bot will show a summary → tap **✅ Yes, Book Now** to confirm.

---

## Telegram Bot Commands

| Command | Action |
|---------|--------|
| `/start` | Welcome message + keyboard |
| `/tatkal` | Tatkal booking guide |
| `/normal` | Normal booking guide |
| `/status 1234567890` | PNR status link |
| `/help` | All examples |

---

## Station Codes

| City | Code | City | Code |
|------|------|------|------|
| New Delhi | NDLS | Mumbai Central | BCT |
| Chennai | MAS | Bangalore | SBC |
| Hyderabad | SC | Kolkata/Howrah | HWH |
| Pune | PUNE | Ahmedabad | ADI |
| Jaipur | JP | Lucknow | LKO |
| Patna | PNBE | Bhopal | BPL |
| Nagpur | NGP | Kochi | ERS |
| Coimbatore | CBE | Madurai | MDU |
| Visakhapatnam | VSKP | Amritsar | ASR |

---

## Payment Methods

### Saved Card (Default)
- Bot uses the first saved card on your IRCTC account
- Enter your card's CVV in `.env` as `IRCTC_CVV`
- No action needed on your phone

### GPay / UPI
- Add `pay via UPI yourname@okicici` to your message
- Bot enters the UPI ID on IRCTC payment page
- **Approve the payment on your GPay / PhonePe / Paytm app within 2 minutes**

---

## Troubleshooting

**Bot not responding:**
```bash
docker compose ps          # check containers running
docker compose logs -f     # check for errors
```

**Booking fails at login (CAPTCHA):**
- IRCTC shows CAPTCHA at login — bot pauses 30 seconds
- For reliable Tatkal booking, integrate [2captcha.com](https://2captcha.com) (₹500/month)
- Add `TWOCAPTCHA_API_KEY=your_key` to `.env`

**Check screenshots for errors:**
```bash
ls /tmp/screenshots/       # booking step screenshots saved here
```

**Restart everything:**
```bash
docker compose restart
```

**Update the bot:**
```bash
git pull
docker compose up -d --build
```

---

## Important Notes

> ⚠️ **Tatkal Timing:** Tatkal opens at **10:00 AM IST** (AC: 1A/2A/3A/CC) and **11:00 AM IST** (Non-AC: SL/2S), exactly one day before journey date.

> ⚠️ **CAPTCHA:** IRCTC shows a CAPTCHA at every login. The bot waits 30 seconds. For Tatkal (where timing is critical), use 2captcha for auto-solving.

> ⚠️ **Security:** Never share your `.env` file. Your IRCTC password stays only on your Oracle VM.

> ⚠️ **Personal Use:** Automated IRCTC booking is against their Terms of Service. Use only for your own personal bookings.

---

## Tech Stack

| Component | Technology | Cost |
|-----------|-----------|------|
| Server | Oracle Cloud Always Free (4 CPU, 24GB RAM) | ₹0 |
| Workflow automation | n8n (self-hosted) | ₹0 |
| Web browser automation | Playwright + Chromium | ₹0 |
| Message parsing | Groq LLM (llama-3.3-70b) | ₹0 |
| API server | FastAPI + Python | ₹0 |
| Telegram interface | python-telegram-bot | ₹0 |
| Containerization | Docker Compose | ₹0 |
| **Total** | | **₹0/month** |
