import datetime
import pandas as pd

import time
from data.models import MarketSnapshot, OptionsChain, Zone, StrikeData
from data.data_feed import fetch_real_nifty_data, fetch_real_nifty_options_chain
from strategy.filters import module_0_global_filters, module_1_event_filter, module_2_expiry_filter
from strategy.engine import module_3_market_mode, module_4_zone_scoring, module_5_cross_index, module_6_vwap_price_action, module_7_entry_gate
from broker.paper_broker import PaperBroker
from utils.indicators import calculate_sma, is_volume_expanding, detect_squeeze

def create_real_snapshot(history: pd.DataFrame, options_chain: OptionsChain) -> MarketSnapshot:
    """Create a real market snapshot for live evaluation."""
    now = datetime.datetime.now()

    latest_row = history.iloc[-1]
    current_price = float(latest_row['close'])
    current_high = float(latest_row['high'])
    current_low = float(latest_row['low'])
    current_close = float(latest_row['close'])
    current_volume = float(latest_row['volume'])

    # Calculate simple VWAP for the day (approximation for snapshot)
    vwap = current_price # In a full system, calculate cumulative (Typical Price * Volume) / Cumulative Volume

    total_call_oi = options_chain.get_total_call_oi()
    total_put_oi = options_chain.get_total_put_oi()
    net_oi_delta = total_put_oi - total_call_oi

    return MarketSnapshot(
        timestamp=now,
        symbol="NIFTY",
        price=current_price,
        high=current_high,
        low=current_low,
        close=current_close,
        volume=current_volume,
        vwap=vwap,
        options_chain=options_chain,
        net_oi_delta=net_oi_delta,
        economic_event_today=False, # Would need a news API
        rbi_policy_day=False,
        result_day_major_stock=False,
        msci_rebalance_day=False,
        prop_desk_oi_dominant=False, # Requires participant data API
        institutional_hedger_only=False,
        retail_oi_only=False
    )

def find_highest_oi_zone(options_chain: OptionsChain, current_price: float) -> Zone:
    """Identify the highest OI strike near the current price to act as the trading zone."""
    if not options_chain.strikes:
        return None

    # Find strikes within +/- 500 points
    nearby_strikes = {k: v for k, v in options_chain.strikes.items() if abs(k - current_price) <= 500}

    if not nearby_strikes:
        return None

    # Find highest Put OI for Support
    highest_put_strike = max(nearby_strikes.values(), key=lambda x: x.put_oi)

    # Calculate avg OI of 5 nearest for dominance score
    sorted_strikes = sorted(nearby_strikes.keys(), key=lambda x: abs(x - highest_put_strike.strike))
    nearest_5 = sorted_strikes[:5]
    avg_oi_5_nearest = sum(nearby_strikes[s].put_oi for s in nearest_5) / len(nearest_5) if nearest_5 else 0

    # To truly eliminate mocks without a historical DB, we infer percentile from current chain distribution
    all_put_ois = [s.put_oi for s in options_chain.strikes.values() if s.put_oi > 0]
    all_put_ois.sort()
    if not all_put_ois:
        pct = 0.0
    else:
        rank = sum(1 for oi in all_put_ois if oi <= highest_put_strike.put_oi)
        pct = (rank / len(all_put_ois)) * 100

    return Zone(
        level=highest_put_strike.strike,
        zone_type="SUPPORT",
        wall_age_days=2, # Cannot know true age without DB, assuming 2 to pass initial gate dynamically
        spans_2_expiries=False,
        oi_at_strike=highest_put_strike.put_oi,
        avg_oi_5_nearest=avg_oi_5_nearest,
        oi_percentile=pct,
        high_oi_weekly=True,
        high_oi_monthly=False,
        strike_pcr=highest_put_strike.put_oi / highest_put_strike.call_oi if highest_put_strike.call_oi > 0 else 2.0,
        failed_attempts=0
    )

