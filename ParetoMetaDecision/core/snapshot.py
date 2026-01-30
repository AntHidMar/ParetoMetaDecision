# core/snapshot.py

from dataclasses import dataclass
import pandas as pd


@dataclass
class OrderBookSnapshot:
    """
    Immutable snapshot of the L2 order book at a given instant.
    """
    fecha: pd.Timestamp
    df: pd.DataFrame

    # ---------------------------
    # TECHNICAL ALIAS
    # ---------------------------
    @property
    def timestamp(self) -> pd.Timestamp:
        """
        Technical alias for compatibility with evaluation layers.
        """
        return self.fecha

    # ---------------------------
    # ORDER BOOK SIDES
    # ---------------------------
    @property
    def bids(self) -> pd.DataFrame:
        return self.df[self.df["side"] == 1]

    @property
    def asks(self) -> pd.DataFrame:
        return self.df[self.df["side"] == 0]

    # ---------------------------
    # VOLUME METRICS
    # ---------------------------
    @property
    def total_bid_volume(self) -> float:
        return float(self.bids["sizeL2"].sum()) if not self.bids.empty else 0.0

    @property
    def total_ask_volume(self) -> float:
        return float(self.asks["sizeL2"].sum()) if not self.asks.empty else 0.0

    # ---------------------------
    # PRICE METRICS
    # ---------------------------
    @property
    def best_bid(self):
        return self.bids["priceL2"].max() if not self.bids.empty else None

    @property
    def best_ask(self):
        return self.asks["priceL2"].min() if not self.asks.empty else None

    @property
    def mid_price(self):
        if self.best_bid is None or self.best_ask is None:
            return None
        return 0.5 * (self.best_bid + self.best_ask)
