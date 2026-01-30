# main.py
import pandas as pd
from core.plotting import show_utility_diagram
from core.optimizer import optimize_parameters
from core.market_data import MarketData
from core.evaluator import compute_metrics
from plugins.investment.problem_factory import make_investment_problem
from core.problem import Problem
from plugins.inversionL2.problem_factory import make_problem as make_inversion
import yaml
from core.utility import UtilitySpec
import json
import math

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def evaluate_single_configuration(problem, params):
    return problem.evaluate(params)


def verify_optimization(evaluated: list, best: dict, problem: Problem, domain_cfg: dict, pareto_axes: tuple) -> None:

    """
    Verifica que la optimización está funcionando correctamente:
      1) best maximiza utility
      2) métricas presentes y no None / no NaN
      3) re-eval determinista del best (coincidencia en mean_return/frequency)
      4) no hay params duplicados evaluados (dedup efectivo)
    Lanza AssertionError si algo falla.
    """
    

    # 1) best == max(utility)
    utilities = [x.get("utility") for x in evaluated]
    assert utilities, "evaluated está vacío"
    assert best.get("utility") == max(utilities), "BEST no coincide con el máximo de utility"
    print("OK(1): best == max(utility)")

    # 2) Invariantes de métricas
    required = tuple(domain_cfg.get("validation", {}).get("required_metrics", ["utility"]))
    for i, x in enumerate(evaluated, start=1):
        for k in required:
            assert k in x, f"Falta '{k}' en evaluated[{i}]"
            v = x[k]
            assert v is not None, f"'{k}' es None en evaluated[{i}]"
            if isinstance(v, float):
                assert not math.isnan(v), f"'{k}' es NaN en evaluated[{i}]"
    print("OK(2): métricas presentes y válidas")

    # 3) Re-eval determinista best (sin recargar CSV)
    assert "params" in best, "best no contiene 'params'"
    assert "horizon" in best, "best no contiene 'horizon'"

    re = evaluate_single_configuration(problem, best["params"])
    print("RE-EVAL(best):", re)

    stable = domain_cfg.get("validation", {}).get("stability_metrics", [])
    for k in stable:
        assert abs(float(re[k]) - float(best[k])) < 1e-9, f"{k} cambia en re-eval"


    stable = domain_cfg.get("validation", {}).get("stability_metrics", [])
    eps = float(domain_cfg.get("validation", {}).get("eps", 1e-9))

    for k in stable:
        assert k in re and k in best, f"Falta {k} en re-eval/best"
        assert abs(float(re[k]) - float(best[k])) < eps, f"{k} cambia en re-eval"
    print("OK(3): re-eval coincide (stable_metrics)")

    # 4) No duplicados de params
    sigs = [json.dumps(x["params"], sort_keys=True, ensure_ascii=False) for x in evaluated]
    assert len(sigs) == len(set(sigs)), "Hay params duplicados evaluados (dedup no funciona o no está activo)"
    print("OK(4): no hay duplicados en evaluated")

    # 5) Tamaño de evaluación (info)
    print(f"INFO: combinaciones evaluadas = {len(evaluated)}")


def main():
    csv_path = "data/raw/MES.csv"

    # Cargar una sola vez (si tu plugin lo usa)
    md = MarketData(csv_path)

    domain_yaml = "plugins/inversionL2/domain.yaml"
    domain_cfg = load_yaml(domain_yaml)

    # Problem (plugin) para optimización
    problem = make_inversion({"domain_yaml": domain_yaml})
    assert problem is not None, "problem is None (factory not returning Problem)"

    pareto_axes = tuple(domain_cfg.get("plot", {}).get("pareto_axes", ("utility", "utility")))

    u = domain_cfg.get("utility", {}) or {}
    utility_spec = UtilitySpec(
        lambda_cost=float(u.get("lambda_cost", 0.0)),
        lambda_risk=float(u.get("lambda_risk", 1.0)),
    )

    search_space = domain_cfg.get("search_space") or {}
    assert search_space, "domain_cfg.search_space vacío (revisa plugins/inversionL2/domain.yaml)"

    print("DEBUG problem =", problem)
    print("DEBUG problem type =", type(problem))

    # 1) OPTIMIZA (aquí se crea evaluated)
    evaluated = optimize_parameters(
        problem=problem,
        search_space=search_space,
        utility_spec=utility_spec,
        pareto_axes=pareto_axes,
    )
    # Si optimize_parameters devuelve (evaluated, tracker), usa:
    # evaluated, tracker = optimize_parameters(...)

    assert evaluated, "No se evaluó ningún candidato."

    # 2) BEST
    best = max(evaluated, key=lambda x: x.get("utility", float("-inf")))
    best_params = best["params"]

    # 3) VERIFY (ahora sí)
    verify_optimization(
        evaluated=evaluated,
        best=best,
        problem=problem,
        domain_cfg=domain_cfg,
        pareto_axes=pareto_axes,
    )

    # 4) Prints
    xk, yk = pareto_axes
    print("\n=== BEST CONFIG (dict-only) ===")
    print("params:", best_params)
    print("utility:", best.get("utility"))
    if "metrics" in best and isinstance(best["metrics"], dict):
        print(f"{xk}:", best["metrics"].get(xk))
        print(f"{yk}:", best["metrics"].get(yk))
    else:
        print(f"{xk}:", best.get(xk))
        print(f"{yk}:", best.get(yk))

    # 5) Re-eval puntual
    metrics = evaluate_single_configuration(problem, best_params)
    print("\n=== RE-EVAL (sanity check) ===")
    print(metrics)

    # 6) Plot utilidad
    results_df = pd.DataFrame(evaluated)
    if "utility" not in results_df.columns and "metrics" in results_df.columns:
        try:
            results_df["utility"] = results_df["metrics"].apply(lambda m: (m or {}).get("utility"))
        except Exception:
            pass

    show_utility_diagram(results_df=results_df, best=best)


if __name__ == "__main__":
    main()
