#!/usr/bin/env python3
"""Draw the five main MA-ABE-FU IEEE figures as vector PDFs and 600 dpi TIFFs."""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from reportlab.lib.colors import Color
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "submission_tifs_v6"
FIG = OUT / "figure"
REPRO = OUT / "reproducibility"
PDFTOCAIRO = Path(os.environ.get("PDFTOCAIRO") or shutil.which("pdftocairo") or "pdftocairo")

DPI = 600
WIDTH_IN = 7.16
WIDTH = WIDTH_IN * 72

INK = (20, 24, 32)
MUTED = (83, 92, 108)
GRID = (214, 221, 230)
LIGHT = (247, 249, 252)
WHITE = (255, 255, 255)
GREEN = (0, 158, 115)
ORANGE = (230, 159, 0)
BLUE = (0, 114, 178)
SKY = (86, 180, 233)
RED = (213, 94, 0)
PINK = (204, 121, 167)
BLACK = (0, 0, 0)

METHODS = [
    "FedEraser-proxy",
    "FedRecovery-proxy",
    "Starfish-proxy",
    "MA-ABE-FU",
    "Oracle-Retrain",
]

SHORT = {
    "FedAvg-Full": "FedAvg",
    "SISA-Retrain": "SISA",
    "FedEraser-proxy": "FedEraser",
    "FedRecovery-proxy": "FedRecovery",
    "Starfish-proxy": "Starfish",
    "MA-ABE-FU": "MA-ABE-FU",
    "Oracle-Retrain": "Oracle",
}

COLORS = {
    "FedAvg-Full": BLUE,
    "SISA-Retrain": GREEN,
    "FedEraser-proxy": ORANGE,
    "FedRecovery-proxy": SKY,
    "Starfish-proxy": RED,
    "MA-ABE-FU": PINK,
    "Oracle-Retrain": BLACK,
}

LINE_DASH = {
    "FedEraser-proxy": [2, 2],
    "FedRecovery-proxy": [5, 2],
    "Starfish-proxy": [7, 3],
    "MA-ABE-FU": [],
    "Oracle-Retrain": [4, 2, 1, 2],
}


def rgb(value):
    r, g, b = value
    return Color(r / 255, g / 255, b / 255)


def lighten(value, factor=0.18):
    return tuple(int(v + (255 - v) * factor) for v in value)


def ci(values) -> float:
    vals = np.asarray(values, dtype=float)
    vals = vals[np.isfinite(vals)]
    if len(vals) <= 1:
        return 0.0
    return float(1.96 * vals.std(ddof=1) / math.sqrt(len(vals)))


def data_map(v, lo, hi, a, b, invert=False):
    vv = min(max(float(v), lo), hi)
    t = (vv - lo) / (hi - lo)
    if invert:
        t = 1 - t
    return a + t * (b - a)


