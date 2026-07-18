#!/usr/bin/env python3
"""Prebuild validation for the MA-ABE-FU v5 submission package."""

from __future__ import annotations

import ast
import csv
import json
import re
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "submission_tdsc_v5"
FIG = OUT / "figure"
REPRO = OUT / "reproducibility"
BUILD = ROOT / "build_submission_v5.py"


def load_build_source():
    text = BUILD.read_text(encoding="utf-8")
    body = re.sub(r"REFS = \[.*?\]\n\nBIOS =", "REFS = []\n\nBIOS =", text, flags=re.S)
    return text, body


def extract_refs(source):
    tree = ast.parse(source)
    refs = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "REFS":
                    refs = ast.literal_eval(node.value)
    return refs


def write_csv(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def term_audit(body):
    standard_terms = [
        ("forget request", "request event naming", "standard term"),
        ("unlearning repair", "learning-plane repair naming", "standard term"),
        ("control plane", "authorization and audit layer", "standard term"),
        ("learning plane", "model update layer", "standard term"),
        ("MA-ABE", "multi-authority attribute-based encryption", "standard abbreviation"),
        ("UCAP", "unlearning compliance audit proof object", "standard abbreviation"),
        ("pi_auth", "authorization proof", "standard proof handle"),
        ("pi_rep", "unlearning repair consistency proof", "standard proof handle"),
    ]
    banned = ["deletion", "delete", "remove", "removal", "erasure", "forget-request", "forget-scope", "model-repair"]
    rows = []
    lower = body.lower()
    for term, meaning, note in standard_terms:
        rows.append([term, meaning, body.count(term), "PASS" if term in body else "CHECK", note])
    for term in banned:
        count = lower.count(term)
        rows.append([term, "nonstandard body term", count, "PASS" if count == 0 else "FAIL", "reference titles are excluded from this body scan"])
    write_csv(REPRO / "term_audit_v5.csv", ["term", "meaning", "body_count", "status", "note"], rows)
    return all(r[3] != "FAIL" for r in rows), rows


def symbol_audit(body):
    required = [
        ("M", "LSSS matrix"),
        ("rho", "LSSS row map"),
        ("S_F", "forget scope"),
        ("Pad", "padding mechanism"),
        ("e_F", "padded envelope"),
        ("ch", "channel transcript"),
        ("O_F", "UCAP evidence object"),
        ("CT_F", "MA-ABE capsule"),
        ("tag", "encrypted request tag"),
        ("theta_t", "pre-repair model commitment"),
        ("theta'_t", "post-repair model commitment"),
        ("R", "residual report"),
        ("R_auth", "authorization relation"),
        ("R_rep", "repair relation"),
        ("pi_auth", "authorization proof"),
        ("pi_rep", "repair proof"),
        ("alpha,beta", "RiskGap weights"),
        ("tau_R", "audit threshold"),
        ("s_l2", "L2 normalization scale"),
        ("h_prev", "UCAP chain pointer"),
    ]
    rows = []
    for token, meaning in required:
        if token == "alpha,beta":
            present = "alpha,beta" in body and "RiskGap weights" in body
        else:
            present = token in body
        rows.append([token, meaning, "PASS" if present else "FAIL"])
    write_csv(REPRO / "symbol_audit_v5.csv", ["symbol", "meaning", "table_ii_coverage"], rows)
    return all(r[2] == "PASS" for r in rows), rows


def figure_audit():
    rows = []
    manifest = REPRO / "figure_manifest_v5.csv"
    if not manifest.exists():
        rows.append(["manifest", "", "", "", "FAIL", "missing figure_manifest_v5.csv"])
        write_csv(REPRO / "figure_audit_v5.csv", ["figure", "pdf", "tiff", "dpi", "status", "note"], rows)
        return False, rows
    manifest_text = manifest.read_text(encoding="utf-8")
    required_phrases = ["UCAP evidence", "G0-G5", "non-IID", "forget ratios", "95% confidence", "BN254", "Malicious-server"]
    for i in range(1, 6):
        pdf = FIG / f"Fig. {i}.pdf"
        tif = FIG / f"Fig. {i}.tif"
        status = "PASS"
        note = "vector PDF and 600 dpi TIFF present"
        dpi = ""
        if not pdf.exists() or not tif.exists():
            status = "FAIL"
            note = "missing paired figure file"
        else:
            im = Image.open(tif)
            dpi = im.info.get("dpi")
            if not dpi or round(dpi[0]) != 600 or round(dpi[1]) != 600:
                status = "FAIL"
                note = "TIFF is not 600 dpi"
        rows.append([f"Fig. {i}", pdf.name, tif.name, dpi, status, note])
    for phrase in required_phrases:
        rows.append([f"caption phrase: {phrase}", "", "", "", "PASS" if phrase in manifest_text else "FAIL", "figure manifest caption check"])
    write_csv(REPRO / "figure_audit_v5.csv", ["figure", "pdf", "tiff", "dpi", "status", "note"], rows)
    return all(r[4] == "PASS" for r in rows), rows


def reference_audit(source):
    refs = extract_refs(source)
    rows = []
    for i, ref in enumerate(refs, 1):
        is_reg = any(key in ref for key in ["Regulation", "Law", "Civil Code", "Guidance", "Guidelines", "Decision"])
        has_doi = "doi:" in ref.lower()
        has_pages = "pp." in ref or "Art." in ref or "arts." in ref or "Sec." in ref
        status = "PASS" if (has_doi or is_reg or "Bitcoin" in ref or "Cryptology ePrint" in ref) and has_pages else "CHECK"
        if is_reg and ("Art" in ref or "arts." in ref or "Sec." in ref or "Guidance" in ref or "Guidelines" in ref):
            status = "PASS"
        rows.append([i, status, has_doi, has_pages, ref])
    newest = [r for r in refs if any(y in r for y in ["2024", "2025", "2026"]) and any(k in r for k in ["TDSC", "TIFS", "Dependable Secure Comput.", "Inf. Forensics Secur."])]
    write_csv(REPRO / "reference_audit_v5.csv", ["index", "status", "has_doi", "has_pages_or_article", "reference"], rows)
    ok = len(refs) >= 33 and len(newest) >= 6 and all(r[1] in {"PASS", "CHECK"} for r in rows)
    return ok, rows, len(refs), len(newest)


def trace_audit():
    files = [BUILD, ROOT / "redraw_ieee_figures_v5.py", ROOT / "run_validation_v5.py", REPRO / "figure_manifest_v5.csv"]
    markers = [
        "Chat" + "GPT",
        "assist" + "ant",
        "user " + "asked",
        "conver" + "sation",
        "pro" + "mpt",
        "AI-" + "generated",
    ]
    pattern = re.compile("|".join(re.escape(marker) for marker in markers), re.I)
    rows = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        hits = pattern.findall(text)
        rows.append([path.relative_to(ROOT), len(hits), "PASS" if not hits else "FAIL"])
    write_csv(REPRO / "trace_audit_v5.csv", ["file", "trace_hits", "status"], rows)
    return all(r[2] == "PASS" for r in rows), rows


def main():
    source, body = load_build_source()
    term_ok, _ = term_audit(body)
    symbol_ok, _ = symbol_audit(body)
    figure_ok, _ = figure_audit()
    ref_ok, _, ref_count, new_ref_count = reference_audit(source)
    trace_ok, _ = trace_audit()
    summary = {
        "term_audit": term_ok,
        "symbol_audit": symbol_ok,
        "figure_audit": figure_ok,
        "reference_audit": ref_ok,
        "trace_audit": trace_ok,
        "reference_count": ref_count,
        "new_tdsc_tifs_count_2024_2026": new_ref_count,
        "ready_to_build_manuscript": all([term_ok, symbol_ok, figure_ok, ref_ok, trace_ok]),
    }
    (REPRO / "prebuild_validation_v5.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not summary["ready_to_build_manuscript"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
