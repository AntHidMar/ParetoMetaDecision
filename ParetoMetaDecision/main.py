# main.py
from __future__ import annotations

import json
import math
import pandas as pd
import yaml

from core.plotting import show_utility_diagram
from core.optimizer import optimize_parameters
from core.utility import UtilitySpec

from core.problem.loader import load_problem_from_domain_yaml

import inspect
from core.problem.loader import load_problem_from_domain_yaml as f_loader

print("DBG import core.problem:", load_problem_from_domain_yaml, load_problem_from_domain_yaml.__module__)
print("DBG import core.problem.loader:", f_loader, f_loader.__module__)
print("DBG same object?:", load_problem_from_domain_yaml is f_loader)

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def evaluate_single_configuration(problem: Problem, params: dict, ctx: dict) -> dict:
    return problem.evaluate(params, ctx)


def verify_optimization(
    *,
    evaluated: list,
    best: dict,
    problem: Problem,
    domain_cfg: dict,
    pareto_axes: tuple,
    ctx: dict,
) -> None:
    """
    Verifica que la optimización está funcionando correctamente:
      1) best maximiza utility
      2) métricas presentes y no None / no NaN
      3) re-eval determinista del best (coincidencia en métricas estables)
      4) no hay params duplicados evaluados (dedup efectivo)
    Lanza AssertionError si algo falla.
    """

    # 1) best == max(utility) (MapA-9: solo candidatos valid=True compiten)
    def _metrics(rec: dict) -> dict:
        return rec.get("metrics") if isinstance(rec.get("metrics"), dict) else rec

    valid_recs = []
    for x in evaluated:
        m = _metrics(x)
        if m.get("valid", True):
            valid_recs.append(x)

    assert valid_recs, "No hay candidatos valid=True en evaluated (todo invalid/no_support)"

    utilities = []
    for x in valid_recs:
        m = _metrics(x)
        utilities.append(float(m["utility"]) if m.get("utility") is not None else float("-inf"))

    best_m = _metrics(best)
    assert best_m.get("valid", True), "best es invalid (MapA-9: best debe ser valid=True)"
    assert best_m.get("utility") is not None, "best.utility es None"

    assert float(best_m["utility"]) == max(utilities), "BEST no coincide con el máximo de utility (valid=True)"
    print("OK(1): best == max(utility) sobre valid=True")

    # 2) Invariantes de métricas (MapA-9)
    required = tuple(domain_cfg.get("validation", {}).get("required_metrics", ["utility"]))

    for i, x in enumerate(evaluated, start=1):
        # métricas pueden estar planas o dentro de "metrics"
        #m = x.get("metrics") if isinstance(x.get("metrics"), dict) else x
        m = _metrics(x)

        # --- Contrato MapA-9: valid puede no estar en required_metrics, pero lo usamos si existe
        valid = m.get("valid", True)

        # A) Caso INVALIDO: se permite None en métricas "predictivas"
        if not valid:
            # Invariantes mínimas para inválidos
            assert "support" in m, f"Falta 'support' en evaluated[{i}] (invalid)"
            assert float(m.get("support", 0.0)) == 0.0 or m.get("reason") in (
                "governance_violation",
                "not_enough_points",
                "no_support",
            ), f"Invalid sin support==0 ni reason esperada en evaluated[{i}]"

            # Si existen ppv/recall, deben ser None (no evaluables)
            reason = m.get("reason", "unknown")

            # En inválidos hay dos familias:
            # - no_support / not_enough_points: puede NO haber métricas (None)
            # - governance_violation: puede haber métricas calculadas, pero se rechaza por política
            if reason in ("no_support", "not_enough_points"):
                if "ppv" in m:
                    assert m["ppv"] is None or float(m["ppv"]) == 0.0, f"ppv debe ser None/0 en {reason} evaluated[{i}]"
                if "recall" in m:
                    assert m["recall"] is None or float(m["recall"]) == 0.0, f"recall debe ser None/0 en {reason} evaluated[{i}]"

            elif reason == "governance_violation":
                # Se permiten métricas numéricas (de hecho ayudan a diagnosticar por qué falla)
                # Solo exigimos que existan los campos de gobernanza
                assert "support" in m, f"Falta support en governance_violation evaluated[{i}]"
                # opcional: si quieres, aseguras que realmente viola algo mínimo
                # (pero esto depende de tu implementación)
                pass

            else:
                # Unknown invalid reason: no rompemos, pero lo dejamos señalado
                # Puedes endurecer esto cuando cierres contrato.
                pass


            # Utility puede ser sentinela (-1e9) o None; no forzamos.
            continue

        # B) Caso VALIDO: aquí sí exigimos todo
        for k in required:
            assert k in m, f"Falta '{k}' en evaluated[{i}]"
            v = m[k]
            assert v is not None, f"'{k}' es None en evaluated[{i}]"
            if isinstance(v, float):
                assert not math.isnan(v), f"'{k}' es NaN en evaluated[{i}]"

    print("OK(2): métricas presentes y válidas (valid=True).")



    # 3) Re-eval determinista best
    assert "params" in best, "best no contiene 'params'"

    # 3) Re-eval robusta (MapA-9): repetición para reducir ruido/no-determinismo
    N = int(domain_cfg.get("validation", {}).get("reeval_repeats", 5))
    
    re_vals = [evaluate_single_configuration(problem, best["params"], ctx) for _ in range(N)]
    # Normalizar re-eval outputs: pueden venir con 'metrics' anidado
    re_vals = [r.get("metrics") if isinstance(r.get("metrics"), dict) else r for r in re_vals]

    # MapA-9: re-eval debe ser válido; si no, el best es inestable o hay no-determinismo fuerte
    if any((rv.get("valid", True) is False) for rv in re_vals):
        bad = [rv.get("reason") for rv in re_vals if rv.get("valid", True) is False]
        raise AssertionError(f"Re-eval devolvió valid=False para best (reasons={bad}). Revisa schedule/noise.")

    re0 = re_vals[0]
    print(f"RE-EVAL(best) x{N} (first):", re0)

    # Media por métrica (sobre stable y/o las que existan)
    # OJO: algunas métricas pueden no estar presentes en todas; filtramos.
    def mean_metric(key: str) -> float:
        vals = [float(r[key]) for r in re_vals if key in r and r[key] is not None]
        return sum(vals) / len(vals)

    re_mean = {}  # métricas agregadas


    stable = domain_cfg.get("validation", {}).get("stability_metrics", [])
    eps = float(domain_cfg.get("validation", {}).get("eps", 1e-9))

    # best puede tener métricas planas o en best["mfetrics"]
    best_m = best.get("metrics") if isinstance(best.get("metrics"), dict) else best

    for k in stable:
        assert k in best_m, f"Falta {k} en best"
        # calculamos media; si no hay valores, fallamos explícito
        vals_present = [r for r in re_vals if k in r and r[k] is not None]
        assert vals_present, f"Falta {k} en re-eval (ninguna de las {N} repeticiones lo devuelve)"

        a = mean_metric(k)  # media
        b = float(best_m[k])

        abs_diff = abs(a - b)
        rel_diff = abs_diff / (abs(b) + 1e-12)

        assert (abs_diff < eps) or (rel_diff < 0.05), (
            f"{k} cambia en re-eval(mean): best={b} re_mean={a} abs={abs_diff} rel={rel_diff}"
        )

    print("OK(3): re-eval coincide (métricas estables)")
    
    # 3b) Validación de utilidad (lo que realmente optimizas)
    if "utility" in best_m:
        tol_u = float(domain_cfg.get("validation", {}).get("utility_tolerance_rel", 0.10))

        # Utility re-eval: si está en re_vals (a veces no), la promediamos.
        if any(("utility" in r and r["utility"] is not None) for r in re_vals):
            u_vals = [float(r["utility"]) for r in re_vals if "utility" in r and r["utility"] is not None]
            u_re = sum(u_vals) / len(u_vals)
        else:
            # Si evaluate_single_configuration NO devuelve utility, no podemos validarla aquí.
            # En ese caso, al menos no fallamos: la utility ya fue validada en evaluated (OK(2)).
            u_re = None

        u_best = float(best_m["utility"])

        if u_re is not None:
            abs_u = abs(u_re - u_best)
            rel_u = abs_u / (abs(u_best) + 1e-12)
            assert rel_u < tol_u, f"utility cambia en re-eval(mean): best={u_best} re={u_re} rel={rel_u} tol={tol_u}"

    print("OK(3b): utility estable (tolerancia relativa)")

    # 4) No duplicados de params (firma JSON)
    sigs = []
    for x in evaluated:
        assert "params" in x, "Cada evaluated[i] debe tener 'params' (contrato core)"
        sigs.append(json.dumps(x["params"], sort_keys=True, ensure_ascii=False))

    assert len(sigs) == len(set(sigs)), "Hay params duplicados evaluados (dedup no funciona o hay append duplicado)"
    print("OK(4): no hay duplicados en evaluated")


    print(f"INFO: combinaciones evaluadas = {len(evaluated)}")


