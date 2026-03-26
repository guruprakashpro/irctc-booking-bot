"""
Parse natural-language Telegram/WhatsApp messages into BookingRequest objects.
Uses Groq (free) to extract structured data from conversational input.

Supported message formats — Tatkal:
  "Book tatkal from NDLS to BCT on 28/03/2026 3A for Raj Kumar 35 M, Priya 30 F"
  "tatkal ticket Delhi to Mumbai 28/03/2026 sleeper 2 passengers John 30 M Jane 28 F"

Supported message formats — Normal (General):
  "Book normal ticket NDLS to BCT 30/03/2026 3A for Raj 35 M"
  "Book general train from Delhi to Chennai on 01/04/2026 SL for 1 passenger Amit 40 Male"
  "Book ticket Delhi to Pune 02/04/2026 2A Raj 35 M"   ← no keyword → defaults to General
"""

import json
import os
from groq import Groq
from models import BookingRequest, Passenger, TrainClass, Quota, PaymentMethod

STATION_ALIASES = {
    "new delhi": "NDLS", "delhi": "NDLS", "ndls": "NDLS",
    "mumbai central": "BCT", "mumbai": "BCT", "bct": "BCT",
    "chennai central": "MAS", "chennai": "MAS", "mas": "MAS",
    "bangalore": "SBC", "bengaluru": "SBC", "sbc": "SBC",
    "hyderabad": "SC", "secunderabad": "SC", "sc": "SC",
    "kolkata": "KOAA", "howrah": "HWH", "hwh": "HWH",
    "pune": "PUNE", "ahmedabad": "ADI", "adi": "ADI",
    "jaipur": "JP", "jp": "JP", "lucknow": "LKO", "lko": "LKO",
    "patna": "PNBE", "bhopal": "BPL", "nagpur": "NGP",
}

SYSTEM_PROMPT = """You are an Indian train booking assistant. Extract booking details from the user message and return ONLY valid JSON.

Output format (all fields required unless marked optional):
{
  "source": "STATION_CODE",           // IRCTC 3-5 letter station code
  "destination": "STATION_CODE",      // IRCTC 3-5 letter station code
  "journey_date": "DD/MM/YYYY",       // travel date
  "train_number": null,               // optional: specific train number e.g. "12951"
  "travel_class": "3A",              // SL, 3A, 2A, 1A, CC, EC, FC
  "quota": "GN",                     // GN (normal/general), TATKAL, LD (ladies), PT (premium tatkal)
  "payment_method": "SAVED_CARD",   // UPI or SAVED_CARD
  "upi_id": null,                    // optional: UPI ID e.g. "name@okicici" if payment_method=UPI
  "passengers": [
    {"name": "Full Name", "age": 30, "gender": "M", "berth_preference": "NO PREFERENCE"}
  ]
}

QUOTA DETECTION RULES (very important):
- User says "tatkal" or "tatkaal" → quota = "TATKAL"
- User says "premium tatkal" or "PT" → quota = "PT"
- User says "ladies" or "LD" → quota = "LD"
- User says "normal", "general", "GN", or does NOT mention any quota keyword → quota = "GN"
- Default quota is "GN" (General/Normal) — only use TATKAL when user explicitly says tatkal

STATION CODE RULES:
- Convert city names to IRCTC station codes: Delhi/New Delhi→NDLS, Mumbai→BCT, Chennai→MAS,
  Bangalore/Bengaluru→SBC, Hyderabad/Secunderabad→SC, Kolkata→KOAA, Howrah→HWH,
  Pune→PUNE, Ahmedabad→ADI, Jaipur→JP, Lucknow→LKO, Patna→PNBE, Bhopal→BPL, Nagpur→NGP,
  Kochi/Ernakulam→ERS, Coimbatore→CBE, Madurai→MDU, Visakhapatnam→VSKP, Agra→AGC,
  Varanasi→BSB, Amritsar→ASR, Chandigarh→CDG, Guwahati→GHY, Bhubaneswar→BBS

PASSENGER RULES:
- Gender: M for male/man/gents/boy, F for female/woman/ladies/girl, T for transgender
- Berth preference: LB (lower berth), MB (middle), UB (upper), SL (side lower), SU (side upper), NO PREFERENCE
- Default berth = "NO PREFERENCE"

OTHER RULES:
- Default class = "3A" if not specified
- Date format in output MUST be DD/MM/YYYY (convert from any input format)
- Return ONLY the JSON object, no explanation, no markdown"""


