from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import numpy as np
from datetime import date

app = FastAPI()

# middleware Allows the Frontend to call API
app.add_middleware(  
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PriceData(BaseModel):
    # Separate platform prices so we don't mix them
    amazon_prices: list[float]   # ordered oldest → newest, one per day
    flipkart_prices: list[float] # ordered oldest → newest, one per day
    current_price: float
    lowest_ever: float
    highest_ever: float
    # Optional: days until next known sale (0 = sale is on, None = unknown)
    days_to_next_sale: Optional[int] = None

@app.get("/")
def home():
    return {"message": "BuyWise ML API running"}

@app.post("/predict")
def predict(data: PriceData):

    # ── 1. BUILD A CLEAN COMBINED SERIES ──────────────────────
    # Average Amazon + Flipkart per day where both exist,
    # otherwise use whichever is available
    amz = np.array(data.amazon_prices, dtype=float)
    fk  = np.array(data.flipkart_prices, dtype=float)

    # Align lengths
    min_len = min(len(amz), len(fk))
    if min_len == 0:
        return _fallback(data.current_price, data.lowest_ever)

    amz = amz[-min_len:]
    fk  = fk[-min_len:]
    combined = (amz + fk) / 2  # daily average of both platforms

    # ── 2. SMOOTH WITH 7-DAY MOVING AVERAGE ──────────────────
    window = min(7, len(combined))
    smoothed = np.convolve(combined, np.ones(window) / window, mode='valid')

    if len(smoothed) < 5:
        return _fallback(data.current_price, data.lowest_ever)

    # ── 3. LINEAR TREND (last 30 days only) ───────────────────
    # Using all 90 days dilutes recent momentum; 30 days is more predictive
    recent = smoothed[-30:] if len(smoothed) >= 30 else smoothed
    x = np.arange(len(recent))
    slope, intercept = np.polyfit(x, recent, 1)

    # Predict 7 days out
    predicted_price = intercept + slope * (len(recent) + 7)
    predicted_price = max(predicted_price, data.lowest_ever * 0.9)  # sanity floor

    # ── 4. SIGNAL 1: TREND DIRECTION ──────────────────────────
    price_range = data.highest_ever - data.lowest_ever
    # Slope is significant only if it moves >0.5% of range per day
    significance_threshold = price_range * 0.005
    if abs(slope) < significance_threshold:
        trend = "flat"
    elif slope < 0:
        trend = "falling"
    else:
        trend = "rising"

    # ── 5. SIGNAL 2: PROXIMITY TO LOWEST EVER ─────────────────
    # How far is current price from all-time low, as % of price range
    if price_range > 0:
        proximity_pct = (data.current_price - data.lowest_ever) / price_range
    else:
        proximity_pct = 0.5

    # 0.0 = at lowest ever, 1.0 = at highest ever
    if proximity_pct <= 0.15:
        proximity_signal = "near_low"      # within bottom 15% of range → strong buy
    elif proximity_pct <= 0.35:
        proximity_signal = "good"          # reasonable price
    elif proximity_pct <= 0.65:
        proximity_signal = "mid"           # middle of range → neutral
    else:
        proximity_signal = "near_high"     # in top 35% → overpriced

    # ── 6. SIGNAL 3: RECENT VOLATILITY ────────────────────────
    # High volatility = price is unstable, might drop further
    recent_prices = combined[-14:] if len(combined) >= 14 else combined
    volatility = np.std(recent_prices) / np.mean(recent_prices) if np.mean(recent_prices) > 0 else 0
    high_volatility = volatility > 0.03  # >3% std dev relative to mean

    # ── 7. SIGNAL 4: SALE SEASON ──────────────────────────────
    sale_incoming = False
    if data.days_to_next_sale is not None and 0 < data.days_to_next_sale <= 21:
        sale_incoming = True  # sale within 3 weeks → wait

    # ── 8. SCORING SYSTEM ─────────────────────────────────────
    # Score: positive = buy, negative = wait, near zero = hold
    score = 0

    # Trend contribution (max ±3)
    if trend == "falling":
        score -= 2   # price dropping → wait
    elif trend == "rising":
        score += 2   # price rising → buy now before it goes up
    # flat = 0

    # Proximity contribution (max ±4) — most important signal
    if proximity_signal == "near_low":
        score += 4
    elif proximity_signal == "good":
        score += 2
    elif proximity_signal == "mid":
        score += 0
    elif proximity_signal == "near_high":
        score -= 3

    # Volatility contribution
    if high_volatility and trend == "falling":
        score -= 1   # unstable + falling = wait more

    # Sale contribution
    if sale_incoming:
        score -= 2   # sale coming → always worth waiting

    # Predicted price vs current
    predicted_diff_pct = (predicted_price - data.current_price) / data.current_price
    if predicted_diff_pct < -0.02:   # predicted >2% below current
        score -= 1
    elif predicted_diff_pct > 0.02:  # predicted >2% above current
        score += 1

    # ── 9. VERDICT ────────────────────────────────────────────
    if score >= 4:
        verdict = "buy"
    elif score <= -2:
        verdict = "wait"
    else:
        verdict = "hold"

    # Build human-readable reason
    reason = _build_reason(verdict, trend, proximity_signal, sale_incoming, high_volatility, predicted_price, data.current_price)

    print({
        "phone_current": float(data.current_price),
        "predicted_7d": int(round(float(predicted_price), 0)),
        "slope": round(float(slope), 2),
        "trend": trend,
        "proximity": proximity_signal,
        "proximity_pct": round(float(proximity_pct), 2),
        "volatility": round(float(volatility), 4),
        "sale_incoming": bool(sale_incoming),
        "score": int(score),
        "verdict": verdict
    })

    print("Score:", score, "Trend:", trend, "Proximity:", proximity_signal)
    return {
        "verdict": verdict,
        "predicted_price": int(round(float(predicted_price), 0)),
        "confidence": _confidence(score),
        "signals": {
            "trend": trend,
            "proximity_to_low": proximity_signal,
            "high_volatility": bool(high_volatility),
            "sale_incoming": bool(sale_incoming),
            "score": int(score)
        },
        "reason": reason
    }


def _fallback(current_price, lowest_ever):
    return {
        "verdict": "hold",
        "predicted_price": int(round(current_price, 0)),
        "confidence": "low",
        "signals": {},
        "reason": "Not enough price history to make a confident prediction."
    }


def _confidence(score: int) -> str:
    abs_score = abs(score)
    if abs_score >= 3:
        return "high"
    elif abs_score >= 1:
        return "medium"
    return "low"


def _build_reason(verdict, trend, proximity, sale_incoming, volatile, predicted, current) -> str:
    parts = []

    if proximity == "near_low":
        parts.append("price is near its all-time low")
    elif proximity == "near_high":
        parts.append("price is near its historical high")

    if trend == "falling":
        parts.append("trend is downward")
    elif trend == "rising":
        parts.append("trend is rising")

    if sale_incoming:
        parts.append("a sale event is coming within 3 weeks")

    diff = predicted - current
    if abs(diff) > current * 0.02:
        direction = "drop" if diff < 0 else "rise"
        parts.append(f"price expected to {direction} to ₹{int(predicted):,} in ~7 days")

    if not parts:
        parts.append("price is stable with no strong signals")

    base = {
        "buy":  "Good time to buy — ",
        "wait": "Consider waiting — ",
        "hold": "Hold for now — "
    }[verdict]

    return base + ", ".join(parts) + "."