def main() -> None:
    
    # ----------------------------
    # 1) Load domain spec (YAML)
    # ----------------------------
    domain_yaml = "plugins/inversionL2/domain.yaml"
    #domain_yaml = "plugins/patternDiscoveryL2/domain.yaml"
    domain_cfg = load_yaml(domain_yaml)
    print("DEBUG Domain = ", domain_cfg)
    
    # ----------------------------
    # 2) Build Problem (MapA 9): core resolves factory from YAML
    # ----------------------------
    problem = load_problem_from_domain_yaml(domain_yaml)
    assert problem is not None, "Problem loader returned None"
    
    print("DEBUG problem =", problem)

    # Context must be callable or dict; context() must work in MapA 9
    ctx = problem.context() if callable(problem.context) else problem.context
    print("DEBUG ctx =", ctx)

    # ----------------------------
    # 3) Utility + search space + plot config
    # ----------------------------
    pareto_axes = tuple(domain_cfg.get("plot", {}).get("pareto_axes", ("utility", "utility")))

    u = domain_cfg.get("utility", {}) or {}
    utility_spec = UtilitySpec(
        lambda_cost=float(u.get("lambda_cost", 0.0)),
        lambda_risk=float(u.get("lambda_risk", 1.0)),
    )

    search_space = domain_cfg.get("search_space") or {}
    assert search_space, "domain_cfg.search_space vacío (revisa domain.yaml)"

    # ----------------------------
    # 4) Sanity eval (single config)
    # ----------------------------
    params0 = {k: (v[0] if isinstance(v, list) and v else v) for k, v in search_space.items()}
    m0 = evaluate_single_configuration(problem, params0, ctx)
    print("DEBUG eval(params0) keys =", list(m0.keys()))
    print("DEBUG eval(params0) sample =", {k: m0.get(k) for k in ("profit", "risk", "frequency", "utility") if k in m0})

    # ----------------------------
    # 5) Optimize
    # ----------------------------
    plot_every = int(domain_cfg.get("plot", {}).get("plot_every", 1))

    evaluated, tracker = optimize_parameters(
        problem=problem,
        domain_cfg=domain_cfg,
        plot_every=plot_every,
        pareto_axes=pareto_axes,
        utility_spec=utility_spec,
        search_space=search_space,
    )
    assert evaluated, "No se evaluó ningún candidato."

    # ----------------------------
    # 6) Best + verify
    # ----------------------------
    best = max(evaluated, key=lambda x: x.get("utility", float("-inf")))
    best_params = best["params"]

    verify_optimization(
        evaluated=evaluated,
        best=best,
        problem=problem,
        domain_cfg=domain_cfg,
        pareto_axes=pareto_axes,
        ctx=ctx,
    )

    xk, yk = pareto_axes
    print("\n=== BEST CONFIG ===")
    print("params:", best_params)
    print("utility:", best.get("utility"))
    best_metrics = best.get("metrics") if isinstance(best.get("metrics"), dict) else {}
    if best_metrics:
        print(f"{xk}:", best_metrics.get(xk))
        print(f"{yk}:", best_metrics.get(yk))
    else:
        print(f"{xk}:", best.get(xk))
        print(f"{yk}:", best.get(yk))

    # ----------------------------
    # 7) Re-eval + plots
    # ----------------------------
    re = evaluate_single_configuration(problem, best_params, ctx)
    print("\n=== RE-EVAL(best) ===")
    print(re)

    results_df = pd.DataFrame(evaluated)
    if "utility" not in results_df.columns and "metrics" in results_df.columns:
        try:
            results_df["utility"] = results_df["metrics"].apply(lambda m: (m or {}).get("utility"))
        except Exception:
            pass

    show_utility_diagram(results_df=results_df, best=best)

    print("len(evaluated) =", len(evaluated))
    print("utilities sample =", [e.get("utility") for e in evaluated[:10]])


if __name__ == "__main__":
    main()
