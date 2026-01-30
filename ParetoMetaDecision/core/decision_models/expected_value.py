def expected_value(
    ppv: float,
    support: float,
    gain: float,
    loss: float,
    cost: float = 0.0,
):
    """
    Valor esperado por unidad de tiempo (MapA-9).
    No asume trading, solo consecuencias asimétricas.
    """
    if ppv is None or support is None:
        return None

    ev_per_trigger = ppv * gain - (1 - ppv) * loss - cost
    ev_time = support * ev_per_trigger
    return ev_time
