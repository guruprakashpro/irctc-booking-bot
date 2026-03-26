from pydantic import BaseModel
from typing import Optional
from enum import Enum


class TrainClass(str, Enum):
    SL = "SL"       # Sleeper
    A3 = "3A"       # AC 3 Tier
    A2 = "2A"       # AC 2 Tier
    A1 = "1A"       # AC 1st Class
    CC = "CC"       # AC Chair Car
    EC = "EC"       # Executive Chair Car
    FC = "FC"       # First Class


class Quota(str, Enum):
    TATKAL = "TATKAL"
    GENERAL = "GN"
    LADIES = "LD"
    PREMIUM_TATKAL = "PT"


class PaymentMethod(str, Enum):
    UPI = "UPI"
    SAVED_CARD = "SAVED_CARD"


class Passenger(BaseModel):
    name: str
    age: int
    gender: str   # M / F / T
    berth_preference: Optional[str] = "NO PREFERENCE"  # LB, MB, UB, SL, SU


class BookingRequest(BaseModel):
    source: str                     # Station code e.g. NDLS
    destination: str                # Station code e.g. BCT
    journey_date: str               # DD/MM/YYYY
    train_number: Optional[str] = None   # e.g. 12951 — if None, auto-pick fastest
    travel_class: TrainClass = TrainClass.A3
    quota: Quota = Quota.TATKAL
    passengers: list[Passenger]
    payment_method: PaymentMethod = PaymentMethod.SAVED_CARD
    upi_id: Optional[str] = None
    telegram_chat_id: Optional[str] = None   # for status updates


class BookingStatus(BaseModel):
    success: bool
    pnr: Optional[str] = None
    train_name: Optional[str] = None
    train_number: Optional[str] = None
    departure: Optional[str] = None
    arrival: Optional[str] = None
    fare: Optional[float] = None
    status: str = "PENDING"
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