class VFigure:
    def __init__(self, name: str, height_in: float):
        self.name = name
        self.width = WIDTH
        self.height = height_in * 72
        FIG.mkdir(parents=True, exist_ok=True)
        self.pdf_path = FIG / f"{name}.pdf"
        self.c = canvas.Canvas(str(self.pdf_path), pagesize=(self.width, self.height))

    def y(self, top_y: float) -> float:
        return self.height - top_y

    def text(self, x, y, value, size=8.5, color=INK, bold=False, align="left"):
        font = "Helvetica-Bold" if bold else "Helvetica"
        self.c.setFillColor(rgb(color))
        self.c.setFont(font, size)
        yy = self.y(y)
        if align == "center":
            self.c.drawCentredString(x, yy, str(value))
        elif align == "right":
            self.c.drawRightString(x, yy, str(value))
        else:
            self.c.drawString(x, yy, str(value))

    def wrapped(self, x, y, value, width, size=8.0, color=INK, bold=False, leading=None):
        font = "Helvetica-Bold" if bold else "Helvetica"
        words = str(value).split()
        lines, current = [], ""
        for word in words:
            trial = word if not current else current + " " + word
            if stringWidth(trial, font, size) <= width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        leading = leading or size * 1.22
        for i, line in enumerate(lines):
            self.text(x, y + i * leading, line, size=size, color=color, bold=bold)
        return y + len(lines) * leading

    def line(self, x0, y0, x1, y1, color=INK, width=0.8, dash=None):
        self.c.setStrokeColor(rgb(color))
        self.c.setLineWidth(width)
        self.c.setDash(dash or [])
        self.c.line(x0, self.y(y0), x1, self.y(y1))
        self.c.setDash([])

    def rect(self, x, y, w, h, fill=WHITE, stroke=GRID, width=0.8, radius=4):
        self.c.setFillColor(rgb(fill))
        self.c.setStrokeColor(rgb(stroke))
        self.c.setLineWidth(width)
        self.c.roundRect(x, self.y(y + h), w, h, radius, fill=1, stroke=1)

    def marker(self, x, y, method, r=3.0, fill=None):
        color = fill or COLORS.get(method, INK)
        self.c.setFillColor(rgb(color))
        self.c.setStrokeColor(rgb(INK))
        self.c.setLineWidth(0.7)
        yy = self.y(y)
        if method == "FedEraser-proxy":
            path = self.c.beginPath()
            path.moveTo(x, yy + r)
            path.lineTo(x - r, yy - r)
            path.lineTo(x + r, yy - r)
            path.close()
            self.c.drawPath(path, fill=1, stroke=1)
        elif method == "FedRecovery-proxy":
            path = self.c.beginPath()
            path.moveTo(x, yy + r)
            path.lineTo(x - r, yy)
            path.lineTo(x, yy - r)
            path.lineTo(x + r, yy)
            path.close()
            self.c.drawPath(path, fill=1, stroke=1)
        elif method == "Starfish-proxy":
            pts = [(x + r * math.cos(a), yy + r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 7)[:-1]]
            path = self.c.beginPath()
            path.moveTo(*pts[0])
            for pt in pts[1:]:
                path.lineTo(*pt)
            path.close()
            self.c.drawPath(path, fill=1, stroke=1)
        elif method == "MA-ABE-FU":
            pts = []
            for i in range(10):
                rr = r * 1.28 if i % 2 == 0 else r * 0.55
                a = math.pi / 2 + i * math.pi / 5
                pts.append((x + rr * math.cos(a), yy + rr * math.sin(a)))
            path = self.c.beginPath()
            path.moveTo(*pts[0])
            for pt in pts[1:]:
                path.lineTo(*pt)
            path.close()
            self.c.drawPath(path, fill=1, stroke=1)
        elif method == "Oracle-Retrain":
            self.c.setStrokeColor(rgb(INK))
            self.c.setLineWidth(1.2)
            self.c.line(x - r, yy - r, x + r, yy + r)
            self.c.line(x - r, yy + r, x + r, yy - r)
        else:
            self.c.circle(x, yy, r, fill=1, stroke=1)

    def arrow(self, x0, y0, x1, y1, color=INK):
        self.line(x0, y0, x1, y1, color=color, width=1.4)
        ang = math.atan2(self.y(y1) - self.y(y0), x1 - x0)
        head = 5
        yy = self.y(y1)
        p = self.c.beginPath()
        p.moveTo(x1, yy)
        p.lineTo(x1 - head * math.cos(ang - 0.55), yy - head * math.sin(ang - 0.55))
        p.lineTo(x1 - head * math.cos(ang + 0.55), yy - head * math.sin(ang + 0.55))
        p.close()
        self.c.setFillColor(rgb(color))
        self.c.drawPath(p, fill=1, stroke=0)

    def save(self):
        self.c.showPage()
        self.c.save()
        render_to_tiff(self.pdf_path, FIG / f"{self.name}.tif")


