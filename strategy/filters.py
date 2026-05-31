import datetime
from data.models import MarketSnapshot

def module_0_global_filters(snapshot: MarketSnapshot) -> dict:
    """MODULE 0 — GLOBAL FILTERS"""
    current_time = snapshot.timestamp.time()

    t_1000 = datetime.time(10, 0)
    t_1130 = datetime.time(11, 30)
    t_1330 = datetime.time(13, 30)
    t_1430 = datetime.time(14, 30)

    result = {
        "status": "WAIT",
        "reliability": "none",
        "reversal_allowed": False,
        "conviction_modifier": 0.0
    }

    if current_time < t_1000:
        result["status"] = "WAIT"
        result["reliability"] = "unreliable"
        result["reversal_allowed"] = False
    elif t_1000 <= current_time < t_1130:
        result["status"] = "PROCEED"
        result["reliability"] = "partial"
        result["reversal_allowed"] = True
        result["conviction_modifier"] = 0.75 # Reduce conviction by 25%
    elif t_1130 <= current_time <= t_1330:
        result["status"] = "PROCEED"
        result["reliability"] = "full"
        result["reversal_allowed"] = True
        result["conviction_modifier"] = 1.0 # Best window
    elif t_1330 < current_time <= t_1430:
        result["status"] = "PROCEED"
        result["reliability"] = "caution"
        result["reversal_allowed"] = False # Only continuation
        result["conviction_modifier"] = 1.0
    else: # > 14:30 PM
        result["status"] = "MANAGE_ONLY"
        result["reliability"] = "none"
        result["reversal_allowed"] = False

    return result

def module_1_event_filter(snapshot: MarketSnapshot, unusual_oi_both_sides_build: bool) -> dict:
    """MODULE 1 — EVENT AND NEWS FILTER"""
    event_risk_flag = False
    if (snapshot.economic_event_today or
        snapshot.rbi_policy_day or
        snapshot.result_day_major_stock or
        snapshot.msci_rebalance_day):
        event_risk_flag = True

    straddle_detected = unusual_oi_both_sides_build

    return {
        "event_risk_flag": event_risk_flag,
        "straddle_detected": straddle_detected,
        "reversal_allowed": not (event_risk_flag or straddle_detected),
        "max_position_size_modifier": 0.5 if event_risk_flag else 1.0
    }

def module_2_expiry_filter(snapshot: MarketSnapshot, current_week_oi_falling: bool, next_week_same_strike_oi_rising: bool) -> dict:
    """MODULE 2 — EXPIRY AND ROLLOVER FILTER"""
    dt = snapshot.timestamp
    day_of_week = dt.weekday() # 0 = Monday, ..., 3 = Thursday
    current_time = dt.time()
    t_1100 = datetime.time(11, 0)

    # Simple check for expiry week - assume standard Thursday expiry
    # For robust paper trading this would need actual expiry calendar mapping
    days_to_expiry = (snapshot.options_chain.expiry_date - dt.date()).days
    expiry_week = days_to_expiry <= 4

    wall_age_decay = 0
    rollover_detected = False
    reversal_entry_allowed = True

    if day_of_week == 3 and current_time > t_1100: # Thursday > 11 AM
        reversal_entry_allowed = False

    if expiry_week:
        if day_of_week in [1, 2] and current_week_oi_falling and next_week_same_strike_oi_rising: # Tuesday/Wednesday
            rollover_detected = True

        if day_of_week in [0, 1]: # Monday, Tuesday
            wall_age_decay = 1
        elif day_of_week == 2: # Wednesday
            wall_age_decay = 1
        elif day_of_week == 3 and current_time < t_1100:
            wall_age_decay = 2

    return {
        "rollover_detected": rollover_detected,
        "wall_age_decay": wall_age_decay,
        "reversal_entry_allowed": reversal_entry_allowed
    }
