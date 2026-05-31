import datetime
import pandas as pd

from data.models import MarketSnapshot, OptionsChain, Zone, StrikeData
from data.data_feed import fetch_real_nifty_data
from strategy.filters import module_0_global_filters, module_1_event_filter, module_2_expiry_filter
from strategy.engine import module_3_market_mode, module_4_zone_scoring, module_5_cross_index, module_6_vwap_price_action, module_7_entry_gate
from broker.paper_broker import PaperBroker

def create_mock_snapshot(current_price: float, current_high: float, current_low: float, current_close: float, current_volume: float) -> MarketSnapshot:
    """Create a mock snapshot for testing, but with real price data integration."""
    now = datetime.datetime.now()
    now = now.replace(hour=11, minute=45) # Set time to valid trading window

    # Mock options chain (real options chain data requires active broker API)
    # Adjust strikes near current real price
    base_strike = round(current_price / 100) * 100
    strikes = {
        float(base_strike): StrikeData(float(base_strike), 100000, 500000, 1000, 5000, 15.0),
        float(base_strike + 100): StrikeData(float(base_strike + 100), 500000, 100000, 5000, 1000, 14.5),
    }
    oc = OptionsChain(now, now.date() + datetime.timedelta(days=3), strikes)

    return MarketSnapshot(
        timestamp=now,
        symbol="NIFTY",
        price=current_price,
        high=current_high,
        low=current_low,
        close=current_close,
        volume=current_volume,
        vwap=current_price * 0.9995, # Mock VWAP slightly below price for testing
        options_chain=oc,
        net_oi_delta=-150000.0, # Negative -> Tail wind for BUY
        economic_event_today=False,
        rbi_policy_day=False,
        result_day_major_stock=False,
        msci_rebalance_day=False,
        prop_desk_oi_dominant=True,
        institutional_hedger_only=False,
        retail_oi_only=False
    )

def main():
    print("Initializing Algo Paper Trading System...")

    # 1. Setup Broker
    broker = PaperBroker(initial_balance=100000.0)

    # 2. Get Real Historical Price Data
    print("Fetching real historical data for NIFTY (^NSEI)...")
    history = fetch_real_nifty_data()

    if history.empty:
        print("Failed to fetch real data. Exiting.")
        return

    latest_row = history.iloc[-1]
    current_price = float(latest_row['close'])
    current_high = float(latest_row['high'])
    current_low = float(latest_row['low'])
    current_close = float(latest_row['close'])
    current_volume = float(latest_row['volume'])

    print(f"Latest NIFTY Price: {current_price}")

    # 3. Create Snapshot with Real Price
    snapshot = create_mock_snapshot(current_price, current_high, current_low, current_close, current_volume)

    # Mock Zone (adjust level to be near current real price)
    zone_level = round(current_price / 100) * 100.0
    zone = Zone(
        level=zone_level,
        zone_type="SUPPORT",
        wall_age_days=5,
        spans_2_expiries=True,
        oi_at_strike=500000,
        avg_oi_5_nearest=100000,
        oi_percentile=95.0,
        high_oi_weekly=True,
        high_oi_monthly=True,
        strike_pcr=5.0,
        failed_attempts=0
    )

    print("\n--- Running Filters ---")

    # MODULE 0
    mod0 = module_0_global_filters(snapshot)
    print(f"Mod 0: {mod0}")
    if mod0["status"] == "WAIT" or mod0["status"] == "MANAGE_ONLY":
        print("Blocked by Mod 0")
        return

    # MODULE 1
    mod1 = module_1_event_filter(snapshot, unusual_oi_both_sides_build=False)
    print(f"Mod 1: {mod1}")
    if not mod1["reversal_allowed"]:
        print("Reversals blocked by Mod 1")
        # In full system, check if momentum allowed. We'll proceed assuming reversal logic.

    # MODULE 2
    mod2 = module_2_expiry_filter(snapshot, False, False)
    print(f"Mod 2: {mod2}")
    if not mod2["reversal_entry_allowed"]:
        print("Reversals blocked by Mod 2")

    print("\n--- Running Strategy Engine ---")

    # MODULE 3
    market_mode = module_3_market_mode(snapshot, history, squeeze_detected=False, volume_expanding=True)
    print(f"Market Mode: {market_mode}")

    # MODULE 4
    zone_scores = module_4_zone_scoring(
        zone=zone, snapshot=snapshot, trade_direction="BUY",
        rollover_detected=mod2["rollover_detected"], wall_age_decay=mod2["wall_age_decay"],
        price_making_lower_lows=True, price_making_higher_highs=False,
        sequence_events_matched=5
    )
    print(f"Zone Scores: {zone_scores}")

    # MODULE 5
    cross_index = module_5_cross_index(nifty_pcr=1.5, banknifty_pcr=1.2)
    print(f"Cross Index: {cross_index}")

    # MODULE 6
    price_trigger = module_6_vwap_price_action(
        snapshot=snapshot, zone=zone, trade_direction="BUY",
        is_sweep=True, closed_favorable=True, volume_expanding=True
    )
    print(f"Price Trigger: {price_trigger}")

    # MODULE 7
    entry_decision = module_7_entry_gate(
        trade_direction="BUY",
        zone_scores=zone_scores,
        market_mode=market_mode,
        snapshot=snapshot,
        pcr_momentum="RISING", # Assume rising
        price_trigger=price_trigger,
        event_filters=mod1,
        cross_index_score=cross_index,
        failed_attempts=zone.failed_attempts,
        oi_divergence_opposing=False
    )
    print(f"\nFinal Entry Decision: {entry_decision}")

    if entry_decision == "ENTER":
        print("\n--- Executing Trade ---")
        # Assume Stop Loss is below zone logic (using a 1% trailing stop calculation)
        sl_price = snapshot.price * 0.99
        stop_loss_points = snapshot.price - sl_price

        qty = broker.calculate_position_size(
            zone_strength_score=zone_scores["zone_strength_score"],
            sequence_score=zone_scores["seq_score"],
            cross_index_score=cross_index,
            event_risk_flag=mod1["event_risk_flag"],
            market_mode=market_mode,
            stop_loss_points=stop_loss_points
        )

        tp_levels = [snapshot.price + stop_loss_points * 1, snapshot.price + stop_loss_points * 2] # 1R, 2R

        success = broker.execute_trade("NIFTY", "BUY", qty, snapshot.price, sl_price, tp_levels)
        if success:
            print(f"Trade Executed! Qty: {qty}, Entry: {snapshot.price}, SL: {sl_price}")
        else:
            print("Trade failed (Qty = 0)")

if __name__ == "__main__":
    main()
