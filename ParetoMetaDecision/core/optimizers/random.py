# core/optimizers/random.py
from __future__ import annotations
import random

class RandomSearch:
    def __init__(self, search_space, max_evals=500, seed=0):
        self.search_space = search_space
        self.max_evals = max_evals
        self.rng = random.Random(seed)

    def _sample_one(self):
        # Mínimo: samplear parámetros discretos tipo {param: [values]}
        params = {}
        for k, v in self.search_space.get("parameters", {}).items():
            params[k] = self.rng.choice(list(v))
        # Mantén horizon si está en el espacio
        if "horizon" in self.search_space:
            params["horizon"] = self.rng.choice(list(self.search_space["horizon"]))
        return params

    def generate(self):
        for _ in range(self.max_evals):
            yield self._sample_one()
