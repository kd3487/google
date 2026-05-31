from dataclasses import dataclass
from typing import Dict, List, Optional
import datetime

@dataclass
class StrikeData:
    strike: float
    call_oi: float
    put_oi: float
    call_volume: float
    put_volume: float
    implied_volatility: float

@dataclass
class OptionsChain:
    timestamp: datetime.datetime
    expiry_date: datetime.date
    strikes: Dict[float, StrikeData]

    def get_total_call_oi(self) -> float:
        return sum(strike.call_oi for strike in self.strikes.values())

    def get_total_put_oi(self) -> float:
        return sum(strike.put_oi for strike in self.strikes.values())

    def get_pcr(self) -> float:
        total_call_oi = self.get_total_call_oi()
        if total_call_oi == 0:
            return 0.0
        return self.get_total_put_oi() / total_call_oi

@dataclass
class MarketSnapshot:
    timestamp: datetime.datetime
    symbol: str
    price: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float
    options_chain: OptionsChain
    net_oi_delta: float  # Difference between total put OI and total call OI change

    # Event and Expiry Flags
    economic_event_today: bool = False
    rbi_policy_day: bool = False
    result_day_major_stock: bool = False
    msci_rebalance_day: bool = False

    # Participant data (mocked)
    prop_desk_oi_dominant: bool = False
    institutional_hedger_only: bool = False
    retail_oi_only: bool = False

@dataclass
class Zone:
    level: float
    zone_type: str  # "SUPPORT" or "RESISTANCE"
    wall_age_days: int
    spans_2_expiries: bool
    oi_at_strike: float
    avg_oi_5_nearest: float
    oi_percentile: float
    high_oi_weekly: bool
    high_oi_monthly: bool
    strike_pcr: float
    failed_attempts: int = 0
