from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import numpy as np

app = FastAPI()

# Allow frontend to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PriceData(BaseModel):
    amazon_prices: list[float]
    flipkart_prices: list[float]
    current_price: float
    lowest_ever: float
    highest_ever: float
    days_to_next_sale: Optional[int] = None


@app.get("/")
def home():
    return {"message": "BuyWise ML API running"}


@app.post("/predict")
def predict(data: PriceData):

    # ---------- 1. CLEAN + COMBINE DATA ----------
    amz = np.array(data.amazon_prices, dtype=float)
    fk = np.array(data.flipkart_prices, dtype=float)

    min_len = min(len(amz), len(fk))
    if min_len < 5:
        return fallback(data)

    amz = amz[-min_len:]
    fk = fk[-min_len:]

    combined = (amz + fk) / 2

    # ---------- 2. LINEAR REGRESSION ----------
    x = np.arange(len(combined))
    slope, intercept = np.polyfit(x, combined, 1)

    # Predict next 7 days
    future_x = len(combined) + 7
    predicted_price = intercept + slope * future_x

    # Safety clamp
    predicted_price = max(predicted_price, data.lowest_ever * 0.9)

    # ---------- 3. TREND ----------
    if slope < -5:
        trend = "falling"
    elif slope > 5:
        trend = "rising"
    else:
        trend = "flat"

    # ---------- 4. POSITION IN PRICE RANGE ----------
    price_range = data.highest_ever - data.lowest_ever
    if price_range <= 0:
        proximity = 0.5
    else:
        proximity = (data.current_price - data.lowest_ever) / price_range

    # ---------- 5. SCORING ----------
    score = 0

    # Trend impact
    if trend == "falling":
        score -= 2
    elif trend == "rising":
        score += 2

    # Position impact
    if proximity <= 0.2:
        score += 3   # cheap → buy
    elif proximity >= 0.7:
        score -= 3   # expensive → hold

    # Prediction impact
    diff_pct = (predicted_price - data.current_price) / data.current_price

    if diff_pct > 0.03:
        score += 2   # price going up → buy now
    elif diff_pct < -0.03:
        score -= 2   # price dropping → wait (hold)

    # ---------- 6. FINAL VERDICT ----------
    if score >= 2:
        verdict = "buy"
    else:
        verdict = "hold"

    # ---------- 7. CONFIDENCE ----------
    if abs(score) >= 4:
        confidence = "high"
    elif abs(score) >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    # ---------- 8. REASONING ----------
    reasons = []

    if trend == "rising":
        reasons.append("Price has been increasing recently")
    elif trend == "falling":
        reasons.append("Price is dropping recently")
    else:
        reasons.append("Price is relatively stable")

    if proximity <= 0.2:
        reasons.append("Price is near historical low")
    elif proximity >= 0.7:
        reasons.append("Price is closer to historical high")

    if diff_pct > 0.03:
        reasons.append("Expected to rise further soon")
    elif diff_pct < -0.03:
        reasons.append("Expected to drop further soon")

    reason = " · ".join(reasons)

    return {
        "verdict": verdict,
        "predicted_price": round(float(predicted_price), 0),
        "confidence": confidence,
        "reason": reason
    }


# ---------- FALLBACK ----------
def fallback(data):
    return {
        "verdict": "hold",
        "predicted_price": data.current_price,
        "confidence": "low",
        "reason": "Not enough data to make a prediction"
    }