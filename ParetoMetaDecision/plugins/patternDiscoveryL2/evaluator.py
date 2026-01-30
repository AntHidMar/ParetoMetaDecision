# plugins/patternDiscoveryL2/evaluator.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
from core.governance.decision_schedule import DecisionScheduler, TimeGridSchedule, apply_decision_mode_tri
import json, hashlib
from core.artifacts.pattern_event_logger import PatternEventLogger, PatternEventLoggerConfig
from core.decision_language.ast import complexity_of

@dataclass
class PatternDiscoveryEvaluator:
    domain: Dict[str, Any]
    dataset: Any
    dataset_desc: Dict[str, Any]

    def _get_df(self) -> pd.DataFrame:
        if isinstance(self.dataset, pd.DataFrame):
            return self.dataset
        if isinstance(self.dataset, dict) and "df" in self.dataset:
            return self.dataset["df"]
        raise TypeError("dataset must be a DataFrame or dict with key 'df'")

    def _build_mid_imb_spread(self, df: pd.DataFrame, k: int) -> Tuple[pd.Series, pd.Series, pd.Series]:
        df = df.copy()
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df = df.dropna(subset=["fecha", "priceL2", "sizeL2", "side"])
        df["priceL2"] = pd.to_numeric(df["priceL2"], errors="coerce")
        df["sizeL2"] = pd.to_numeric(df["sizeL2"], errors="coerce")
        df = df.dropna(subset=["priceL2", "sizeL2", "side"])
        df = df.sort_values(["fecha", "side"])

        side_vals = sorted(set(df["side"].dropna().unique().tolist()))
        if set(side_vals).issubset({0, 1}):
            bid_side, ask_side = 1, 0
        elif set(side_vals).issubset({1, 2}):
            bid_side, ask_side = 1, 2
        elif set(side_vals).issubset({-1, 1}):
            bid_side, ask_side = 1, -1
        else:
            raise ValueError(f"unsupported_side_values:{side_vals}")

        bid = df[df["side"] == bid_side]
        ask = df[df["side"] == ask_side]
        if bid.empty or ask.empty:
            raise ValueError("missing_bid_or_ask")

        best_bid = bid.groupby("fecha")["priceL2"].max()
        best_ask = ask.groupby("fecha")["priceL2"].min()
        mid = ((best_bid + best_ask) / 2.0).dropna().sort_index()
        spread = (best_ask - best_bid).dropna().sort_index()

        # top-k sizes
        bid_k = bid.groupby("fecha", group_keys=False).apply(lambda x: x.nlargest(k, "priceL2"))
        ask_k = ask.groupby("fecha", group_keys=False).apply(lambda x: x.nsmallest(k, "priceL2"))
        bid_sz = bid_k.groupby("fecha")["sizeL2"].sum()
        ask_sz = ask_k.groupby("fecha")["sizeL2"].sum()
        denom = (bid_sz + ask_sz).replace(0.0, np.nan)
        imb = ((bid_sz - ask_sz) / denom).dropna().sort_index()

        idx = mid.index.intersection(imb.index).intersection(spread.index)
        return mid.loc[idx], imb.loc[idx], spread.loc[idx]

    def _label(self, mid: pd.Series, horizon: int, labeling: Dict[str, Any]) -> pd.Series:
        mid_vals = mid.values
        ret = (mid_vals[horizon:] - mid_vals[:-horizon]) / mid_vals[:-horizon]
        ret_s = pd.Series(ret, index=mid.index[:-horizon])

        scheme = labeling.get("scheme", "quantile")
        classes = labeling.get("classes", ["UP", "DOWN"])

        if scheme == "quantile":
            q_up = float(labeling.get("q_up", 0.9))
            q_down = float(labeling.get("q_down", 0.1))
            up_th = float(ret_s.quantile(q_up))
            down_th = float(ret_s.quantile(q_down))
        else:
            up_th = float(labeling.get("up_th", 0.001))
            down_th = float(labeling.get("down_th", -0.001))

        y = pd.Series("OTHER", index=ret_s.index)
        if "UP" in classes:
            y[ret_s >= up_th] = "UP"
        if "DOWN" in classes:
            y[ret_s <= down_th] = "DOWN"
        # FLAT opcional si lo añades
        return y

    def _match_rule_flat(    self,    *,    params: Dict[str, Any],    imb: pd.Series,    spread: pd.Series,   d_imb: pd.Series | None,) -> np.ndarray:
        """
        Primer MVP: regla flat muy simple:
          params: {policy: imb_gt|imb_lt|spread_gt|spread_lt, theta: float}
        Luego lo elevamos a AST y combinadores AND/OR.
        """
        pol = params.get("policy", "imb_gt")
        theta = float(params.get("theta", 0.0))

        if pol == "imb_gt":
            return (imb.values > theta)
        if pol == "imb_lt":
            return (imb.values < -theta)
        if pol == "spread_gt":
            return (spread.values > theta)
        if pol == "spread_lt":
            return (spread.values < theta)
        if pol == "dimb_gt" and d_imb is not None:
            return (d_imb.values > theta)
        if pol == "dimb_lt" and d_imb is not None:
            return (d_imb.values < -theta)

        # unknown → match nada
        return np.zeros(len(imb), dtype=bool)

    def _match_rule_ast(
        self,
        *,
        ast: Dict[str, Any],
        imb: pd.Series,
        spread: pd.Series,
        d_imb: pd.Series | None,
    ) -> np.ndarray:    
        """
        AST booleano:
          leaf policy: imb_gt|imb_lt|spread_gt|spread_lt con theta
          combinators: AND|OR con left/right
        """
        pol = ast.get("policy")

        # leaf
        if pol in ("imb_gt", "imb_lt", "spread_gt", "spread_lt", "dimb_gt", "dimb_lt"):
            theta = float(ast.get("theta", 0.0))
            if pol == "imb_gt":
                return (imb.values > theta)
            if pol == "imb_lt":
                return (imb.values < -theta)
            if pol == "spread_gt":
                return (spread.values > theta)
            if pol == "spread_lt":
                return (spread.values < theta)
            if pol == "dimb_gt" and d_imb is not None:
                return (d_imb.values > theta)
            if pol == "dimb_lt" and d_imb is not None:
                return (d_imb.values < -theta)
            return np.zeros(len(imb), dtype=bool)

        # combinators
        if pol in ("AND", "OR"):
            left = self._match_rule_ast(ast=ast["left"], imb=imb, spread=spread, d_imb=d_imb)
            right = self._match_rule_ast(ast=ast["right"], imb=imb, spread=spread, d_imb=d_imb)

            if pol == "AND":
                return left & right
            else:
                return left | right

        # unknown
        return np.zeros(len(imb), dtype=bool)

    def _complexity(node: Dict[str, Any]) -> int:
        p = node.get("policy")
        if p in ("AND", "OR"):
            return 1 + _complexity(node["left"]) + _complexity(node["right"])
        return 1

    def _load_decision_schedule(self, context: Dict[str, Any]) -> TimeGridSchedule:
        ds = (context.get("decision_schedule") if context else None) or self.domain.get("decision_schedule") or {}
        seconds = int(ds.get("seconds", 180))
        mode = str(ds.get("mode", "sample")).lower()
        if mode not in ("sample", "hold"):
            mode = "sample"
        return TimeGridSchedule(seconds=seconds, mode=mode)

    def _pattern_audit_enabled(self) -> bool:
        return bool(
            ((self.domain.get("audit") or {}).get("pattern_events") or {}).get("enabled", False)
        )

    def _decision_audit_enabled(self) -> bool:
        return bool(
            ((self.domain.get("audit") or {}).get("decision_events") or {}).get("enabled", False)
        )

    def evaluate(self, *, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        df = self._get_df()

        # Context activo (MapA9): lo decide problem.context(...)
        ctx = context or {}
        ctx0 = (self.domain.get("context", {}) or {})

        horizon = int(ctx.get("horizon", ctx0.get("horizon", 3)))
        labeling = ctx.get("labeling", ctx0.get("labeling", {})) or {}
        features = ctx.get("features", ctx0.get("features", {})) or {}

        k = int(features.get("k", 1))

        mid, imb, spread = self._build_mid_imb_spread(df, k=k)
        if len(mid) <= horizon + 5:
            return {"ppv": 0.0, "recall": 0.0, "support": 0.0, "complexity": 1.0, "reason": "not_enough_points", "valid": False,}

        y = self._label(mid, horizon=horizon, labeling=labeling)

        # alinear imb/spread con y (y ya está recortado a index[:-horizon])
        idx = y.index.intersection(imb.index).intersection(spread.index)
        y = y.loc[idx]
        imb = imb.loc[idx]
        spread = spread.loc[idx]

        # -------------------------------------------------
        # Payoff base (MapA9): forward return para decision_model
        # -------------------------------------------------
        mid = mid.loc[idx]  # alinear mid también con idx
        fwd_ret = (mid.shift(-horizon) - mid) / mid  # retorno futuro a horizonte h

        # y ya suele venir recortado para no incluir los últimos 'horizon' puntos,
        # pero por seguridad quitamos NaN si quedaran
        valid = fwd_ret.notna()
        if not bool(valid.all()):
            y = y.loc[valid]
            imb = imb.loc[valid]
            spread = spread.loc[valid]
            mid = mid.loc[valid]
            fwd_ret = fwd_ret.loc[valid]
            idx = y.index  # mantener idx consistente

        # delta imbalance (feature opcional)
        if bool(features.get("use_delta_imb", False)):
            d_imb = imb.diff().fillna(0.0)
        else:
            d_imb = None

        # clase target por ahora: UP (luego: por YAML y multi-clase)
        target = labeling.get("target", "UP")

        is_ast = isinstance(params, dict) and "policy" in params and ("left" in params or "right" in params)

        if is_ast:
            match = self._match_rule_ast(ast=params, imb=imb, spread=spread, d_imb=d_imb)
        else:
            match = self._match_rule_flat(params=params, imb=imb, spread=spread, d_imb=d_imb)

        schedule = self._load_decision_schedule(context)
        scheduler = DecisionScheduler(schedule)
        timestamps = list(idx)  # idx ya es el índice alineado de y/imb/spread
        gate = scheduler.gate(timestamps)

        # En discovery, "hold" no tiene sentido semántico para boolean match; lo tratamos como sample.
        match = match & gate

        # -------------------------------------------------
        # Baseline (MapA9): tasa base del target en el dataset
        # -------------------------------------------------
        base_rate_up = float((y.values == target).mean()) if len(y) > 0 else 0.0


        if self._pattern_audit_enabled():
            params_json = json.dumps(params, sort_keys=True, ensure_ascii=False)
            params_hash = hashlib.sha256(params_json.encode("utf-8")).hexdigest()

            domain_json = json.dumps(self.domain, sort_keys=True, ensure_ascii=False)
            domain_hash = hashlib.sha256(domain_json.encode("utf-8")).hexdigest()

            dataset_id = context.get("dataset_id")
            problem_id = context.get("problem_id", "patternDiscoveryL2")
            target = labeling.get("target", "UP")

            cfg = PatternEventLoggerConfig(root_dir="cache/audit/pattern_events/v1")

            with PatternEventLogger(cfg) as log:
                log.write_run_meta({
                    "problem_id": problem_id,
                    "dataset_id": dataset_id,
                    "params_hash": params_hash,
                    "domain_hash": domain_hash,
                    "target": target,
                    "horizon": int(horizon),
                    "schedule": {"type": "time_grid", "seconds": schedule.seconds, "mode": schedule.mode},
                    "labeling": labeling,
                })

                debug_cfg = (self.domain.get("debug") or {})
                progress_every = int(debug_cfg.get("progress_every", 0))
                total = len(timestamps)

                yv = y.values
                for i, ts in enumerate(timestamps):
                    if not gate[i]:
                        reason = "BLOCKED_BY_SCHEDULE"
                    else:
                        reason = "MATCH" if bool(match[i]) else "NO_MATCH"

                    log.log({
                        "ts": pd.Timestamp(ts).isoformat(),
                        "i": int(i),
                        "gate": bool(gate[i]),
                        "match": bool(match[i]),
                        "label": str(yv[i]),
                        "reason_code": reason,
                        "features": {
                            "imbalance": float(imb.values[i]),
                            "spread": float(spread.values[i]),
                        },
                    })

                    if progress_every > 0 and i % progress_every == 0:
                        print(
                            f"[PatternDiscovery] {i}/{total} snapshots "
                            f"({100*i/total:.1f}%)"
                        )

        #complexity = float(_complexity(params) if is_ast else 1)
        complexity = float(complexity_of(params))

        # métricas
        sup = int(match.sum())
        support = sup / len(match) if len(match) > 0 else 0.0
        n_total = int(len(match))

        if sup == 0:
            return {
                "ppv": None,
                "recall": None,
                "support": float(support),
                "complexity": float(complexity),
                "utility": -1e9,
                "reason": "no_support",
                "valid": False,

                # decision_model inputs (para comparación MapA9)
                "base_rate_up": float(base_rate_up),
                "ret_tp_mean": 0.0,
                "ret_fp_mean": 0.0,
                "n_signals": 0,
                "tp": 0,
                "fp": 0,
                "n_total": n_total
            }

        
        tp = int(((y.values == target) & match).sum())
        fp = sup - tp
        pos = int((y.values == target).sum())

        # -------------------------------------------------
        # Payoff stats para decision_model (MapA9)
        # -------------------------------------------------
        y_arr = y.values
        m_arr = match.values if hasattr(match, "values") else match  # match puede ser Series/ndarray

        tp_mask = (y_arr == target) & m_arr
        fp_mask = (y_arr != target) & m_arr

        # fwd_ret está alineado con y (Series); convertimos a ndarray
        r = fwd_ret.values

        tp_returns = r[tp_mask]
        fp_returns = r[fp_mask]

        ret_tp_mean = float(tp_returns.mean()) if tp_returns.size else 0.0
        ret_fp_mean = float(fp_returns.mean()) if fp_returns.size else 0.0

        ppv = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / pos if pos > 0 else 0.0
        support = sup / len(match) if len(match) > 0 else 0.0

        # ---------------------------
        # Governance constraints (MapA9): invalidar reglas patológicas
        # ---------------------------
        g = (self.domain.get("governance") or {}).get("constraints") or {}
        min_support = float(g.get("min_support", 0.0))
        min_ppv = float(g.get("min_ppv", 0.0))
        min_recall = float(g.get("min_recall", 0.0))

        if support < min_support or ppv < min_ppv or recall < min_recall:
            return {
                "ppv": float(ppv),
                "recall": float(recall),
                "support": float(support),
                "complexity": float(complexity),
                "utility": -1e9,
                "reason": "governance_violation",
                "valid": False,
                "base_rate_up": float(base_rate_up),
                "ret_tp_mean": float(ret_tp_mean),
                "ret_fp_mean": float(ret_fp_mean),
                # NUEVO: conteos absolutos (MapA-9, interpretabilidad)
                "n_total": n_total,
                "n_signals": int(sup),
                "tp": int(tp),
                "fp": int(fp),

            }

        # ---------------------------
        # Utility (MapA9): no premiar patrones sin poder predictivo
        # ---------------------------
        u_cfg = self.domain.get("utility", {}) or {}
        lam_c = float(u_cfg.get("lambda_complexity", 0.01))
        lam_s = float(u_cfg.get("lambda_support", 0.0))

        eps = 1e-12
        f1 = (2.0 * ppv * recall) / (ppv + recall + eps)

        # Guardrail: si no hay señal predictiva, no se premia soporte
        if ppv <= 0.0 and recall <= 0.0:
            f1 = 0.0

        utility = float(f1 + lam_s * support - lam_c * float(complexity))

        # --- Decision model derived metrics (MapA-9, domain-agnostic style) ---
        ppv_f = float(ppv)
        rtp = float(ret_tp_mean)
        rfp = float(ret_fp_mean)

        ev_gross = ppv_f * rtp + (1.0 - ppv_f) * rfp

        dm = (self.domain.get("decision_model") or {})
        cost = float(dm.get("cost_per_signal", 0.0)) if bool(dm.get("enabled", False)) else 0.0
        ev_net = ev_gross - cost

        risk = abs(rfp)  # proxy mínimo (mejorable a std/CVaR cuando tengas dist.)
        
        return {
            "ppv": float(ppv),
            "recall": float(recall),
            "support": float(support),
            "complexity": float(complexity),
            "utility": utility,
            
            # decision_model inputs
            "base_rate_up": float(base_rate_up),
            "ret_tp_mean": float(ret_tp_mean),
            "ret_fp_mean": float(ret_fp_mean),
            "ev_gross": float(ev_gross),
            "cost": float(cost),
            "ev_net": float(ev_net),
            "risk": float(risk),
            "valid": True,
        }


def make_evaluator(*, domain: Dict[str, Any], dataset: Dict[str, Any], dataset_desc: Dict[str, Any]) -> PatternDiscoveryEvaluator:
    return PatternDiscoveryEvaluator(domain=domain, dataset=dataset, dataset_desc=dataset_desc)
