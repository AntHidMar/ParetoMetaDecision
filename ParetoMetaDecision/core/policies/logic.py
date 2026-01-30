# core/policies/logic.py
import numpy as np

class AndPolicy:
    def __init__(self, left, right):
        self.left = left
        self.right = right

    def decide_series(self, market_data):
        a = np.asarray(self.left.decide_series(market_data), dtype=bool)
        b = np.asarray(self.right.decide_series(market_data), dtype=bool)
        n = min(len(a), len(b))
        return np.logical_and(a[:n], b[:n])


class OrPolicy:
    def __init__(self, left, right):
        self.left = left
        self.right = right

    def decide_series(self, market_data):
        a = np.asarray(self.left.decide_series(market_data), dtype=bool)
        b = np.asarray(self.right.decide_series(market_data), dtype=bool)
        n = min(len(a), len(b))
        return np.logical_or(a[:n], b[:n])
