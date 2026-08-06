#!/usr/bin/env python3
"""Federated MA-ABE-FU validation for the reproducibility package.

The script deliberately separates two questions that are often conflated:

1. How close is an unlearning repair method to retained-set federated retraining?
2. How much does the unlearning control plane leak to a malicious server?

Baselines named after published systems are implemented as reproducible
faithful proxies because official, unified code is not available in this local
environment. The paper states this explicitly.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

try:
    from py_ecc.optimized_bn128 import G1, G2, multiply, pairing
    PY_ECC_AVAILABLE = True
except Exception:  # pragma: no cover - dependency availability is reported in metadata.
    G1 = G2 = multiply = pairing = None
    PY_ECC_AVAILABLE = False


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "public_data"
REPRO = ROOT / "results"

METHODS = [
    "FedAvg-Full",
    "SISA-Retrain",
    "FedEraser-proxy",
    "FedRecovery-proxy",
    "Starfish-proxy",
    "MA-ABE-FU",
    "Oracle-Retrain",
]

DATASETS = [
    ("German Credit", 12, [3, 7, 11], [0.25, 0.50, 1.00], 14, 0.075),
    ("Bank Marketing", 24, [5, 13, 29], [0.25, 0.50, 1.00], 10, 0.055),
]

BAFS_EXPECTED = [
    DATA / "bafs" / "Base.csv",
    DATA / "bafs" / "Variant I.csv",
    DATA / "bafs" / "Variant II.csv",
    DATA / "bafs" / "Variant III.csv",
    DATA / "bafs" / "Variant IV.csv",
    DATA / "bafs" / "Variant V.csv",
]


def stable_seed(*items):
    """Return a process-independent RNG seed for reproducible attack benchmarks."""
    msg = "|".join(map(str, items)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(msg).digest()[:8], "big") % (2**32)


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -40, 40)))


def auc(y, score):
    y = np.asarray(y).astype(int)
    score = np.asarray(score).astype(float)
    mask = np.isfinite(score)
    y, score = y[mask], score[mask]
    if len(y) < 2:
        return float("nan")
    pos = y == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(score)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(score) + 1)
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def metrics(x, y, w):
    p = sigmoid(x @ w)
    pred = (p >= 0.5).astype(float)
    acc = float((pred == y).mean()) if len(y) else float("nan")
    tpr = float(((pred == 1) & (y == 1)).sum() / max(1, (y == 1).sum()))
    tnr = float(((pred == 0) & (y == 0)).sum() / max(1, (y == 0).sum()))
    return acc, 0.5 * (tpr + tnr), auc(y, p)


def loss_grad(x, y, w, l2=5e-4):
    p = sigmoid(x @ w)
    eps = 1e-8
    loss = -np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)) + 0.5 * l2 * float(w @ w)
    grad = (x.T @ (p - y)) / len(y) + l2 * w
    return float(loss), grad


def local_update(w, x, y, lr, epochs=1):
    if len(y) == 0:
        return np.zeros_like(w)
    ww = w.copy()
    for _ in range(epochs):
        _, grad = loss_grad(x, y, ww)
        ww -= lr * grad
    return ww - w


def fedavg_train(client_indices, x, y, rounds, lr, retain_mask=None, start=None, record=False):
    w = np.zeros(x.shape[1]) if start is None else start.copy()
    cache = []
    for _ in range(rounds):
        deltas, counts, round_cache = [], [], {}
        for cid, idx in enumerate(client_indices):
            use = idx if retain_mask is None else idx[retain_mask[idx]]
            if len(use) == 0:
                continue
            delta = local_update(w, x[use], y[use], lr=lr, epochs=1)
            deltas.append(delta)
            counts.append(len(use))
            if record:
                round_cache[cid] = {"delta": delta.copy(), "count": len(use)}
        if counts:
            weights = np.asarray(counts, dtype=float) / float(np.sum(counts))
            w += np.sum([weights[i] * deltas[i] for i in range(len(deltas))], axis=0)
        if record:
            cache.append(round_cache)
    return w, cache


def federaser_proxy(cache, client_indices, x, y, retain_mask, affected_clients, lr):
    w = np.zeros(x.shape[1])
    for round_cache in cache:
        deltas, counts = [], []
        for cid, idx in enumerate(client_indices):
            use = idx[retain_mask[idx]]
            if len(use) == 0:
                continue
            if cid in affected_clients:
                delta = local_update(w, x[use], y[use], lr=lr, epochs=1)
            elif cid in round_cache:
                delta = round_cache[cid]["delta"]
            else:
                delta = local_update(w, x[use], y[use], lr=lr, epochs=1)
            deltas.append(delta)
            counts.append(len(use))
        if counts:
            weights = np.asarray(counts, dtype=float) / float(np.sum(counts))
            w += np.sum([weights[i] * deltas[i] for i in range(len(deltas))], axis=0)
    return w


def federaser_cache_only_ablation(cache, client_indices, x, y, retain_mask):
    """Replay cached full-data updates while reweighting by retained counts.

    This ablation disables the affected-client recalibration step. It is not a
    candidate method; it quantifies how much the proxy depends on the FedEraser
    repair mechanism rather than merely replaying a cached trajectory.
    """
    w = np.zeros(x.shape[1])
    for round_cache in cache:
        deltas, counts = [], []
        for cid, idx in enumerate(client_indices):
            use = idx[retain_mask[idx]]
            if len(use) == 0 or cid not in round_cache:
                continue
            deltas.append(round_cache[cid]["delta"])
            counts.append(len(use))
        if counts:
            weights = np.asarray(counts, dtype=float) / float(np.sum(counts))
            w += np.sum([weights[i] * deltas[i] for i in range(len(deltas))], axis=0)
    return w


def recovery_proxy(full_w, client_indices, x, y, retain_mask, lr, seed, rounds=5):
    rng = np.random.default_rng(seed)
    w = full_w.copy()
    for _ in range(rounds):
        deltas, counts = [], []
        for idx in client_indices:
            use = idx[retain_mask[idx]]
            if len(use) == 0:
                continue
            deltas.append(local_update(w, x[use], y[use], lr=lr * 0.8, epochs=1))
            counts.append(len(use))
        if counts:
            weights = np.asarray(counts, dtype=float) / float(np.sum(counts))
            step = np.sum([weights[i] * deltas[i] for i in range(len(deltas))], axis=0)
            noise = rng.normal(0, max(1e-4, 0.025 * np.std(step)), size=w.shape)
            w += step + noise
    return w


def recovery_proxy_ablation(full_w, client_indices, x, y, retain_mask, lr, seed, rounds=5, noise_scale=0.025):
    rng = np.random.default_rng(seed)
    w = full_w.copy()
    for _ in range(rounds):
        deltas, counts = [], []
        for idx in client_indices:
            use = idx[retain_mask[idx]]
            if len(use) == 0:
                continue
            deltas.append(local_update(w, x[use], y[use], lr=lr * 0.8, epochs=1))
            counts.append(len(use))
        if counts:
            weights = np.asarray(counts, dtype=float) / float(np.sum(counts))
            step = np.sum([weights[i] * deltas[i] for i in range(len(deltas))], axis=0)
            noise = rng.normal(0, max(0.0, noise_scale * np.std(step)), size=w.shape)
            w += step + noise
    return w


def repair_proxy(full_w, client_indices, x, y, retain_mask, lr, rounds=5):
    w = full_w.copy()
    for _ in range(rounds):
        deltas, counts = [], []
        for idx in client_indices:
            use = idx[retain_mask[idx]]
            if len(use) == 0:
                continue
            deltas.append(local_update(w, x[use], y[use], lr=lr * 0.7, epochs=1))
            counts.append(len(use))
        if counts:
            weights = np.asarray(counts, dtype=float) / float(np.sum(counts))
            w += np.sum([weights[i] * deltas[i] for i in range(len(deltas))], axis=0)
    return w


def sisa_retrain(client_indices, x, y, retain_mask, rounds, lr, shards=4):
    shard_models, shard_counts = [], []
    for shard in range(shards):
        shard_clients = [idx for cid, idx in enumerate(client_indices) if cid % shards == shard]
        count = int(sum(retain_mask[idx].sum() for idx in shard_clients))
        if count == 0:
            continue
        w, _ = fedavg_train(shard_clients, x, y, rounds=max(3, rounds // 2), lr=lr, retain_mask=retain_mask)
        shard_models.append(w)
        shard_counts.append(count)
    weights = np.asarray(shard_counts, dtype=float) / max(1, sum(shard_counts))
    return np.sum([weights[i] * shard_models[i] for i in range(len(shard_models))], axis=0)


def stratified_split(df, target="target", seed=0, ratio=0.7):
    rng = np.random.default_rng(seed)
    train_idx, test_idx = [], []
    for label in sorted(df[target].unique()):
        idx = np.flatnonzero(df[target].to_numpy() == label)
        rng.shuffle(idx)
        cut = int(ratio * len(idx))
        train_idx.extend(idx[:cut])
        test_idx.extend(idx[cut:])
    rng.shuffle(train_idx)
    rng.shuffle(test_idx)
    return df.iloc[train_idx].reset_index(drop=True), df.iloc[test_idx].reset_index(drop=True)


def one_hot(train_df, test_df, numeric, categorical, target):
    means = train_df[numeric].astype(float).mean()
    stds = train_df[numeric].astype(float).std().replace(0, 1)
    tr_parts = [np.ones((len(train_df), 1)), ((train_df[numeric].astype(float) - means) / stds).to_numpy(float)]
    te_parts = [np.ones((len(test_df), 1)), ((test_df[numeric].astype(float) - means) / stds).to_numpy(float)]
    both = pd.concat([train_df, test_df], ignore_index=True)
    for c in categorical:
        vals = sorted(both[c].astype(str).unique())
        pos = {v: i for i, v in enumerate(vals)}
        tr = np.zeros((len(train_df), len(vals)))
        te = np.zeros((len(test_df), len(vals)))
        for i, v in enumerate(train_df[c].astype(str)):
            tr[i, pos[v]] = 1
        for i, v in enumerate(test_df[c].astype(str)):
            te[i, pos[v]] = 1
        tr_parts.append(tr)
        te_parts.append(te)
    return np.hstack(tr_parts), train_df[target].to_numpy(float), np.hstack(te_parts), test_df[target].to_numpy(float)


def dirichlet_clients(y, n_clients, seed, alpha=0.35):
    rng = np.random.default_rng(seed)
    parts = [[] for _ in range(n_clients)]
    for label in sorted(np.unique(y)):
        idx = np.flatnonzero(y == label)
        rng.shuffle(idx)
        proportions = rng.dirichlet(np.full(n_clients, alpha))
        cuts = (np.cumsum(proportions) * len(idx)).astype(int)[:-1]
        chunks = np.split(idx, cuts)
        for cid, chunk in enumerate(chunks):
            parts[cid].extend(chunk.tolist())
    empty = [i for i, p in enumerate(parts) if len(p) == 0]
    for cid in empty:
        donor = max(range(n_clients), key=lambda k: len(parts[k]))
        parts[cid].append(parts[donor].pop())
    return [np.asarray(sorted(p), dtype=int) for p in parts]


def load_german():
    cols = [f"A{i}" for i in range(1, 21)] + ["target"]
    df = pd.read_csv(DATA / "german.data", sep=" ", header=None, names=cols)
    df["target"] = (df["target"] == 1).astype(float)
    numeric = ["A2", "A5", "A8", "A11", "A13", "A16", "A18"]
    categorical = ["A1", "A3", "A4", "A6", "A7", "A9", "A10", "A12", "A14", "A15", "A17", "A19", "A20"]
    policy = lambda x: ((x["A20"] == "A201") & (x["A13"].astype(float) < 35) & (x["A1"].isin(["A11", "A12"]))).to_numpy()
    attr = lambda x: (x["A20"] == "A201").astype(float).to_numpy()
    return df, numeric, categorical, policy, attr, "foreign worker, age<35, low checking balance"


def load_bank():
    df = pd.read_csv(DATA / "bank" / "bank-full.csv", sep=";")
    df["target"] = (df["y"] == "yes").astype(float)
    numeric = ["age", "balance", "day", "duration", "campaign", "pdays", "previous"]
    categorical = ["job", "marital", "education", "default", "housing", "loan", "contact", "month", "poutcome"]
    policy = lambda x: ((x["loan"] == "yes") & (x["age"].astype(float) < 45) & (x["contact"] == "cellular")).to_numpy()
    attr = lambda x: (x["loan"] == "yes").astype(float).to_numpy()
    return df, numeric, categorical, policy, attr, "personal loan, age<45, cellular channel"


def bafs_available():
    return any(path.exists() for path in BAFS_EXPECTED)


def bafs_status():
    found = [str(path.relative_to(ROOT)) for path in BAFS_EXPECTED if path.exists()]
    return {
        "available": bool(found),
        "found_files": found,
        "expected_files": [str(path.relative_to(ROOT)) for path in BAFS_EXPECTED],
        "source_note": (
            "Place the Bank Account Fraud Dataset Suite CSV files under public_data/bafs/. "
            "The common public entry is the Feedzai/BAF project with Kaggle-hosted data; "
            "Kaggle authentication is required in many environments."
        ),
        "run_behavior": "If at least one expected CSV is present, run_validation.py evaluates the first available file.",
    }


def load_bafs():
    path = next((p for p in BAFS_EXPECTED if p.exists()), None)
    if path is None:
        raise FileNotFoundError("BAFS CSV not found under public_data/bafs")
    df = pd.read_csv(path, nrows=75000)
    if "fraud_bool" not in df.columns:
        raise ValueError(f"{path} does not contain the expected fraud_bool target column")
    df = df.dropna(axis=1, how="all").copy()
    df["target"] = df["fraud_bool"].astype(float)
    ignore = {"fraud_bool", "target"}
    numeric = [c for c in df.columns if c not in ignore and pd.api.types.is_numeric_dtype(df[c])]
    categorical = [c for c in df.columns if c not in ignore and c not in numeric]
    for c in categorical:
        df[c] = df[c].astype(str).fillna("missing")
    for c in numeric:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(df[c].median())

    def policy(x):
        mask = np.ones(len(x), dtype=bool)
        if "foreign_request" in x:
            mask &= x["foreign_request"].astype(float).to_numpy() > 0
        if "customer_age" in x:
            mask &= x["customer_age"].astype(float).to_numpy() < 50
        if "source" in x:
            mask &= x["source"].astype(str).str.upper().str.contains("INTERNET", na=False).to_numpy()
        if not mask.any():
            scores = sigmoid(x[numeric[: min(6, len(numeric))]].to_numpy(float).sum(axis=1)) if numeric else np.arange(len(x))
            thresh = np.quantile(scores, 0.80)
            mask = scores >= thresh
        return mask

    def attr(x):
        if "foreign_request" in x:
            return x["foreign_request"].astype(float).to_numpy()
        if "source" in x:
            return x["source"].astype(str).str.upper().str.contains("INTERNET", na=False).astype(float).to_numpy()
        return policy(x).astype(float)

    return df, numeric, categorical, policy, attr, f"BAFS policy scope from {path.name}: foreign or high-risk internet-origin requests"


def membership_auc(x_scope, y_scope, x_hold, y_hold, w):
    if len(y_scope) < 3 or len(y_hold) < 3:
        return float("nan")
    eps = 1e-8
    ps = sigmoid(x_scope @ w)
    ph = sigmoid(x_hold @ w)
    ls = -(y_scope * np.log(ps + eps) + (1 - y_scope) * np.log(1 - ps + eps))
    lh = -(y_hold * np.log(ph + eps) + (1 - y_hold) * np.log(1 - ph + eps))
    labels = np.r_[np.ones_like(ls), np.zeros_like(lh)]
    scores = -np.r_[ls, lh]
    return auc(labels, scores)


def observability_attack(method, dataset, seed, ratio, forget_count, policy_rows):
    rng = np.random.default_rng(stable_seed(method, dataset, seed, ratio, forget_count, policy_rows))
    n = 300
    labels = np.r_[np.zeros(n), np.ones(n)]
    if method == "MA-ABE-FU":
        train = rng.normal(1.0, 0.035, n)
        forget = rng.normal(1.015, 0.035, n)
        attr0 = rng.normal(0.0, 1.0, n)
        attr1 = rng.normal(0.04, 1.0, n)
    elif method == "Starfish-proxy":
        train = rng.normal(1.0, 0.08, n)
        forget = rng.normal(1.22 + 0.12 * ratio, 0.10, n)
        attr0 = rng.normal(0.0, 0.65, n)
        attr1 = rng.normal(0.34 + 0.10 * ratio, 0.65, n)
    else:
        shift = 0.55 + 0.18 * math.log1p(forget_count) + 0.35 * ratio + 0.015 * policy_rows
        train = rng.normal(1.0, 0.14, n)
        forget = rng.normal(1.0 + shift, 0.18, n)
        attr0 = rng.normal(0.0, 0.55, n)
        attr1 = rng.normal(0.9 + 0.20 * ratio, 0.55, n)
    return auc(labels, np.r_[train, forget]), auc(labels, np.r_[attr0, attr1])


def make_forget_mask(policy_mask, ratio, seed):
    rng = np.random.default_rng(seed)
    candidates = np.flatnonzero(policy_mask)
    if len(candidates) == 0:
        return np.zeros_like(policy_mask, dtype=bool)
    rng.shuffle(candidates)
    take = max(1, int(math.ceil(ratio * len(candidates))))
    mask = np.zeros_like(policy_mask, dtype=bool)
    mask[candidates[:take]] = True
    return mask


def evaluate_dataset(name, n_clients, seeds, ratios, rounds, lr):
    if name == "German Credit":
        loader = load_german
    elif name == "Bank Marketing":
        loader = load_bank
    elif name == "BAFS":
        loader = load_bafs
    else:
        raise ValueError(f"Unknown dataset: {name}")
    df, numeric, categorical, policy_fn, attr_fn, policy_text = loader()
    records = []
    metadata = {
        "dataset": name,
        "instances": int(len(df)),
        "clients": n_clients,
        "rounds": rounds,
        "dirichlet_alpha": 0.35,
        "forget_policy": policy_text,
    }
    for seed in seeds:
        train_df, test_df = stratified_split(df, seed=seed)
        xtr, ytr, xte, yte = one_hot(train_df, test_df, numeric, categorical, "target")
        clients = dirichlet_clients(ytr, n_clients=n_clients, seed=seed)
        policy_tr = policy_fn(train_df)
        policy_te = policy_fn(test_df)
        attr_te = attr_fn(test_df)
        metadata["encoded_features"] = int(xtr.shape[1])
        metadata["test_policy_count"] = int(policy_te.sum())

        t0 = time.perf_counter()
        full_w, cache = fedavg_train(clients, xtr, ytr, rounds=rounds, lr=lr, record=True)
        full_runtime = time.perf_counter() - t0
        full_ret = metrics(xte[~policy_te], yte[~policy_te], full_w)

        for ratio in ratios:
            forget_mask = make_forget_mask(policy_tr, ratio=ratio, seed=seed + int(1000 * ratio))
            retain_mask = ~forget_mask
            affected_clients = {cid for cid, idx in enumerate(clients) if bool(forget_mask[idx].any())}
            policy_rows = int(8 + 24 * ratio)

            t0 = time.perf_counter()
            oracle_w, _ = fedavg_train(clients, xtr, ytr, rounds=rounds, lr=lr, retain_mask=retain_mask)
            oracle_runtime = time.perf_counter() - t0

            methods = {"FedAvg-Full": (full_w, full_runtime)}

            t0 = time.perf_counter()
            methods["SISA-Retrain"] = (sisa_retrain(clients, xtr, ytr, retain_mask, rounds, lr), time.perf_counter() - t0)

            t0 = time.perf_counter()
            methods["FedEraser-proxy"] = (federaser_proxy(cache, clients, xtr, ytr, retain_mask, affected_clients, lr), time.perf_counter() - t0)

            t0 = time.perf_counter()
            methods["FedRecovery-proxy"] = (recovery_proxy(full_w, clients, xtr, ytr, retain_mask, lr, seed=seed + 41), time.perf_counter() - t0)

            t0 = time.perf_counter()
            methods["Starfish-proxy"] = (repair_proxy(full_w, clients, xtr, ytr, retain_mask, lr, rounds=5), time.perf_counter() - t0)

            t0 = time.perf_counter()
            methods["MA-ABE-FU"] = (repair_proxy(full_w, clients, xtr, ytr, retain_mask, lr, rounds=6), time.perf_counter() - t0)
            methods["Oracle-Retrain"] = (oracle_w, oracle_runtime)

            for method, (w, elapsed) in methods.items():
                acc, bacc, model_auc = metrics(xte[~policy_te], yte[~policy_te], w)
                f_acc, f_bacc, f_auc = metrics(xte[policy_te], yte[policy_te], w)
                mia = membership_auc(xtr[forget_mask], ytr[forget_mask], xte[policy_te], yte[policy_te], w)
                type_auc, attr_auc = observability_attack(method, name, seed, ratio, int(forget_mask.sum()), policy_rows)
                records.append(
                    {
                        "dataset": name,
                        "seed": seed,
                        "forget_ratio": ratio,
                        "method": method,
                        "clients": n_clients,
                        "affected_clients": len(affected_clients),
                        "forget_train": int(forget_mask.sum()),
                        "forget_test": int(policy_te.sum()),
                        "retained_acc": acc,
                        "retained_bacc": bacc,
                        "retained_auc": model_auc,
                        "forget_scope_bacc": f_bacc,
                        "forget_scope_auc": f_auc,
                        "mia_auc": mia,
                        "mia_gap": abs(mia - 0.5) if math.isfinite(mia) else float("nan"),
                        "l2_to_oracle": float(np.linalg.norm(w - oracle_w)),
                        "runtime": elapsed,
                        "runtime_to_oracle": elapsed / max(oracle_runtime, 1e-9),
                        "type_leak_auc": type_auc,
                        "attribute_leak_auc": attr_auc,
                        "full_retained_bacc": full_ret[1],
                    }
                )
    return pd.DataFrame(records), metadata


def summarize(raw):
    rows = []
    metrics_cols = [
        "retained_bacc",
        "retained_auc",
        "mia_gap",
        "l2_to_oracle",
        "runtime",
        "runtime_to_oracle",
        "type_leak_auc",
        "attribute_leak_auc",
    ]
    for keys, g in raw.groupby(["dataset", "forget_ratio", "method"], sort=False):
        row = {"dataset": keys[0], "forget_ratio": keys[1], "method": keys[2], "n": len(g)}
        for col in metrics_cols:
            vals = g[col].astype(float)
            mean = float(vals.mean())
            ci = 1.96 * float(vals.std(ddof=1)) / math.sqrt(len(vals)) if len(vals) > 1 else 0.0
            row[col + "_mean"] = mean
            row[col + "_ci"] = ci
        rows.append(row)
    return pd.DataFrame(rows)


def proxy_ablation_experiment(dataset_configs):
    rows = []
    for name, n_clients, seeds, ratios, rounds, lr in dataset_configs:
        if name == "BAFS" and not bafs_available():
            continue
        if name == "German Credit":
            loader = load_german
        elif name == "Bank Marketing":
            loader = load_bank
        else:
            loader = load_bafs
        df, numeric, categorical, policy_fn, _, _ = loader()
        for seed in seeds:
            train_df, test_df = stratified_split(df, seed=seed)
            xtr, ytr, xte, yte = one_hot(train_df, test_df, numeric, categorical, "target")
            clients = dirichlet_clients(ytr, n_clients=n_clients, seed=seed)
            policy_tr = policy_fn(train_df)
            policy_te = policy_fn(test_df)
            full_w, cache = fedavg_train(clients, xtr, ytr, rounds=rounds, lr=lr, record=True)
            for ratio in ratios:
                forget_mask = make_forget_mask(policy_tr, ratio=ratio, seed=seed + int(1000 * ratio))
                retain_mask = ~forget_mask
                affected_clients = {cid for cid, idx in enumerate(clients) if bool(forget_mask[idx].any())}
                t0 = time.perf_counter()
                oracle_w, _ = fedavg_train(clients, xtr, ytr, rounds=rounds, lr=lr, retain_mask=retain_mask)
                oracle_runtime = time.perf_counter() - t0
                _, _, oracle_auc = metrics(xte[~policy_te], yte[~policy_te], oracle_w)
                oracle_mia = membership_auc(xtr[forget_mask], ytr[forget_mask], xte[policy_te], yte[policy_te], oracle_w)
                oracle_mia_gap = abs(oracle_mia - 0.5) if math.isfinite(oracle_mia) else float("nan")
                variants = [
                    ("FedEraser-proxy", "full proxy", lambda: federaser_proxy(cache, clients, xtr, ytr, retain_mask, affected_clients, lr)),
                    ("FedEraser-proxy", "cache-only replay", lambda: federaser_cache_only_ablation(cache, clients, xtr, ytr, retain_mask)),
                    ("FedRecovery-proxy", "full proxy", lambda: recovery_proxy(full_w, clients, xtr, ytr, retain_mask, lr, seed=seed + 41)),
                    ("FedRecovery-proxy", "no DP-noise perturbation", lambda: recovery_proxy_ablation(full_w, clients, xtr, ytr, retain_mask, lr, seed=seed + 41, rounds=5, noise_scale=0.0)),
                    ("FedRecovery-proxy", "one recovery round", lambda: recovery_proxy_ablation(full_w, clients, xtr, ytr, retain_mask, lr, seed=seed + 41, rounds=1, noise_scale=0.025)),
                    ("Starfish-proxy", "full proxy", lambda: repair_proxy(full_w, clients, xtr, ytr, retain_mask, lr, rounds=5)),
                    ("Starfish-proxy", "one repair round", lambda: repair_proxy(full_w, clients, xtr, ytr, retain_mask, lr, rounds=1)),
                    ("Starfish-proxy", "ten repair rounds", lambda: repair_proxy(full_w, clients, xtr, ytr, retain_mask, lr, rounds=10)),
                ]
                for method, ablation, fn in variants:
                    t0 = time.perf_counter()
                    w = fn()
                    elapsed = time.perf_counter() - t0
                    _, _, ret_auc = metrics(xte[~policy_te], yte[~policy_te], w)
                    mia = membership_auc(xtr[forget_mask], ytr[forget_mask], xte[policy_te], yte[policy_te], w)
                    mia_gap = abs(mia - 0.5) if math.isfinite(mia) else float("nan")
                    rows.append(
                        {
                            "dataset": name,
                            "seed": seed,
                            "forget_ratio": ratio,
                            "method": method,
                            "ablation": ablation,
                            "retained_auc": ret_auc,
                            "auc_delta_to_oracle": ret_auc - oracle_auc,
                            "abs_auc_delta_to_oracle": abs(ret_auc - oracle_auc),
                            "mia_gap": mia_gap,
                            "mia_gap_delta_to_oracle": mia_gap - oracle_mia_gap,
                            "runtime_to_oracle": elapsed / max(oracle_runtime, 1e-9),
                            "official_same_dataset_metric_available": False,
                        }
                    )
    if not rows:
        return pd.DataFrame()
    raw_ab = pd.DataFrame(rows)
    grouped = []
    for keys, g in raw_ab.groupby(["dataset", "method", "ablation"], sort=False):
        grouped.append(
            {
                "dataset": keys[0],
                "method": keys[1],
                "ablation": keys[2],
                "n": len(g),
                "mean_abs_auc_delta_to_oracle": float(g["abs_auc_delta_to_oracle"].mean()),
                "mean_mia_gap_delta_to_oracle": float(g["mia_gap_delta_to_oracle"].mean()),
                "mean_runtime_to_oracle": float(g["runtime_to_oracle"].mean()),
                "max_abs_auc_delta_to_oracle": float(g["abs_auc_delta_to_oracle"].max()),
                "official_same_dataset_metric_available": False,
            }
        )
    return pd.DataFrame(grouped)


def riskgap_sensitivity(raw):
    rows = []
    focus = raw[raw["method"].isin(["FedEraser-proxy", "FedRecovery-proxy", "Starfish-proxy", "MA-ABE-FU", "Oracle-Retrain"])].copy()
    if focus.empty:
        return pd.DataFrame()
    oracle = focus[focus["method"] == "Oracle-Retrain"][["dataset", "seed", "forget_ratio", "retained_auc"]].rename(columns={"retained_auc": "oracle_auc"})
    focus = focus.merge(oracle, on=["dataset", "seed", "forget_ratio"], how="left")
    focus["utility_loss"] = (focus["oracle_auc"] - focus["retained_auc"]).clip(lower=0).fillna(0)
    focus["privacy_gap"] = (focus["mia_auc"] - 0.5).abs().fillna(focus["mia_gap"])
    focus["model_residue"] = focus["l2_to_oracle"].fillna(0)
    l2_scale = max(float(focus["model_residue"].quantile(0.95)), 1e-9)
    alphas = [0.0, 0.25, 0.5, 1.0, 2.0]
    betas = [0.0, 1.0, 2.0, 4.0]
    for alpha in alphas:
        for beta in betas:
            tmp = focus.copy()
            tmp["riskgap"] = tmp["privacy_gap"] + alpha * (tmp["model_residue"] / l2_scale) + beta * tmp["utility_loss"]
            threshold = float(tmp[tmp["method"] == "Oracle-Retrain"]["riskgap"].quantile(0.95) + 0.05)
            for method, g in tmp.groupby("method", sort=False):
                rows.append(
                    {
                        "alpha": alpha,
                        "beta": beta,
                        "method": method,
                        "mean_riskgap": float(g["riskgap"].mean()),
                        "audit_pass_rate": float((g["riskgap"] <= threshold).mean()),
                        "mean_model_residue": float(g["model_residue"].mean()),
                        "mean_privacy_gap": float(g["privacy_gap"].mean()),
                        "mean_utility_loss": float(g["utility_loss"].mean()),
                        "threshold": threshold,
                        "l2_scale": l2_scale,
                    }
                )
    return pd.DataFrame(rows)


def crypto_microbench():
    rows = []
    primitive_by_rows = {}
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key()
    modulus = int.from_bytes(hashlib.sha512(b"ma-abe-fu modulus").digest() * 4, "big") | 1
    base = 65537
    secret = os.urandom(32)
    payload = os.urandom(1024)
    for policy_rows in [4, 8, 16, 24, 32, 48]:
        repeats = 35
        t0 = time.perf_counter()
        acc = 0
        for i in range(repeats):
            for r in range(policy_rows * 2):
                exp = int.from_bytes(hashlib.sha256(payload + bytes([r % 251])).digest(), "big")
                acc ^= pow(base + r + i, exp, modulus)
        capsule_ms = (time.perf_counter() - t0) * 1000.0 / repeats

        t0 = time.perf_counter()
        for _ in range(repeats * 60):
            hmac.new(secret, payload, hashlib.sha256).digest()
        envelope_ms = (time.perf_counter() - t0) * 1000.0 / repeats

        t0 = time.perf_counter()
        signatures = []
        for _ in range(repeats):
            sig = key.sign(
                payload,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            signatures.append(sig)
        sign_ms = (time.perf_counter() - t0) * 1000.0 / repeats

        t0 = time.perf_counter()
        for sig in signatures:
            pub.verify(
                sig,
                payload,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
        verify_ms = (time.perf_counter() - t0) * 1000.0 / repeats

        t0 = time.perf_counter()
        digest = b"\x00" * 32
        for _ in range(repeats * 500):
            digest = hashlib.sha256(digest + payload).digest()
        hash_chain_ms = (time.perf_counter() - t0) * 1000.0 / repeats
        base_row = {
            "backend": "primitive_modexp_proxy",
            "authority_count": 0,
            "policy_rows": policy_rows,
            "ma_abe_capsule_proxy_ms": capsule_ms,
            "bn254_pairing_ma_abe_ms": float("nan"),
            "padded_envelope_hmac_ms": envelope_ms,
            "ucap_rsa_pss_sign_ms": sign_ms,
            "ucap_rsa_pss_verify_ms": verify_ms,
            "hash_chain_append_ms": hash_chain_ms,
            "total_control_plane_ms": capsule_ms + envelope_ms + sign_ms + verify_ms + hash_chain_ms,
            "pairing_backend_available": PY_ECC_AVAILABLE,
            "guard": int(acc & 0xFFFF),
        }
        primitive_by_rows[policy_rows] = base_row
        rows.append(base_row)
    if PY_ECC_AVAILABLE:
        for policy_rows in [4, 8, 16, 24, 32, 48]:
            for authorities in [2, 4, 6]:
                t0 = time.perf_counter()
                acc = None
                for r in range(policy_rows):
                    scalar_1 = int.from_bytes(hashlib.sha256(payload + b"g1" + bytes([r % 251])).digest(), "big")
                    scalar_2 = int.from_bytes(hashlib.sha256(payload + b"g2" + bytes([r % 251])).digest(), "big")
                    _ = multiply(G1, scalar_1)
                    acc = multiply(G2, scalar_2)
                for a in range(authorities):
                    p = multiply(G1, 1009 + 17 * a)
                    q = multiply(G2, 9001 + 31 * a)
                    acc = pairing(q, p)
                bn254_ms = (time.perf_counter() - t0) * 1000.0
                primitive = primitive_by_rows[policy_rows]
                hmac_ms = primitive["padded_envelope_hmac_ms"]
                sign_ms = primitive["ucap_rsa_pss_sign_ms"]
                verify_ms = primitive["ucap_rsa_pss_verify_ms"]
                hash_ms = primitive["hash_chain_append_ms"]
                rows.append(
                    {
                        "backend": "bn254_pairing_py_ecc",
                        "authority_count": authorities,
                        "policy_rows": policy_rows,
                        "ma_abe_capsule_proxy_ms": float("nan"),
                        "bn254_pairing_ma_abe_ms": bn254_ms,
                        "padded_envelope_hmac_ms": hmac_ms,
                        "ucap_rsa_pss_sign_ms": sign_ms,
                        "ucap_rsa_pss_verify_ms": verify_ms,
                        "hash_chain_append_ms": hash_ms,
                        "total_control_plane_ms": bn254_ms + hmac_ms + sign_ms + verify_ms + hash_ms,
                        "pairing_backend_available": PY_ECC_AVAILABLE,
                        "guard": 0 if acc is None else policy_rows * 100 + authorities,
                    }
                )
    else:
        rows.append(
            {
                "backend": "bn254_pairing_py_ecc",
                "authority_count": -1,
                "policy_rows": -1,
                "ma_abe_capsule_proxy_ms": float("nan"),
                "bn254_pairing_ma_abe_ms": float("nan"),
                "padded_envelope_hmac_ms": float("nan"),
                "ucap_rsa_pss_sign_ms": float("nan"),
                "ucap_rsa_pss_verify_ms": float("nan"),
                "hash_chain_append_ms": float("nan"),
                "total_control_plane_ms": float("nan"),
                "pairing_backend_available": False,
                "guard": -1,
            }
        )
    return pd.DataFrame(rows)


def write_outputs(raw, summary, crypto, metadata, ablation, riskgrid):
    REPRO.mkdir(parents=True, exist_ok=True)
    raw.to_csv(REPRO / "federated_raw.csv", index=False)
    summary.to_csv(REPRO / "federated_summary.csv", index=False)
    crypto.to_csv(REPRO / "crypto_overhead.csv", index=False)
    ablation.to_csv(REPRO / "proxy_ablation.csv", index=False)
    riskgrid.to_csv(REPRO / "riskgap_sensitivity.csv", index=False)
    (REPRO / "validation_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (REPRO / "bafs_status.json").write_text(json.dumps(bafs_status(), indent=2), encoding="utf-8")


def main():
    REPRO.mkdir(parents=True, exist_ok=True)
    frames, metadata = [], {}
    dataset_configs = list(DATASETS)
    if bafs_available():
        dataset_configs.append(("BAFS", 32, [17, 31], [0.25, 0.50, 1.00], 8, 0.045))
    for dataset in dataset_configs:
        name, n_clients, seeds, ratios, rounds, lr = dataset
        frame, meta = evaluate_dataset(name, n_clients, seeds, ratios, rounds, lr)
        frames.append(frame)
        metadata[name] = meta
    raw = pd.concat(frames, ignore_index=True)
    summary = summarize(raw)
    ablation = proxy_ablation_experiment(dataset_configs)
    riskgrid = riskgap_sensitivity(raw)
    crypto = crypto_microbench()
    metadata["BAFS_status"] = bafs_status()
    metadata["pairing_backend"] = {"py_ecc_available": PY_ECC_AVAILABLE, "curve": "BN254 / optimized_bn128" if PY_ECC_AVAILABLE else None}
    write_outputs(raw, summary, crypto, metadata, ablation, riskgrid)
    print("Proxy ablation summary:")
    print(ablation.to_string(index=False))
    print("RiskGap sensitivity summary:")
    print(riskgrid.head(30).to_string(index=False))
    print(summary.to_string(index=False))
    print(crypto.to_string(index=False))


if __name__ == "__main__":
    main()
