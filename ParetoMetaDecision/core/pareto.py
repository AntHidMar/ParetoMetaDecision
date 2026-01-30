# core/pareto.py

def _get_metric(p, key):
    if key in p:
        return p.get(key)
    m = p.get("metrics") or {}
    return m.get(key)

def pareto_front(points, axes=("mean_return", "frequency")):
    xk, yk = axes
    # filtra puntos válidos
    valid = []
    for p in points:
        x = _get_metric(p, xk)
        y = _get_metric(p, yk)
        if x is None or y is None:
            continue
        try:
            valid.append((p, float(x), float(y)))
        except Exception:
            continue

    # si no hay suficientes puntos, devuelve vacío
    if not valid:
        return []

    # Pareto (asumiendo max en ambos; si tu modelo es min en alguno, lo ajustamos después)
    pareto = []
    for i, (pi, xi, yi) in enumerate(valid):
        dominated = False
        for j, (pj, xj, yj) in enumerate(valid):
            if j == i:
                continue
            if (xj >= xi and yj >= yi) and (xj > xi or yj > yi):
                dominated = True
                break
        if not dominated:
            pareto.append(pi)
    return pareto
