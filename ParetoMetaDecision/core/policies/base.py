import numpy as np

class DecisionPolicy:
    """
    Interfaz base para cualquier política de decisión.
    """

    def decide_series(self, market_data) -> np.ndarray:
        """
        Devuelve un vector booleano:
        True  -> LONG
        False -> ABSTAIN
        """
        raise NotImplementedError