def render_to_tiff(pdf_path: Path, tiff_path: Path):
    if not PDFTOCAIRO.exists():
        raise FileNotFoundError(f"pdftocairo not found at {PDFTOCAIRO}")
    fc_cache = ROOT / ".fontconfig-cache"
    fc_cache.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["XDG_CACHE_HOME"] = str(fc_cache)
    env["FC_CACHEDIR"] = str(fc_cache)
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        subprocess.run(
            [str(PDFTOCAIRO), "-r", str(DPI), "-tiff", str(pdf_path), str(prefix)],
            check=True,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=90,
        )
        generated = Path(str(prefix) + "-1.tif")
        with Image.open(generated) as im:
            im.save(tiff_path, compression="tiff_lzw", dpi=(DPI, DPI))


def clear_generated_figures():
    FIG.mkdir(parents=True, exist_ok=True)
    for old in FIG.glob("Fig. *.*"):
        old.unlink()


def panel_title(fig, x, y, panel, title, subtitle=""):
    fig.text(x, y, panel, size=11.0, bold=True)
    fig.text(x + 15, y, title, size=10.8, bold=True)
    if subtitle:
        fig.text(x + 15, y + 13, subtitle, size=8.2, color=MUTED)


def draw_axes(fig, box, x_label="", y_label="", x_ticks=None, y_ticks=None, x_fmt="{:.2f}", y_fmt="{:.2f}"):
    x0, y0, x1, y1 = box
    fig.line(x0, y1, x1, y1, width=0.8)
    fig.line(x0, y0, x0, y1, width=0.8)
    if y_ticks:
        lo, hi, vals = y_ticks
        for val in vals:
            y = data_map(val, lo, hi, y1, y0)
            fig.line(x0, y, x1, y, color=GRID, width=0.35)
            fig.text(x0 - 4, y + 2.5, y_fmt.format(val), size=8.0, color=MUTED, align="right")
    if x_ticks:
        lo, hi, vals = x_ticks
        for val in vals:
            x = data_map(val, lo, hi, x0, x1)
            fig.line(x, y1, x, y1 + 3, width=0.5)
            fig.text(x, y1 + 12, x_fmt.format(val), size=8.0, color=MUTED, align="center")
    if x_label:
        fig.text((x0 + x1) / 2, y1 + 25, x_label, size=8.1, color=MUTED, bold=True, align="center")
    if y_label:
        fig.text(x0, y0 - 14, y_label, size=8.0, color=MUTED, bold=True)