def normalize_station(name: str) -> str:
    key = name.lower().strip()
    return STATION_ALIASES.get(key, name.upper())


def parse_booking_message(message: str) -> BookingRequest:
    """Use Groq LLM to parse natural-language booking request."""
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        temperature=0.1,
        max_tokens=800,
        response_format={"type": "json_object"},
    )

    data = json.loads(response.choices[0].message.content)

    # Normalize station codes
    data["source"] = normalize_station(data.get("source", ""))
    data["destination"] = normalize_station(data.get("destination", ""))

    # Build passengers
    passengers = [
        Passenger(
            name=p["name"],
            age=int(p["age"]),
            gender=p["gender"].upper()[0],
            berth_preference=p.get("berth_preference", "NO PREFERENCE"),
        )
        for p in data.get("passengers", [])
    ]

    # Fallback quota detection from raw message text (safety net)
    raw_lower = message.lower()
    parsed_quota = data.get("quota", "GN")
    if parsed_quota not in ("TATKAL", "PT", "LD", "GN"):
        parsed_quota = "GN"
    # Override: if LLM returned GN but message has tatkal keyword, force TATKAL
    if parsed_quota == "GN" and any(k in raw_lower for k in ["tatkal", "tatkaal"]):
        parsed_quota = "TATKAL"
    # Override: if LLM returned TATKAL but message has normal/general keyword, force GN
    if parsed_quota == "TATKAL" and any(k in raw_lower for k in ["normal ticket", "general ticket", "normal train", "general quota"]):
        parsed_quota = "GN"

    return BookingRequest(
        source=data["source"],
        destination=data["destination"],
        journey_date=data["journey_date"],
        train_number=data.get("train_number"),
        travel_class=TrainClass(data.get("travel_class", "3A")),
        quota=Quota(parsed_quota),
        passengers=passengers,
        payment_method=PaymentMethod(data.get("payment_method", "SAVED_CARD")),
        upi_id=data.get("upi_id"),
    )


QUOTA_LABELS = {
    "TATKAL": "⚡ Tatkal",
    "PT": "💎 Premium Tatkal",
    "GN": "🎟 General (Normal)",
    "LD": "👩 Ladies",
}


def format_booking_status(status, req: BookingRequest) -> str:
    """Format booking result as a readable Telegram message."""
    quota_label = QUOTA_LABELS.get(req.quota.value if hasattr(req.quota, "value") else req.quota, req.quota)

    if status.success:
        pax = "\n".join(
            f"  {i+1}. {p.name} ({p.age}/{p.gender})"
            for i, p in enumerate(req.passengers)
        )
        return (
            f"✅ *Ticket Booked Successfully!*\n\n"
            f"🚂 *Train:* {status.train_name} ({status.train_number})\n"
            f"📍 *Route:* {req.source} → {req.destination}\n"
            f"📅 *Date:* {req.journey_date}\n"
            f"🎫 *Class:* {req.travel_class} | *Quota:* {quota_label}\n"
            f"💰 *Fare:* ₹{status.fare:.0f}\n"
            f"🔖 *PNR:* `{status.pnr}`\n\n"
            f"👥 *Passengers:*\n{pax}\n\n"
            f"📲 Check PNR: https://www.irctc.co.in/nget/pnr-enquiry"
        )
    else:
        return (
            f"❌ *Booking Failed*\n\n"
            f"Route: {req.source} → {req.destination} | {req.journey_date}\n"
            f"Quota: {quota_label}\n"
            f"Error: `{status.error or 'Unknown error'}`\n\n"
            f"Please try again or book manually at irctc.co.in"
        )
