"""
Parse natural-language Telegram/WhatsApp messages into BookingRequest objects.
Uses Groq (free) to extract structured data from conversational input.

Supported message formats:
  "Book tatkal from NDLS to BCT on 28/03/2026 3A for 2 passengers: Raj Kumar 35 M, Priya 30 F"
  "Book train NDLS to MAS 27-03-2026 SL tatkal passenger: John 28 male"
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

SYSTEM_PROMPT = """You are a train booking assistant. Extract booking details from the user message and return ONLY valid JSON.

Output format (all fields required unless marked optional):
{
  "source": "STATION_CODE",           // IRCTC 3-5 letter station code
  "destination": "STATION_CODE",      // IRCTC 3-5 letter station code
  "journey_date": "DD/MM/YYYY",       // travel date
  "train_number": null,               // optional: specific train number
  "travel_class": "3A",              // SL, 3A, 2A, 1A, CC, EC
  "quota": "TATKAL",                 // TATKAL, GN, LD, PT
  "payment_method": "SAVED_CARD",   // UPI or SAVED_CARD
  "upi_id": null,                    // optional: UPI ID if payment_method=UPI
  "passengers": [
    {"name": "Full Name", "age": 30, "gender": "M", "berth_preference": "NO PREFERENCE"}
  ]
}

Rules:
- Convert city names to IRCTC station codes (e.g. Delhi→NDLS, Mumbai→BCT, Chennai→MAS)
- Default class=3A, quota=TATKAL if not specified
- Gender: M for male/man/gents, F for female/woman/ladies
- Berth: LB (lower), MB (middle), UB (upper), SL (side lower), SU (side upper), NO PREFERENCE
- Date format must be DD/MM/YYYY
- Return ONLY the JSON object, no explanation"""


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

    return BookingRequest(
        source=data["source"],
        destination=data["destination"],
        journey_date=data["journey_date"],
        train_number=data.get("train_number"),
        travel_class=TrainClass(data.get("travel_class", "3A")),
        quota=Quota(data.get("quota", "TATKAL")),
        passengers=passengers,
        payment_method=PaymentMethod(data.get("payment_method", "SAVED_CARD")),
        upi_id=data.get("upi_id"),
    )


def format_booking_status(status, req: BookingRequest) -> str:
    """Format booking result as a readable Telegram message."""
    if status.success:
        pax = "\n".join(f"  {i+1}. {p.name} ({p.age}/{p.gender})"
                        for i, p in enumerate(req.passengers))
        return (
            f"✅ *Ticket Booked Successfully!*\n\n"
            f"🚂 *Train:* {status.train_name} ({status.train_number})\n"
            f"📍 *Route:* {req.source} → {req.destination}\n"
            f"📅 *Date:* {req.journey_date}\n"
            f"🎫 *Class:* {req.travel_class} | *Quota:* {req.quota}\n"
            f"💰 *Fare:* ₹{status.fare:.0f}\n"
            f"🔖 *PNR:* `{status.pnr}`\n\n"
            f"👥 *Passengers:*\n{pax}\n\n"
            f"📲 Check status: https://www.irctc.co.in"
        )
    else:
        return (
            f"❌ *Booking Failed*\n\n"
            f"Route: {req.source} → {req.destination} | {req.journey_date}\n"
            f"Error: {status.error or 'Unknown error'}\n\n"
            f"Please try again or book manually at irctc.co.in"
        )
