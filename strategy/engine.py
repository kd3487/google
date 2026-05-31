from data.models import MarketSnapshot, Zone
import pandas as pd

def module_3_market_mode(snapshot: MarketSnapshot, history: pd.DataFrame, squeeze_detected: bool, volume_expanding: bool) -> str:
    """MODULE 3 — MARKET MODE CLASSIFICATION"""
    # Simplified assumptions based on paper trading logic parameters
    price_vwap_diff = abs(snapshot.price - snapshot.vwap) / snapshot.vwap

    if squeeze_detected:
        return "SQUEEZE"
    elif price_vwap_diff < 0.002: # Price rotating around VWAP tightly
        return "RANGE"
    elif volume_expanding and price_vwap_diff > 0.005: # Strong breakout condition mocked
        return "BREAKOUT"
    else:
        return "TREND"

def module_4_zone_scoring(zone: Zone, snapshot: MarketSnapshot, trade_direction: str,
                          rollover_detected: bool, wall_age_decay: int,
                          price_making_lower_lows: bool, price_making_higher_highs: bool,
                          sequence_events_matched: int) -> dict:
    """MODULE 4 — ZONE QUALIFICATION"""

    # STEP 4A - Age Score
    age = zone.wall_age_days - wall_age_decay
    if age <= 1: age_score = 1
    elif 2 <= age <= 3: age_score = 2
    elif 4 <= age <= 6: age_score = 3
    else: age_score = 4
    if zone.spans_2_expiries: age_score = 5

    # STEP 4B - Dominance Score
    dom_ratio = zone.oi_at_strike / zone.avg_oi_5_nearest if zone.avg_oi_5_nearest > 0 else 1.0
    if dom_ratio < 1.2: dom_score = 1
    elif 1.2 <= dom_ratio < 1.5: dom_score = 2
    elif 1.5 <= dom_ratio < 2.0: dom_score = 3
    elif 2.0 <= dom_ratio < 3.0: dom_score = 4
    else: dom_score = 5
    wall_strength_score = age_score + dom_score

    # STEP 4C - Percentile Score
    pct = zone.oi_percentile
    if pct > 90: pct_score = 2
    elif 70 <= pct <= 90: pct_score = 1
    elif 40 <= pct < 70: pct_score = 0
    else: pct_score = -1

    # STEP 4D - Multi-Expiry Score
    if rollover_detected: me_score = 0
    elif zone.high_oi_weekly and zone.high_oi_monthly: me_score = 3
    elif not zone.high_oi_weekly and zone.high_oi_monthly: me_score = 1
    else: me_score = 0

    # STEP 4E - Net OI Delta Score
    net_delta = snapshot.net_oi_delta
    if net_delta < -100000 and trade_direction == "BUY": net_delta_score = 2
    elif net_delta > 100000 and trade_direction == "BUY": net_delta_score = -1
    elif net_delta > 100000 and trade_direction == "SELL": net_delta_score = 2
    elif net_delta < -100000 and trade_direction == "SELL": net_delta_score = -1
    else: net_delta_score = 0

    # STEP 4F - Divergence Score
    div_score = 0
    if price_making_lower_lows and trade_direction == "BUY": div_score = 2
    elif price_making_higher_highs and trade_direction == "SELL": div_score = 2

    # STEP 4G - Strike PCR Score
    pcr = zone.strike_pcr
    if trade_direction == "BUY":
        if pcr > 2.0: pcr_score = 2
        elif 1.0 <= pcr <= 2.0: pcr_score = 0
        else: pcr_score = -1
    else:
        if pcr < 0.5: pcr_score = 2
        elif 0.5 <= pcr <= 1.0: pcr_score = 0
        else: pcr_score = -1

    # STEP 4H - Participant Quality Score
    if snapshot.prop_desk_oi_dominant: part_score = 2
    elif snapshot.institutional_hedger_only: part_score = 0
    elif snapshot.retail_oi_only: part_score = -1
    else: part_score = 0

    # STEP 4I - Confirmation Sequence
    if sequence_events_matched == 5: seq_score = 3
    elif sequence_events_matched == 4: seq_score = 2
    elif sequence_events_matched == 3: seq_score = 1
    else: seq_score = 0

    # Final Zone Score
    zone_strength_score = min(21, wall_strength_score + pct_score + me_score + net_delta_score +
                              div_score + pcr_score + part_score + seq_score)

    return {
        "zone_strength_score": zone_strength_score,
        "wall_strength_score": wall_strength_score,
        "seq_score": seq_score
    }

def module_5_cross_index(nifty_pcr: float, banknifty_pcr: float) -> str:
    """MODULE 5 — CROSS-INDEX CONFIRMATION"""
    nifty_bullish = nifty_pcr > 1.0
    bn_bullish = banknifty_pcr > 1.0

    if nifty_bullish == bn_bullish:
        return "STRONG"
    return "DIVERGE"

def module_6_vwap_price_action(snapshot: MarketSnapshot, zone: Zone, trade_direction: str,
                               is_sweep: bool, closed_favorable: bool, volume_expanding: bool) -> str:
    """MODULE 6 — VWAP AND PRICE ACTION FILTER"""
    # Assuming price is at the zone.
    price = snapshot.price
    vwap = snapshot.vwap

    if trade_direction == "BUY":
        if is_sweep and closed_favorable and volume_expanding:
            return "CONFIRMED"
        elif price >= vwap:
            return "WEAK"
        else:
            return "FAILED"
    else: # SELL
        if is_sweep and closed_favorable and volume_expanding:
            return "CONFIRMED"
        elif price <= vwap:
            return "WEAK"
        else:
            return "FAILED"

def module_7_entry_gate(
    trade_direction: str,
    zone_scores: dict,
    market_mode: str,
    snapshot: MarketSnapshot,
    pcr_momentum: str,
    price_trigger: str,
    event_filters: dict,
    cross_index_score: str,
    failed_attempts: int,
    oi_divergence_opposing: bool = False
) -> str:
    """MODULE 7 — FINAL BUY / SELL ENTRY GATE"""

    z_score = zone_scores["zone_strength_score"]
    w_score = zone_scores["wall_strength_score"]

    if z_score < 10 or w_score < 5:
        return "NO_TRADE"

    if market_mode not in ["RANGE", "TREND"]: # Assuming pullback
        return "WAIT"

    if cross_index_score == "DIVERGE" and z_score < 14:
        return "WAIT"

    if event_filters["straddle_detected"] or event_filters["event_risk_flag"]:
        return "NO_TRADE"

    if price_trigger == "FAILED":
        return "NO_TRADE"
    elif price_trigger == "WEAK":
        return "WAIT"

    if failed_attempts >= 2:
        return "NO_TRADE"

    if oi_divergence_opposing:
        return "NO_TRADE"

    if trade_direction == "BUY":
        if snapshot.net_oi_delta > 0: return "WAIT"
        if pcr_momentum == "FALLING": return "WAIT"
        return "ENTER"
    else:
        if snapshot.net_oi_delta < 0: return "WAIT"
        if pcr_momentum == "RISING": return "WAIT"
        return "ENTER"
