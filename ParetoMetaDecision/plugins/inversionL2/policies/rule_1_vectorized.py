import numpy as np
from core.policies.base import DecisionPolicy

class SellPressureAbsorptionPolicyVectorized(DecisionPolicy):

    def __init__(self, theta: float, k: int, **_):
        self.theta = theta
        self.k = k

    def decide_series(self, market_data):

        bid_volume = market_data.bid_volume
        ask_volume = market_data.ask_volume

        k = self.k

        if len(bid_volume) < k:
            return np.zeros_like(bid_volume, dtype=bool)

        bid_cum = np.cumsum(bid_volume)
        ask_cum = np.cumsum(ask_volume)

        bid_k = bid_cum[k-1:] - np.concatenate(([0.0], bid_cum[:-k]))
        ask_k = ask_cum[k-1:] - np.concatenate(([0.0], ask_cum[:-k]))

        denom = bid_k + ask_k
        imbalance = np.zeros_like(bid_k)
        mask = denom > 0
        imbalance[mask] = (bid_k[mask] - ask_k[mask]) / denom[mask]

        decision = imbalance > self.theta

        out = np.zeros(len(bid_volume), dtype=bool)
        out[k-1:] = decision

        return out
