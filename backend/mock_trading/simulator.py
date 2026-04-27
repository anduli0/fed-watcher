from backend.mock_trading.portfolio import Position


def calculate_pnl(position: Position, current_rate: float, entry_rate: float) -> float:
    """
    Simplified P&L: bond price moves inversely to rate.
    1 bps rate move ≈ duration * 0.01% price move.
    Duration proxies: 2Y=2, 10Y=8, TLT=18, USD=1
    """
    durations = {"2Y_TREASURY": 2, "10Y_TREASURY": 8, "TLT": 18, "USD": 1}
    dur = durations.get(position.instrument, 1)
    rate_change_bps = (current_rate - entry_rate) * 100
    price_change_pct = -dur * rate_change_bps * 0.01

    if position.direction == "short":
        price_change_pct *= -1

    return round(price_change_pct, 4)  # % P&L


def evaluate_prediction(predicted_delta_bps: float, actual_rate_change_bps: float) -> dict:
    """Compare forecast to realized rate change."""
    error = actual_rate_change_bps - predicted_delta_bps
    return {
        "predicted_bps": predicted_delta_bps,
        "actual_bps": actual_rate_change_bps,
        "error_bps": error,
        "abs_error": abs(error),
        "direction_correct": (predicted_delta_bps * actual_rate_change_bps) >= 0,
    }
