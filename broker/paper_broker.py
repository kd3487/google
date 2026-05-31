from typing import Dict, Any

class PaperBroker:
    def __init__(self, initial_balance: float = 100000.0, risk_per_trade_pct: float = 0.02):
        self.balance = initial_balance
        self.risk_per_trade_pct = risk_per_trade_pct
        self.open_positions: Dict[str, Any] = {}
        self.trade_history = []

    def calculate_position_size(self, zone_strength_score: int, sequence_score: int, cross_index_score: str, event_risk_flag: bool, market_mode: str, stop_loss_points: float) -> float:
        """MODULE 8 — POSITION SIZING"""
        if stop_loss_points <= 0:
            return 0

        allowed_risk_amount = self.balance * self.risk_per_trade_pct

        if zone_strength_score >= 18: size_modifier = 1.0
        elif 14 <= zone_strength_score <= 17: size_modifier = 0.75
        elif 10 <= zone_strength_score <= 13: size_modifier = 0.50
        elif 6 <= zone_strength_score <= 9: size_modifier = 0.25
        else: return 0.0

        if sequence_score == 1: size_modifier *= 0.75
        if cross_index_score == "DIVERGE": size_modifier *= 0.50
        if event_risk_flag: size_modifier = min(size_modifier, 0.50)
        if market_mode == "TREND": size_modifier = min(size_modifier, 0.50) # Assuming reversal trade

        # Risk amount based on modifiers
        final_risk_amount = allowed_risk_amount * size_modifier

        # Quantity = Risk / Stop Loss Points
        # Using abstract lots/quantities
        quantity = int(final_risk_amount / stop_loss_points)
        return quantity

    def execute_trade(self, symbol: str, direction: str, quantity: float, entry_price: float, sl_price: float, tp_levels: list):
        """Execute a paper trade."""
        if quantity <= 0:
            return False

        trade = {
            "symbol": symbol,
            "direction": direction,
            "quantity": quantity,
            "entry_price": entry_price,
            "sl_price": sl_price,
            "tp_levels": tp_levels,
            "status": "OPEN",
            "pnl": 0.0
        }
        self.open_positions[symbol] = trade
        return True

    def evaluate_refresh_monitor(self, symbol: str, wall_oi_drop_pct: float, iv_rising: bool,
                                 net_delta_flipped: bool, pcr_momentum_reversed: bool):
        """MODULE 13 — EVERY 30-MINUTE REFRESH MONITOR"""
        if symbol not in self.open_positions:
            return

        trade = self.open_positions[symbol]

        if wall_oi_drop_pct > 0.20:
            self._close_position(symbol, "Wall Collapse > 20%", 1.0)
        elif 0.10 <= wall_oi_drop_pct <= 0.15 and iv_rising:
            self._close_position(symbol, "Partial Collapse Warning", 0.5)
            self._trail_sl_to_breakeven(symbol)
        elif net_delta_flipped:
            self._close_position(symbol, "Net Delta Flipped", 0.5)
            # tight rest not fully implemented in mock
        elif pcr_momentum_reversed:
            self._close_position(symbol, "PCR Momentum Reversed", 0.25)

    def _close_position(self, symbol: str, reason: str, percentage: float = 1.0):
        if symbol in self.open_positions:
            trade = self.open_positions[symbol]
            qty_to_close = trade["quantity"] * percentage
            # Simplistic PNL calc for mock (assuming current price isn't passed here, just logging closure)
            print(f"[{symbol}] Closing {percentage*100}% of position due to: {reason}")

            if percentage >= 1.0:
                self.trade_history.append(trade)
                del self.open_positions[symbol]
            else:
                trade["quantity"] -= qty_to_close

    def _trail_sl_to_breakeven(self, symbol: str):
        if symbol in self.open_positions:
            trade = self.open_positions[symbol]
            trade["sl_price"] = trade["entry_price"]
            print(f"[{symbol}] SL Trailed to Breakeven ({trade['entry_price']})")

    def update_prices(self, symbol: str, current_price: float):
        """Simple check for SL/TP."""
        if symbol not in self.open_positions:
            return

        trade = self.open_positions[symbol]

        # Check SL
        if trade["direction"] == "BUY" and current_price <= trade["sl_price"]:
            trade["pnl"] = (current_price - trade["entry_price"]) * trade["quantity"]
            self._close_position(symbol, "Stop Loss Hit", 1.0)
            self.balance += trade["pnl"]
        elif trade["direction"] == "SELL" and current_price >= trade["sl_price"]:
            trade["pnl"] = (trade["entry_price"] - current_price) * trade["quantity"]
            self._close_position(symbol, "Stop Loss Hit", 1.0)
            self.balance += trade["pnl"]
