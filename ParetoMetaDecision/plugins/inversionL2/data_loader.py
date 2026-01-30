from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple, Optional
import pandas as pd
import hashlib
import json


def _stable_hash(obj: Any) -> str:
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(s).hexdigest()


def _normalize_side(series: pd.Series) -> pd.Series:
    """
    Normaliza 'side' a {1=bids, 0=asks}.
    Soporta codificaciones típicas:
      - {0,1}: 1=bids, 0=asks (ya OK)
      - {1,2}: 1=bids, 2=asks
      - {-1,1}: 1=bids, -1=asks
    """
    vals = set(pd.unique(series.dropna()))
    if vals.issubset({0, 1}):
        return series.astype(int)

    if vals.issubset({1, 2}):
        # 1 -> bid, 2 -> ask(0)
        return series.map(lambda x: 1 if int(x) == 1 else 0).astype(int)

    if vals.issubset({-1, 1}):
        # 1 -> bid, -1 -> ask(0)
        return series.map(lambda x: 1 if int(x) == 1 else 0).astype(int)

    # Fallback: intenta inferir por precio (heurística)
    # Si el "side" con precio medio más alto probablemente son asks (depende del feed),
    # pero como no hay garantía, preferimos fallar explícito:
    raise ValueError(f"Unsupported 'side' encoding. Unique values: {sorted(list(vals))}")


def _build_snapshot(group: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    Crea un snapshot dict con bids/asks y midprice.
    Espera que 'side' ya esté normalizado a {1 bid, 0 ask}.
    """
    ts = group["fecha"].iloc[0]
    symbol = group["symbol"].iloc[0] if "symbol" in group.columns else None

    bids = group[group["side"] == 1][["priceL2", "sizeL2"]].dropna()
    asks = group[group["side"] == 0][["priceL2", "sizeL2"]].dropna()

    # Convertir a listas de tuples (price, size)
    bid_levels: List[Tuple[float, float]] = [(float(p), float(sz)) for p, sz in bids.to_numpy()]
    ask_levels: List[Tuple[float, float]] = [(float(p), float(sz)) for p, sz in asks.to_numpy()]

    if not bid_levels or not ask_levels:
        # Snapshot inutilizable para midprice/returns
        return None

    best_bid = max(p for p, _ in bid_levels)
    best_ask = min(p for p, _ in ask_levels)
    if best_ask <= 0 or best_bid <= 0:
        return None
    mid = 0.5 * (best_bid + best_ask)

    return {
        "ts": ts,
        "symbol": symbol,
        "bids": bid_levels,
        "asks": ask_levels,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
    }


def load_dataset(dataset_desc: Dict[str, Any]) -> Dict[str, Any]:
    src = dataset_desc["source"]
    if src["format"].lower() == "csv":
        read = src.get("read", {})
        df = pd.read_csv(
            src["path"],
            nrows=read.get("nrows"),
            parse_dates=read.get("parse_dates"),
            dtype=read.get("dtype"),
        )
    else:
        raise ValueError(f"Unsupported format: {src['format']}")

    # fingerprint del fichero para MapA 9 (misma config + datos distintos => dataset distinto)
    st = os.stat(src["path"])
    dataset_desc = dict(dataset_desc)  # copia para no mutar input
    dataset_desc["_source_fingerprint"] = {
        "path": src["path"],
        "size": st.st_size,
        "mtime": int(st.st_mtime),
    }

    dataset_id = dataset_desc.get("dataset_id") or (_stable_hash(dataset_desc) + "-v1")

    # Validación mínima
    req = dataset_desc.get("schema", {}).get("required_columns", [])
    missing = [c for c in req if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset missing columns: {missing}")

    # Normalizaciones básicas
    if "fecha" not in df.columns:
        raise ValueError("Dataset requires 'fecha' column")
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha"]).copy()

    print("df")
    #print(df.head(100).to_string())
    print(df)
        
    if "side" not in df.columns:
        raise ValueError("Dataset requires 'side' column")
    df["side"] = _normalize_side(df["side"])

    # Construcción de snapshots: 1 snapshot por (fecha, symbol)
    group_cols = ["fecha"] + (["symbol"] if "symbol" in df.columns else [])
    snapshots: List[Dict[str, Any]] = []
    dropped = 0

    for _, g in df.groupby(group_cols, sort=True):
        snap = _build_snapshot(g)
        if snap is None:
            dropped += 1
            continue
        snapshots.append(snap)

    # Sanity rápido (muy útil para tu problema actual)
    if snapshots:
        n = len(snapshots)
        print(f"Loaded {n} snapshots (dropped groups without both sides: {dropped})")
        # mira primeros 3
        for i, s in enumerate(snapshots[:3]):
            print("SNAP", i, "ts", s["ts"], "bids", len(s["bids"]), "asks", len(s["asks"]),
                  "best_bid", s["best_bid"], "best_ask", s["best_ask"], "mid", s["mid"])
    else:
        print(f"Loaded 0 snapshots (dropped groups: {dropped}) -> check 'side' and grouping")

    return {"df": df, "snapshots": snapshots, "dataset_id": dataset_id}
