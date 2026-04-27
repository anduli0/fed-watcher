from dataclasses import dataclass, field

INSTRUMENTS = ["2Y_TREASURY", "10Y_TREASURY", "TLT", "USD"]


@dataclass
class Position:
    instrument: str
    direction: str  # long|short
    entry_rate: float
    rationale: str


def build_positions_from_forecast(delta_bps: float) -> list[Position]:
    """Map rate path prediction to mock positions."""
    positions = []

    if delta_bps <= -25:
        # Dovish: long bonds (rates fall → bond prices rise)
        positions.append(Position("2Y_TREASURY", "long",  0.0, f"Rate cut expected ({delta_bps:+.0f} bps)"))
        positions.append(Position("10Y_TREASURY", "long", 0.0, f"Duration play on easing cycle"))
        positions.append(Position("TLT",          "long", 0.0, f"Long-duration ETF on rate cut thesis"))
        positions.append(Position("USD",           "short", 0.0, f"USD weakens on dovish Fed"))
    elif delta_bps >= 25:
        # Hawkish: short bonds
        positions.append(Position("2Y_TREASURY", "short", 0.0, f"Rate hike expected ({delta_bps:+.0f} bps)"))
        positions.append(Position("10Y_TREASURY", "short", 0.0, f"Sell duration on tightening"))
        positions.append(Position("TLT",          "short", 0.0, f"Short long-duration on hike thesis"))
        positions.append(Position("USD",           "long",  0.0, f"USD strengthens on hawkish Fed"))
    else:
        # Neutral: no directional bet
        positions.append(Position("2Y_TREASURY", "long", 0.0, "Neutral carry position"))

    return positions