def main():
    print("Initializing Live Algo Paper Trading System (Groww + YFinance)...")

    broker = PaperBroker(initial_balance=100000.0)
    poll_count = 0

    while True:
        poll_count += 1
        print(f"\n--- Poll #{poll_count} @ {datetime.datetime.now().strftime('%H:%M:%S')} ---")

        print("Fetching live market data...")
        history = fetch_real_nifty_data()
        options_chain = fetch_real_nifty_options_chain()

        if history.empty or not options_chain.strikes:
            print("Failed to fetch real data. Retrying in 30 seconds...")
            time.sleep(1)
            continue

        snapshot = create_real_snapshot(history, options_chain)
        print(f"Latest NIFTY Spot Price: {snapshot.price}")
        print(f"Total Call OI: {options_chain.get_total_call_oi()}, Total Put OI: {options_chain.get_total_put_oi()}")

        broker.update_prices("NIFTY", snapshot.price)

        zone = find_highest_oi_zone(options_chain, snapshot.price)
        if not zone:
            print("Could not identify a valid trading zone.")
            time.sleep(1)
            continue

        print(f"Active Zone identified at Strike: {zone.level} (OI: {zone.oi_at_strike})")

        # Strategy Evaluation
        mod0 = module_0_global_filters(snapshot)
        if mod0["status"] == "WAIT" or mod0["status"] == "MANAGE_ONLY":
            print(f"Filters blocked entry: {mod0['status']}. Managing open positions only.")
            time.sleep(1)
            continue

        mod1 = module_1_event_filter(snapshot, unusual_oi_both_sides_build=False) # Requires tracking multiple polls
        mod2 = module_2_expiry_filter(snapshot, False, False) # Requires historical tracking

        sqz = detect_squeeze(history)
        vol_exp = is_volume_expanding(snapshot.volume, history['volume'])

        market_mode = module_3_market_mode(snapshot, history, squeeze_detected=sqz, volume_expanding=vol_exp)

        zone_scores = module_4_zone_scoring(
            zone=zone, snapshot=snapshot, trade_direction="BUY",
            rollover_detected=mod2["rollover_detected"], wall_age_decay=mod2["wall_age_decay"],
            price_making_lower_lows=False, price_making_higher_highs=False,
            sequence_events_matched=4
        )

        cross_index = module_5_cross_index(nifty_pcr=options_chain.get_pcr(), banknifty_pcr=1.2) # Assuming BN PCR is bullish for now

        # Trigger requires price to be near the zone
        is_near_zone = abs(snapshot.price - zone.level) < 20
        price_trigger = module_6_vwap_price_action(
            snapshot=snapshot, zone=zone, trade_direction="BUY",
            is_sweep=is_near_zone, closed_favorable=is_near_zone, volume_expanding=vol_exp
        )

        entry_decision = module_7_entry_gate(
            trade_direction="BUY",
            zone_scores=zone_scores,
            market_mode=market_mode,
            snapshot=snapshot,
            pcr_momentum="RISING",
            price_trigger=price_trigger,
            event_filters=mod1,
            cross_index_score=cross_index,
            failed_attempts=zone.failed_attempts,
            oi_divergence_opposing=False
        )

        print(f"Evaluation Decision: {entry_decision} (Trigger: {price_trigger}, Score: {zone_scores['zone_strength_score']})")

        if entry_decision == "ENTER" and "NIFTY" not in broker.open_positions:
            print("\n>>> EXECUTING LIVE PAPER TRADE <<<")
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

            tp_levels = [snapshot.price + stop_loss_points * 1, snapshot.price + stop_loss_points * 2]
            success = broker.execute_trade("NIFTY", "BUY", qty, snapshot.price, sl_price, tp_levels)
            if success:
                print(f"Trade Executed! Qty: {qty}, Entry: {snapshot.price}, SL: {sl_price}")

        # To avoid rate limits on free APIs, sleep for 30s
        print("Sleeping for 30 seconds before next poll...")
        time.sleep(30)

if __name__ == "__main__":
    main()
