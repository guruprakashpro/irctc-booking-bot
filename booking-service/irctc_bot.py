"""
IRCTC Booking Automation using Playwright.

Automates:
1. Login to IRCTC
2. Search trains (source → destination, date, class, quota)
3. Select best available Tatkal train
4. Fill passenger details
5. Proceed to payment (GPay UPI or saved card)
"""

import os
import asyncio
import time
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PWTimeout
from models import BookingRequest, BookingStatus, PaymentMethod


IRCTC_URL = "https://www.irctc.co.in/nget/train-search"
SCREENSHOTS_DIR = Path("/app/screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)


async def screenshot(page: Page, name: str):
    path = SCREENSHOTS_DIR / f"{name}_{int(time.time())}.png"
    await page.screenshot(path=str(path), full_page=False)
    return str(path)


class IRCTCBot:
    def __init__(self):
        self.username = os.getenv("IRCTC_USERNAME")
        self.password = os.getenv("IRCTC_PASSWORD")
        self.card_last4 = os.getenv("IRCTC_CARD_LAST4", "")
        self.cvv = os.getenv("IRCTC_CVV", "")
        self.upi_id = os.getenv("UPI_ID", "")

    async def book(self, req: BookingRequest) -> BookingStatus:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            try:
                status = await self._run_booking(page, req)
            except Exception as e:
                sc = await screenshot(page, "error")
                status = BookingStatus(
                    success=False,
                    status="FAILED",
                    error=str(e),
                    screenshot_path=sc,
                )
            finally:
                await browser.close()

            return status

    async def _run_booking(self, page: Page, req: BookingRequest) -> BookingStatus:
        # ── Step 1: Login ──────────────────────────────────────────────────────
        await self._login(page)

        # ── Step 2: Search train ───────────────────────────────────────────────
        train_info = await self._search_train(page, req)

        # ── Step 3: Select train & class ──────────────────────────────────────
        await self._select_train(page, req, train_info)

        # ── Step 4: Fill passengers ───────────────────────────────────────────
        await self._fill_passengers(page, req)

        # ── Step 5: Review & proceed to payment ───────────────────────────────
        fare = await self._review_booking(page)

        # ── Step 6: Payment ───────────────────────────────────────────────────
        pnr = await self._pay(page, req, fare)

        sc = await screenshot(page, "booking_success")
        return BookingStatus(
            success=True,
            pnr=pnr,
            train_name=train_info.get("name"),
            train_number=train_info.get("number"),
            departure=train_info.get("departure"),
            arrival=train_info.get("arrival"),
            fare=fare,
            status="BOOKED",
            screenshot_path=sc,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Login
    # ──────────────────────────────────────────────────────────────────────────
    async def _login(self, page: Page):
        await page.goto(IRCTC_URL, wait_until="networkidle")
        await asyncio.sleep(2)

        # Click login button (top-right)
        await page.click("a.loginText, button:has-text('LOGIN')", timeout=10000)
        await asyncio.sleep(1)

        # Fill username
        await page.fill("input[placeholder*='User Name' i], #userId", self.username)
        await asyncio.sleep(0.5)

        # Fill password
        await page.fill("input[type='password']", self.password)
        await asyncio.sleep(0.5)

        # Handle CAPTCHA — wait for user or use 2captcha service
        # For now: take screenshot and wait (manual CAPTCHA solve in 30s)
        sc = await screenshot(page, "captcha")
        print(f"CAPTCHA screenshot saved: {sc}")
        print("Waiting 30s for CAPTCHA to be solved externally...")
        await asyncio.sleep(30)   # In production: integrate 2captcha API

        # Click Sign In
        await page.click("button[type='submit']:has-text('SIGN IN'), .loginBtn")
        await page.wait_for_url("**/nget/**", timeout=20000)
        await asyncio.sleep(2)
        print("Login successful")

    # ──────────────────────────────────────────────────────────────────────────
    # Search train
    # ──────────────────────────────────────────────────────────────────────────
    async def _search_train(self, page: Page, req: BookingRequest) -> dict:
        await page.goto(IRCTC_URL, wait_until="networkidle")
        await asyncio.sleep(2)

        # From station
        from_input = page.locator("input[placeholder*='From' i]").first
        await from_input.click()
        await from_input.fill(req.source)
        await asyncio.sleep(1)
        await page.click(f"li:has-text('{req.source}')", timeout=5000)

        # To station
        to_input = page.locator("input[placeholder*='To' i]").first
        await to_input.click()
        await to_input.fill(req.destination)
        await asyncio.sleep(1)
        await page.click(f"li:has-text('{req.destination}')", timeout=5000)

        # Journey date — DD/MM/YYYY format
        date_input = page.locator("input[placeholder*='Date' i], p-calendar input").first
        await date_input.click()
        await date_input.fill(req.journey_date)
        await asyncio.sleep(0.5)

        # Class
        await page.select_option("select[formcontrolname='journeyClass'], .journeyClass select",
                                  value=req.travel_class.value)

        # Quota
        await page.select_option("select[formcontrolname='journeyQuota'], .quota select",
                                  value=req.quota.value)

        # Search
        await page.click("button:has-text('Search')")
        await page.wait_for_selector(".train-info, .train-heading, .trainName", timeout=30000)
        await asyncio.sleep(2)

        await screenshot(page, "search_results")

        # Get first available train
        train_rows = await page.query_selector_all(".train-info, .train-heading")
        if not train_rows:
            raise ValueError("No trains found for the given route/date/class")

        # If specific train number given, find it; else pick first available
        for row in train_rows:
            name = await row.inner_text()
            if req.train_number and req.train_number not in name:
                continue
            # Extract train details
            parts = name.strip().split("\n")
            return {
                "name": parts[0] if parts else "Unknown",
                "number": req.train_number or parts[1].strip() if len(parts) > 1 else "",
                "departure": "",
                "arrival": "",
                "row_element": row,
            }

        raise ValueError("Specified train not found or not available")

    # ──────────────────────────────────────────────────────────────────────────
    # Select train and class
    # ──────────────────────────────────────────────────────────────────────────
    async def _select_train(self, page: Page, req: BookingRequest, train_info: dict):
        row = train_info.get("row_element")
        if row:
            await row.click()
            await asyncio.sleep(1)

        # Click on the requested class availability cell
        class_selector = (
            f".pre-avl:has-text('{req.travel_class.value}'), "
            f"td:has-text('{req.travel_class.value}') .AVAILABLE, "
            f".booking-avl:has-text('{req.travel_class.value}')"
        )
        try:
            await page.click(class_selector, timeout=8000)
        except PWTimeout:
            raise ValueError(f"{req.travel_class.value} class not available on this train")

        await asyncio.sleep(1)

        # Click "Book Now"
        await page.click("button:has-text('Book Now'), a:has-text('Book Now')", timeout=8000)
        await page.wait_for_selector(".passenger-form, input[placeholder*='Name' i]", timeout=20000)
        await asyncio.sleep(1)
        await screenshot(page, "passenger_form")

    # ──────────────────────────────────────────────────────────────────────────
    # Fill passengers
    # ──────────────────────────────────────────────────────────────────────────
    async def _fill_passengers(self, page: Page, req: BookingRequest):
        for i, passenger in enumerate(req.passengers):
            row_prefix = f".passenger-{i+1}, .psgr-row:nth-child({i+1})"

            # Name
            name_input = page.locator(f"{row_prefix} input[placeholder*='Name' i]").first
            if not await name_input.count():
                # Try generic nth row
                name_input = page.locator("input[placeholder*='Name' i]").nth(i)
            await name_input.fill(passenger.name)

            # Age
            age_input = page.locator("input[placeholder*='Age' i]").nth(i)
            await age_input.fill(str(passenger.age))

            # Gender
            await page.select_option(
                page.locator("select[formcontrolname='passengerGender'], select.gender").nth(i),
                value=passenger.gender,
            )

            # Berth preference
            try:
                await page.select_option(
                    page.locator("select[formcontrolname='passengerBerthChoice']").nth(i),
                    value=passenger.berth_preference,
                )
            except Exception:
                pass   # berth pref not always shown

            await asyncio.sleep(0.3)

        # Check "Consider alternate trains" if shown
        try:
            await page.uncheck("input[id*='alternate']", timeout=2000)
        except Exception:
            pass

        await screenshot(page, "passengers_filled")

        # Next: go to review page
        await page.click("button:has-text('Next'), button:has-text('Continue')")
        await page.wait_for_selector(".review-details, .booking-summary", timeout=20000)
        await asyncio.sleep(1)

    # ──────────────────────────────────────────────────────────────────────────
    # Review booking and extract fare
    # ──────────────────────────────────────────────────────────────────────────
    async def _review_booking(self, page: Page) -> float:
        await screenshot(page, "review_page")
        fare = 0.0
        try:
            fare_text = await page.inner_text(".fare-details .total, .totalFare, td:has-text('Total Fare')")
            fare = float("".join(filter(lambda c: c.isdigit() or c == ".", fare_text)))
        except Exception:
            pass

        # Confirm booking details
        await page.click("button:has-text('Continue'), button:has-text('Make Payment')")
        await page.wait_for_selector(".payment-options, .pay-btn, iframe[src*='payu']", timeout=30000)
        await asyncio.sleep(2)
        return fare

    # ──────────────────────────────────────────────────────────────────────────
    # Payment
    # ──────────────────────────────────────────────────────────────────────────
    async def _pay(self, page: Page, req: BookingRequest, fare: float) -> str:
        await screenshot(page, "payment_page")

        if req.payment_method == PaymentMethod.UPI:
            await self._pay_upi(page, req.upi_id or self.upi_id)
        else:
            await self._pay_saved_card(page)

        # Wait for booking confirmation / PNR
        await page.wait_for_selector(
            ".pnr-no, .booking-confirmation, span:has-text('PNR')",
            timeout=120000,   # payment can take up to 2 min
        )
        await asyncio.sleep(2)
        await screenshot(page, "confirmation")

        # Extract PNR
        try:
            pnr_text = await page.inner_text(".pnr-no, .pnrNo")
            return "".join(filter(str.isdigit, pnr_text))[:10]
        except Exception:
            return "PENDING"

    async def _pay_upi(self, page: Page, upi_id: str):
        """Select UPI option and enter UPI ID (works for GPay / PhonePe / Paytm)."""
        try:
            await page.click("label:has-text('UPI'), div:has-text('UPI')", timeout=5000)
        except PWTimeout:
            # Try inside payment iframe
            frames = page.frames
            for frame in frames:
                try:
                    await frame.click("label:has-text('UPI')", timeout=3000)
                    break
                except Exception:
                    continue

        await asyncio.sleep(1)

        # Enter UPI ID
        upi_input = page.locator("input[placeholder*='UPI' i], input[name*='upi' i]").first
        await upi_input.fill(upi_id)
        await asyncio.sleep(0.5)

        # Verify UPI
        await page.click("button:has-text('Verify'), button:has-text('Validate')")
        await asyncio.sleep(3)

        # Submit payment — user must approve on GPay app within 2 min
        print(f"UPI payment request sent to {upi_id}. Approve on your GPay/PhonePe app!")
        await page.click("button:has-text('Pay'), button:has-text('Submit')")

    async def _pay_saved_card(self, page: Page):
        """Use the first saved card on IRCTC."""
        try:
            await page.click("label:has-text('Saved Cards'), div:has-text('Saved Cards')", timeout=5000)
        except PWTimeout:
            await page.click("label:has-text('Debit'), label:has-text('Credit')", timeout=5000)

        await asyncio.sleep(1)

        # Select first saved card
        await page.click(".saved-card:first-child, .card-item:first-child", timeout=5000)
        await asyncio.sleep(0.5)

        # Enter CVV
        cvv_input = page.locator("input[placeholder*='CVV' i], input[name*='cvv' i]").first
        await cvv_input.fill(self.cvv)
        await asyncio.sleep(0.3)

        await screenshot(page, "card_payment")
        await page.click("button:has-text('Pay'), button:has-text('Submit')")