def method_legend(fig, x, y, methods, columns=3):
    for i, method in enumerate(methods):
        xx = x + (i % columns) * 120
        yy = y + (i // columns) * 14
        fig.line(xx, yy, xx + 18, yy, color=COLORS[method], width=1.4, dash=LINE_DASH.get(method, []))
        fig.marker(xx + 9, yy, method, r=2.6)
        fig.text(xx + 24, yy + 2.5, SHORT[method], size=8.2, bold=(method == "MA-ABE-FU"))


def fig1_protocol():
    fig = VFigure("Fig. 1", 4.05)
    fig.text(16, 21, "MA-ABE-FU protocol surface and UCAP evidence fields", size=12.0, bold=True)
    fig.text(16, 35, "Control plane authorization and learning-plane unlearning repair are separated, then transcript-bound for audit.", size=8.0, color=MUTED)

    boxes = [
        (18, 62, 86, 54, "Authorities", "Issue GID-bound keys; publish mpk_i.", BLUE),
        (116, 62, 86, 54, "Forget request", "CT_F hides tag; pi_auth proves P.", GREEN),
        (214, 62, 86, 54, "Padded channel", "Pad matches ordinary update length and timing.", ORANGE),
        (312, 62, 86, 54, "Unlearning repair", "Repair on D\\S_F outputs theta'_t and report R.", SKY),
        (410, 62, 86, 54, "Audit verify", "Check proofs, signature, chain, and RiskGap.", RED),
    ]
    for x, y, w, h, head, body, color in boxes:
        fig.rect(x, y, w, h, fill=LIGHT, stroke=color, width=1.3, radius=5)
        fig.text(x + 5, y + 13, head, size=8.0, bold=True, color=color)
        fig.wrapped(x + 5, y + 25, body, w - 10, size=8.0, color=INK, leading=9.4)
    for i in range(len(boxes) - 1):
        x_start = boxes[i][0] + boxes[i][2] + 3
        x_end = boxes[i + 1][0] - 3
        fig.arrow(x_start, 89, x_end, 89)

    fig.rect(32, 144, 452, 130, fill=(252, 253, 255), stroke=GRID, width=0.8, radius=6)
    fig.text(44, 160, "UCAP evidence object O_F", size=9.8, bold=True)
    fields = [
        ("c_P=H(P)", "policy commitment"),
        ("c_s=H(scope)", "scope commitment"),
        ("H(ch)", "channel hash"),
        ("H(theta_t)", "pre-repair model commitment"),
        ("H(theta'_t)", "post-repair model commitment"),
        ("H(R)", "risk-report commitment"),
        ("pi_auth", "authorization proof"),
        ("pi_rep", "repair proof"),
        ("sigma_AS", "AS signature"),
        ("h_prev", "UCAP chain pointer"),
    ]
    for i, (field, desc) in enumerate(fields):
        col = i % 2
        row = i // 2
        x = 48 + col * 218
        y = 181 + row * 16
        fig.rect(x, y - 9, 66, 13, fill=lighten(BLUE if col == 0 else GREEN, 0.72), stroke=GRID, width=0.3, radius=2)
        fig.text(x + 3, y + 1, field, size=8.0, bold=True, color=INK)
        fig.text(x + 75, y + 1, desc, size=8.0, color=MUTED)
    fig.text(44, 265, "The server sees commitments and proof handles; RiskGap reports model residue.", size=8.0, color=MUTED)
    fig.save()


def fig2_security_game():
    fig = VFigure("Fig. 2", 3.90)
    fig.text(16, 21, "Policy-authenticated update-hiding game and reduction purpose", size=12.0, bold=True)
    fig.text(16, 35, "Each hop bounds one observable advantage: commitments, policy capsule, channel shape, audit forgery, and false proofs.", size=8.0, color=MUTED)

    stages = [
        ("G0", "Real game", "A receives View_b for ordinary update or forget request.", BLUE),
        ("G1", "Commitments", "Lazy-sample H(.) values; reduce collision events.", GREEN),
        ("G2", "MA-ABE", "Swap CT_F tag under an unsatisfied policy.", ORANGE),
        ("G3", "Padding", "Replace visible metadata by Pad distribution.", SKY),
        ("G4", "UCAP chain", "Reject forged evidence unless signature or chain breaks.", RED),
        ("G5", "Proofs", "Reject false proofs; residual RiskGap remains.", PINK),
    ]
    x0, y0 = 12, 72
    w, h, gap = 75, 76, 6
    for i, (gid, head, body, color) in enumerate(stages):
        x = x0 + i * (w + gap)
        fig.rect(x, y0, w, h, fill=LIGHT, stroke=color, width=1.2, radius=5)
        fig.text(x + 5, y0 + 13, f"{gid}: {head}", size=8.2, bold=True, color=color)
        fig.wrapped(x + 5, y0 + 29, body, w - 10, size=8.0, color=INK, leading=9.5)
        if i < len(stages) - 1:
            fig.arrow(x + w + 2, y0 + h / 2, x + w + gap - 2, y0 + h / 2)
    fig.rect(35, 182, 446, 86, fill=(252, 253, 255), stroke=GRID, width=0.8, radius=6)
    fig.text(48, 199, "Reduction bound", size=9.8, bold=True)
    fig.text(48, 217, "Adv_auth(A) <= Adv_MA-ABE(B1) + Adv_RO(B2) + Adv_PAD(B3) + Adv_SIG(B4)", size=8.0, color=INK)
    fig.text(48, 230, "+ Adv_ZK(B5) + eps_R + negl(lambda)", size=8.0, color=INK)
    notes = [
        ("B1", "policy capsule indistinguishability"),
        ("B2", "commitment consistency"),
        ("B3", "request-type padding"),
        ("B4", "audit-chain unforgeability"),
        ("B5", "authorization/repair proof soundness"),
    ]
    for i, (name, desc) in enumerate(notes):
        x = 48 + (i % 3) * 142
        y = 249 + (i // 3) * 15
        fig.text(x, y, f"{name}: {desc}", size=8.0, color=MUTED)
    fig.save()


def fig3_results(raw):
    fig = VFigure("Fig. 3", 5.85)
    fig.text(16, 20, "Unlearning repair quality under non-IID federated partitions", size=12.0, bold=True)
    fig.text(16, 34, "Dirichlet alpha=0.35; forget ratios 0.25, 0.50, and 1.00; error bars show 95% confidence intervals over seeds.", size=8.0, color=MUTED)
    method_legend(fig, 76, 58, METHODS, columns=3)

    def dot_panel(box, dataset, metric, lo, hi, panel, title, fmt="{:.3f}"):
        x0, y0, x1, y1 = box
        panel_title(fig, x0, y0 - 18, panel, title, dataset)
        draw_axes(fig, (x0 + 66, y0, x1 - 28, y1), x_ticks=(lo, hi, np.linspace(lo, hi, 4)), x_fmt=fmt)
        sub = raw[raw["dataset"] == dataset]
        for i, method in enumerate(METHODS):
            vals = sub[sub["method"] == method][metric].to_numpy(float)
            m = float(np.nanmean(vals))
            e = ci(vals)
            y = y0 + 16 + i * ((y1 - y0 - 28) / (len(METHODS) - 1))
            x = data_map(m, lo, hi, x0 + 66, x1 - 28)
            xe = e * (x1 - x0 - 94) / (hi - lo)
            fig.line(x - xe, y, x + xe, y, color=COLORS[method], width=1.2)
            fig.marker(x, y, method, r=3.1)
            fig.text(x0, y + 2.4, SHORT[method], size=8.0, color=INK, bold=(method == "MA-ABE-FU"))
            fig.text(x1 - 1, y + 2.4, fmt.format(m), size=8.0, color=MUTED, align="right")

    dot_panel((24, 106, 250, 226), "German Credit", "retained_auc", 0.73, 0.78, "a", "Retained AUC")
    dot_panel((278, 106, 504, 226), "Bank Marketing", "retained_auc", 0.79, 0.825, "b", "Retained AUC")

    def line_panel(box, dataset, metric, lo, hi, panel, title, ylabel):
        x0, y0, x1, y1 = box
        panel_title(fig, x0, y0 - 28, panel, title, dataset)
        draw_axes(fig, (x0 + 40, y0, x1 - 10, y1), "forget ratio", "", (0.25, 1.0, [0.25, 0.5, 1.0]), (lo, hi, np.linspace(lo, hi, 4)))
        fig.text(x0 + 44, y0 + 10, ylabel, size=8.2, color=MUTED, bold=True)
        for method in METHODS:
            pts = []
            for ratio in [0.25, 0.5, 1.0]:
                vals = raw[(raw["dataset"] == dataset) & (raw["method"] == method) & (raw["forget_ratio"] == ratio)][metric].to_numpy(float)
                if len(vals) == 0:
                    continue
                m = float(np.nanmean(vals))
                e = ci(vals)
                x = data_map(ratio, 0.25, 1.0, x0 + 40, x1 - 10)
                y = data_map(m, lo, hi, y1, y0)
                ye = e * (y1 - y0) / (hi - lo)
                fig.line(x, y - ye, x, y + ye, color=COLORS[method], width=0.7)
                pts.append((x, y))
            if len(pts) > 1:
                for a, b in zip(pts[:-1], pts[1:]):
                    fig.line(a[0], a[1], b[0], b[1], color=COLORS[method], width=1.2, dash=LINE_DASH.get(method, []))
            for x, y in pts:
                fig.marker(x, y, method, r=2.6)

    line_panel((28, 312, 248, 384), "German Credit", "mia_gap", 0.0, 0.10, "c", "Membership residue", "MIA gap")
    line_panel((286, 312, 506, 384), "Bank Marketing", "l2_to_oracle", 0.0, 0.17, "d", "Distance to oracle", "L2")
    fig.save()


def fig4_crypto(crypto):
    fig = VFigure("Fig. 4", 4.85)
    fig.text(16, 20, "Measured cryptographic overhead of the control plane", size=12.0, bold=True)
    fig.text(16, 34, "Primitive proxy and BN254 pairing backend are measured on the same local runtime; timings are end-to-end per forget request.", size=8.0, color=MUTED)

    prim = crypto[crypto["backend"] == "primitive_modexp_proxy"].copy()
    bn = crypto[crypto["backend"] == "bn254_pairing_py_ecc"].copy()
    x0, y0, x1, y1 = 48, 86, 504, 184
    panel_title(fig, 22, 60, "a", "Total control-plane latency", "")
    x_ticks = [4, 8, 16, 24, 32, 48]
    y_ticks = [20, 50, 100, 300, 1000, 3000]
    draw_axes(fig, (x0, y0, x1, y1), "LSSS policy rows", "", (4, 48, x_ticks), None, "{:.0f}", "{:.1f}")
    fig.text(x0, y0 - 12, "latency (ms, log scale)", size=8.0, color=MUTED, bold=True)
    for val in y_ticks:
        y = data_map(math.log10(val), math.log10(20), math.log10(3200), y1, y0)
        fig.line(x0, y, x1, y, color=GRID, width=0.35)
        fig.text(x0 - 4, y + 2.4, str(val), size=8.0, color=MUTED, align="right")
    series = [("primitive proxy", prim, BLUE, [], "FedAvg-Full")]
    for auth, color, dash in [(2, GREEN, [5, 2]), (4, ORANGE, [2, 2]), (6, PINK, [7, 3])]:
        sub = bn[bn["authority_count"] == auth]
        if not sub.empty:
            series.append((f"BN254, {auth} authorities", sub, color, dash, "MA-ABE-FU"))
    for label, sub, color, dash, marker in series:
        pts = []
        for _, row in sub.sort_values("policy_rows").iterrows():
            x = data_map(row["policy_rows"], 4, 48, x0, x1)
            y = data_map(math.log10(row["total_control_plane_ms"]), math.log10(20), math.log10(3200), y1, y0)
            pts.append((x, y))
        for a, b in zip(pts[:-1], pts[1:]):
            fig.line(a[0], a[1], b[0], b[1], color=color, width=1.25, dash=dash)
        for x, y in pts:
            fig.marker(x, y, marker, r=2.7, fill=color)
    for i, (label, _, color, dash, marker) in enumerate(series):
        x = 60 + (i % 2) * 220
        y = 216 + (i // 2) * 14
        fig.line(x, y, x + 18, y, color=color, width=1.3, dash=dash)
        fig.marker(x + 9, y, marker, r=2.4, fill=color)
        fig.text(x + 24, y + 2.5, label, size=8.0)

    panel_title(fig, 22, 247, "b", "Audit-chain micro-costs", "primitive backend, linear milliseconds")
    x0b, y0b, x1b, y1b = 48, 268, 504, 316
    draw_axes(fig, (x0b, y0b, x1b, y1b), "", "", (4, 48, x_ticks), (0, 1.25, [0, 0.4, 0.8, 1.2]), "{:.0f}", "{:.1f}")
    comps = [
        ("padded_envelope_hmac_ms", "HMAC padded envelope", GREEN, []),
        ("ucap_rsa_pss_sign_ms", "RSA-PSS sign", RED, [5, 2]),
        ("ucap_rsa_pss_verify_ms", "RSA-PSS verify", ORANGE, [2, 2]),
        ("hash_chain_append_ms", "hash-chain append", SKY, [7, 3]),
    ]
    short_label = {
        "HMAC padded envelope": "HMAC envelope",
        "RSA-PSS sign": "RSA-PSS sign",
        "RSA-PSS verify": "RSA verify",
        "hash-chain append": "hash append",
    }
    label_y = {
        "RSA-PSS sign": 271,
        "hash-chain append": 289,
        "HMAC padded envelope": 305,
        "RSA-PSS verify": 322,
    }
    for col, label, color, dash in comps:
        pts = []
        for _, row in prim.sort_values("policy_rows").iterrows():
            x = data_map(row["policy_rows"], 4, 48, x0b, x1b)
            y = data_map(row[col], 0, 1.25, y1b, y0b)
            pts.append((x, y))
        for a, b in zip(pts[:-1], pts[1:]):
            fig.line(a[0], a[1], b[0], b[1], color=color, width=1.0, dash=dash)
        for x, y in pts:
            fig.marker(x, y, "FedAvg-Full", r=2.0, fill=color)
        if pts:
            tx, ty = pts[-1]
            fig.line(tx - 1, ty, x1b - 55, label_y[label], color=color, width=0.35, dash=[1, 1])
            fig.text(x1b - 4, label_y[label] + 2, short_label[label], size=8.0, color=color, align="right")
    fig.save()


def fig5_leakage(raw):
    fig = VFigure("Fig. 5", 4.65)
    fig.text(16, 20, "Malicious-server leakage: request type and hidden policy attributes", size=12.0, bold=True)
    fig.text(16, 34, "Non-IID alpha=0.35; forget ratios 0.25, 0.50, and 1.00; points and bars report mean AUC with 95% confidence intervals over all runs.", size=8.0, color=MUTED)

    stats = []
    for method in METHODS:
        sub = raw[raw["method"] == method]
        stats.append(
            {
                "method": method,
                "type": float(sub["type_leak_auc"].mean()),
                "type_ci": ci(sub["type_leak_auc"]),
                "attr": float(sub["attribute_leak_auc"].mean()),
                "attr_ci": ci(sub["attribute_leak_auc"]),
                "mia": float(sub["mia_gap"].mean()),
            }
        )
    stats = pd.DataFrame(stats)
    ma_attr = float(stats[stats["method"] == "MA-ABE-FU"]["attr"].iloc[0])
    ma_type = float(stats[stats["method"] == "MA-ABE-FU"]["type"].iloc[0])
    baseline_attr = float(stats[stats["method"].isin(["FedEraser-proxy", "FedRecovery-proxy", "Starfish-proxy"])]["attr"].mean())

    x0, y0, x1, y1 = 60, 82, 280, 255
    panel_title(fig, 24, 64, "a", "Observable metadata leakage", "random guessing is 0.5")
    draw_axes(fig, (x0, y0, x1, y1), "request-type leakage AUC", "", (0.5, 1.0, [0.5, 0.7, 0.9, 1.0]), (0.5, 1.0, [0.5, 0.7, 0.9, 1.0]), "{:.1f}", "{:.1f}")
    fig.text(x0 + 4, y0 + 11, "attribute leakage AUC", size=8.0, color=MUTED, bold=True)
    fig.line(x0, data_map(0.5, 0.5, 1.0, y1, y0), x1, data_map(0.5, 0.5, 1.0, y1, y0), color=MUTED, width=0.7, dash=[3, 2])
    fig.line(data_map(0.5, 0.5, 1.0, x0, x1), y0, data_map(0.5, 0.5, 1.0, x0, x1), y1, color=MUTED, width=0.7, dash=[3, 2])
    fig.rect(x0 + 5, y1 - 65, 86, 28, fill=(238, 247, 244), stroke=lighten(GREEN, 0.35), width=0.5, radius=3)
    fig.text(x0 + 9, y1 - 50, "privacy-favorable", size=8.0, bold=True, color=GREEN)
    fig.text(x0 + 9, y1 - 39, "near-random in both tests", size=8.0, color=MUTED)
    for _, row in stats.iterrows():
        method = row["method"]
        x = data_map(row["type"], 0.5, 1.0, x0, x1)
        y = data_map(row["attr"], 0.5, 1.0, y1, y0)
        xe = row["type_ci"] * (x1 - x0) / 0.5
        ye = row["attr_ci"] * (y1 - y0) / 0.5
        fig.line(x - xe, y, x + xe, y, color=COLORS[method], width=0.9)
        fig.line(x, y - ye, x, y + ye, color=COLORS[method], width=0.9)
        fig.marker(x, y, method, r=3.2)
        if method == "MA-ABE-FU":
            fig.text(x + 15, y - 2, SHORT[method], size=8.0, bold=True, color=COLORS[method])

    x0b, y0b, x1b, y1b = 344, 82, 502, 255
    panel_title(fig, 300, 64, "b", "Attribute-leakage reduction", "lower is better")
    fig.line(x0b, y1b, x1b, y1b, width=0.8)
    fig.line(x0b, y0b, x0b, y1b, width=0.8)
    for tick in [0.5, 0.7, 0.9, 1.0]:
        x = data_map(tick, 0.5, 1.0, x0b, x1b)
        fig.line(x, y0b, x, y1b, color=GRID, width=0.35)
        fig.text(x, y1b + 12, f"{tick:.1f}", size=8.0, color=MUTED, align="center")
    for i, row in stats.iterrows():
        method = row["method"]
        y = y0b + 14 + i * 29
        x = data_map(row["attr"], 0.5, 1.0, x0b, x1b)
        fig.line(x0b, y, x, y, color=COLORS[method], width=4.8)
        fig.marker(x, y, method, r=3.0)
        fig.text(x0b - 7, y + 2.3, SHORT[method], size=8.0, bold=(method == "MA-ABE-FU"), align="right")
        value_x = max(x + 4, x0b + 14)
        fig.text(value_x, y + 2.3, f"{row['attr']:.3f}", size=8.0, bold=True)
    fig.text(x0b + 4, y1b + 27, "attribute leakage AUC", size=8.0, color=MUTED, bold=True)

    fig.rect(52, 286, 412, 34, fill=(252, 253, 255), stroke=GRID, width=0.6, radius=4)
    fig.text(62, 302, f"MA-ABE-FU lowers attribute leakage to {ma_attr:.3f}; FU repair proxies average {baseline_attr:.3f}.", size=8.0, bold=True)
    fig.text(62, 314, f"Remaining request-type signal is {ma_type:.3f}; padding reduces but does not eliminate timing/queue observability.", size=8.0, color=MUTED)
    fig.save()


def write_manifest():
    captions = [
        ("Fig. 1", "MA-ABE-FU control plane and UCAP evidence fields; every evidence-field abbreviation is decoded in the figure."),
        ("Fig. 2", "Policy-authenticated update-hiding game; G0-G5 show the purpose of each reduction hop."),
        ("Fig. 3", "Unlearning repair quality under Dirichlet non-IID alpha=0.35, forget ratios 0.25/0.50/1.00, and 95% confidence intervals over seeds."),
        ("Fig. 4", "Measured control-plane cryptographic overhead for primitive proxy and BN254 pairing backend; log-scale total plus audit-chain zoom."),
        ("Fig. 5", "Malicious-server request-type and attribute leakage under the same non-IID partitions, forget ratios, and 95% confidence interval convention."),
    ]
    with open(REPRO / "figure_manifest_v6.csv", "w", encoding="utf-8") as f:
        f.write("figure,vector_pdf,tiff_600dpi,caption_check\n")
        for fig, caption in captions:
            f.write(f"{fig},figure/{fig}.pdf,figure/{fig}.tif,{caption}\n")


def main():
    clear_generated_figures()
    raw = pd.read_csv(REPRO / "federated_raw_v6.csv")
    crypto = pd.read_csv(REPRO / "crypto_overhead_v6.csv")
    fig1_protocol()
    fig2_security_game()
    fig3_results(raw)
    fig4_crypto(crypto)
    fig5_leakage(raw)
    write_manifest()


if __name__ == "__main__":
    main()
