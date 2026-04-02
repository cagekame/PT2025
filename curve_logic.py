"""
curve_logic.py
Logica della scheda Performance Curve: lettura TDMS, matplotlib, callbacks.
Istanzia CurveUI e popola i frame esposti.
Le funzioni build_*_figure rimangono qui e sono riusate da pdf_report.
"""
import math

# matplotlib
try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.lines import Line2D
    from matplotlib.path import Path
    MPL_OK = True
except Exception:
    MPL_OK = False

from tdms_reader import read_performance_tables_dynamic, read_contract_and_loop_data
from ui_format import fmt_if_number as _fmt_if_number, fmt_num as _fmt_num


# ── MARKER CUSTOM ─────────────────────────────────────────────────────────────
def _marker_triangle_right_angle_top_right():
    verts = [(-0.5, 0.5), (0.5, 0.5), (0.5, -0.5), (-0.5, 0.5)]
    codes = [Path.MOVETO, Path.LINETO, Path.LINETO, Path.CLOSEPOLY]
    return Path(verts, codes)

RIGHT_ANGLE_TR_MARKER = _marker_triangle_right_angle_top_right()

# ── COLONNE CONVERTED ─────────────────────────────────────────────────────────
FLOW_NAME  = "FLOW"
TDH_NAME   = "TDH"
EFF_NAME   = "EFF"
POWER_NAME = "POWER"


# ── HELPERS NUMERICI ──────────────────────────────────────────────────────────

def _to_float(x, default=None):
    try:
        if isinstance(x, str):
            x = x.replace(",", ".").strip()
        f = float(x)
        if math.isfinite(f):
            return f
    except Exception:
        pass
    return default


def _dedupe_and_sort_xy(xs, ys):
    pairs = {}
    for x, y in zip(xs, ys):
        try:
            xf = float(x); yf = float(y)
        except Exception:
            continue
        if not (math.isfinite(xf) and math.isfinite(yf)):
            continue
        pairs.setdefault(xf, []).append(yf)
    if not pairs:
        return [], []
    xs_s = sorted(pairs.keys())
    return xs_s, [sum(pairs[x]) / len(pairs[x]) for x in xs_s]


def _solve_linear_system_4x4(A, b):
    M = [list(A[i]) + [b[i]] for i in range(4)]
    for col in range(4):
        pivot_row = max(range(col, 4), key=lambda r: abs(M[r][col]))
        if abs(M[pivot_row][col]) < 1e-12:
            return None
        if pivot_row != col:
            M[col], M[pivot_row] = M[pivot_row], M[col]
        pivot = M[col][col]
        for j in range(col, 5):
            M[col][j] /= pivot
        for r in range(col + 1, 4):
            factor = M[r][col]
            if factor == 0:
                continue
            for j in range(col, 5):
                M[r][j] -= factor * M[col][j]
    x = [0.0] * 4
    for i in range(3, -1, -1):
        s = M[i][4] - sum(M[i][j] * x[j] for j in range(i + 1, 4))
        x[i] = s
    return x


def _poly3_trendline(xs, ys):
    n = len(xs)
    if n < 4:
        return (None, None, None, None, None)
    S = [sum(x**k for x in xs) for k in range(7)]
    T = [sum((x**k) * y for x, y in zip(xs, ys)) for k in range(4)]
    A = [[S[6-r-c] for c in range(4)] for r in range(4)]
    b = [T[3-i] for i in range(4)]
    coeffs = _solve_linear_system_4x4(A, b)
    if coeffs is None:
        return (None, None, None, None, None)
    a, b2, c, d = coeffs
    y_mean = sum(ys) / n
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (a*x**3 + b2*x**2 + c*x + d))**2 for x, y in zip(xs, ys))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
    return (a, b2, c, d, r2)


def _idx_exact_or_dup(columns, base_name):
    if not columns:
        return None
    for i, c in enumerate(columns):
        if c == base_name:
            return i
    prefix = f"{base_name}__"
    for i, c in enumerate(columns):
        if isinstance(c, str) and c.startswith(prefix):
            return i
    return None


def _get_converted(tdms_path: str, test_index: int = 0):
    perf = read_performance_tables_dynamic(tdms_path, test_index=test_index) or {}
    conv = perf.get("Converted") or {}
    return conv.get("columns") or [], conv.get("rows") or []


def _extract_series(cols, rows, x_name, y_name):
    if not cols or not rows:
        return [], []
    ix_x = _idx_exact_or_dup(cols, x_name)
    ix_y = _idx_exact_or_dup(cols, y_name)
    if ix_x is None or ix_y is None:
        return [], []
    xs, ys = [], []
    for r in rows:
        xv = _to_float(r[ix_x], None)
        yv = _to_float(r[ix_y], None)
        if xv is not None and yv is not None:
            if math.isfinite(xv) and math.isfinite(yv):
                xs.append(xv); ys.append(yv)
    return xs, ys


def _read_contractual_meta(tdms_path: str) -> dict:
    raw = read_contract_and_loop_data(tdms_path) or {}
    return {
        "capacity":  raw.get("Capacity [m3/h]", "") or "—",
        "tdh":       raw.get("TDH [m]", "") or "—",
        "eff":       raw.get("Efficiency [%]", "") or "—",
        "abs_pow":   raw.get("ABS_Power [kW]", "") or "—",
        "speed":     raw.get("Speed [rpm]", "") or "—",
        "sg":        raw.get("SG Contract", "") or "—",
        "temp":      (raw.get("Temperature [°C]") or raw.get("Temperature [C]", "")) or "—",
        "visc":      raw.get("Viscosity [cP]", "") or "—",
        "npsh":      raw.get("NPSH [m]", "") or "—",
        "liquid":    raw.get("Liquid", "") or "—",
        "fsg_order": raw.get("FSG ORDER", "") or "—",
        "customer":  raw.get("Customer", "") or "—",
        "po":        raw.get("Purchaser Order", "") or "—",
        "end_user":  raw.get("End User", "") or "—",
        "item":      raw.get("Item", "") or "—",
        "pump":      raw.get("Pump", "") or "—",
        "sn":        raw.get("Serial Number_Elenco", "") or "—",
        "imp_draw":  raw.get("Impeller Drawing", "") or "—",
        "imp_mat":   raw.get("Impeller Material", "") or "—",
        "imp_dia":   raw.get("Diam Nominal", "") or "—",
        "specs":     raw.get("Applic. Specs.", "") or "—",
    }


# ── BUILD FIGURES (riusate anche da pdf_report) ───────────────────────────────

def _contract_get(raw: dict, base_name: str) -> str:
    """Cerca un valore nel contract per nome base, ignorando le unita'."""
    import re as _re
    for k, v in raw.items():
        k_base = _re.sub(r"\s*\[[^\]]*\]\s*$", "", k).strip()
        if k_base.lower() == base_name.lower() and v is not None and v != "":
            return str(v)
    return ""

def build_tdh_eff_figure(tdms_path: str, show_points: bool = True,
                         eff_min: float = 0.0, eff_max: float = 100.0,
                         unit_system: str = "Metric", cache: dict = None,
                         hidden_rows: set = None):
    if not MPL_OK:
        return None
    try:
        import unit_converter as uc
    except Exception:
        uc = None; unit_system = "Metric"

    # Usa cache se disponibile, altrimenti leggi dal TDMS
    if cache:
        raw = cache.get("contract", {})
        meta = {
            "capacity":  _contract_get(raw, "Capacity"),
            "tdh":       _contract_get(raw, "TDH"),
            "eff":       _contract_get(raw, "Efficiency"),
            "speed":     _contract_get(raw, "Speed"),
            "sg":        _contract_get(raw, "SG Contract"),
            "fsg_order": raw.get("FSG ORDER", ""),
        }
        conv = cache.get("perf", {}).get("Converted", {})
        conv_cols = conv.get("columns", [])
        conv_rows = conv.get("rows", [])
    else:
        meta = _read_contractual_meta(tdms_path)
        conv_cols, conv_rows = _get_converted(tdms_path)

    fig = Figure(figsize=(11, 7), dpi=100)
    ax  = fig.add_subplot(111)
    # Filtra righe nascoste
    if hidden_rows and conv_rows:
        hidden_idx = {int(iid.lstrip("p")) - 1 for iid in hidden_rows
                      if iid.lstrip("p").isdigit()}
        conv_rows = [r for i, r in enumerate(conv_rows) if i not in hidden_idx]

    xs_raw, ys_raw = _extract_series(conv_cols, conv_rows, FLOW_NAME, TDH_NAME)
    xs_eff, ys_eff = _extract_series(conv_cols, conv_rows, FLOW_NAME, EFF_NAME)

    from_cache = bool(cache and cache.get("from_cache"))
    if not from_cache and uc and unit_system != "Metric":
        xs_raw = [uc.convert_value(x, "flow", "Metric", unit_system) for x in xs_raw]
        ys_raw = [uc.convert_value(y, "head", "Metric", unit_system) for y in ys_raw]
        xs_eff = [uc.convert_value(x, "flow", "Metric", unit_system) for x in xs_eff]

    rated_q   = _to_float(meta.get("capacity", ""), None)
    rated_tdh = _to_float(meta.get("tdh", ""),      None)
    rated_eta = _to_float(meta.get("eff", ""),      None)
    if not from_cache and uc and unit_system != "Metric":
        if rated_q:   rated_q   = uc.convert_value(rated_q,   "flow", "Metric", unit_system)
        if rated_tdh: rated_tdh = uc.convert_value(rated_tdh, "head", "Metric", unit_system)

    has_rated = has_bep = has_rated_eff = False
    flow_unit = uc.get_unit_label("flow", unit_system) if uc else "m³/h"
    head_unit = uc.get_unit_label("head", unit_system) if uc else "m"

    tdhs_trend = None
    x_curve = []
    if xs_raw and ys_raw:
        sc = ax.scatter(xs_raw, ys_raw, s=30, label="_nolegend_")
        sc.set_visible(show_points)
        xs, ys = _dedupe_and_sort_xy(xs_raw, ys_raw)
        if xs:
            a, b, c, d, _ = _poly3_trendline(xs, ys)
            if a is not None and len(xs) >= 4:
                xmin, xmax = min(xs), max(xs)
                num = max(50, min(400, 10 * len(xs)))
                x_curve = [xmin + (xmax - xmin) * i / (num - 1) for i in range(num)]
                y_curve = [a*x**3 + b*x**2 + c*x + d for x in x_curve]
                tdhs_trend = ax.plot(x_curve, y_curve, linewidth=1.8, label="TDH")[0]
            else:
                tdhs_trend = ax.plot(xs, ys, linewidth=1.8, label="TDH")[0]

    if rated_q is not None and rated_tdh is not None:
        ax.scatter([rated_q], [rated_tdh], marker=RIGHT_ANGLE_TR_MARKER, s=140,
                   facecolors="none", edgecolors="tab:blue",
                   linewidths=1.6, zorder=10)
        has_rated = True

    ax.set_ylabel(f"TDH [{head_unit}]")
    ax.set_ylim(bottom=0); ax.set_xlim(left=0)
    ax.set_xlabel(f"Capacity [{flow_unit}]")
    ax.grid(True, linestyle=":", linewidth=0.8)

    eta_line = None; ax2 = None
    if xs_eff and ys_eff:
        ax2 = ax.twinx()
        ax.set_zorder(2); ax2.set_zorder(1); ax.patch.set_visible(False)
        ax2.set_ylabel("Efficiency [%]")
        eff_sc = ax2.scatter(xs_eff, ys_eff, s=25, marker="o")
        eff_sc.set_visible(show_points)
        if rated_q is not None and rated_eta is not None:
            ax2.scatter([rated_q], [rated_eta], marker=RIGHT_ANGLE_TR_MARKER, s=140,
                        facecolors="none", edgecolors="tab:orange",
                        linewidths=1.6, zorder=10)
            has_rated_eff = True
        xe, ye = _dedupe_and_sort_xy(xs_eff, ys_eff)
        if xe:
            ea, eb, ec, ed, _ = _poly3_trendline(xe, ye)
            e_x = x_curve or [min(xe) + (max(xe)-min(xe))*i/(max(50,min(400,10*len(xe)))-1)
                               for i in range(max(50, min(400, 10*len(xe))))]
            if ea is not None and len(xe) >= 4:
                e_y = [ea*x**3 + eb*x**2 + ec*x + ed for x in e_x]
                eta_line = ax2.plot(e_x, e_y, linewidth=1.8, color="orange", label="Efficiency")[0]
                try:
                    mi = max(range(len(e_x)), key=lambda k: e_y[k])
                    ax2.scatter([e_x[mi]], [e_y[mi]], s=80, marker="D",
                                color="red", edgecolors="red", zorder=10)
                    has_bep = True
                except Exception:
                    pass
            else:
                eta_line = ax2.plot(xe, ye, linewidth=1.8, color="orange", label="Efficiency")[0]
        ax2.set_ylim(eff_min, eff_max)

    ax.relim(); ax.autoscale(axis="y")
    _, ymax = ax.get_ylim(); ax.set_ylim(bottom=0, top=ymax * 1.10)

    handles, labels = [], []
    if tdhs_trend: handles.append(tdhs_trend); labels.append("TDH")
    if eta_line:   handles.append(eta_line);   labels.append("Efficiency")
    if has_rated:
        handles.append(Line2D([0],[0], marker=RIGHT_ANGLE_TR_MARKER, linestyle="None",
                               markersize=10, markerfacecolor="none",
                               markeredgecolor="tab:blue", markeredgewidth=1.6))
        labels.append("Rated TDH")
    if has_rated_eff:
        handles.append(Line2D([0],[0], marker=RIGHT_ANGLE_TR_MARKER, linestyle="None",
                               markersize=10, markerfacecolor="none",
                               markeredgecolor="tab:orange", markeredgewidth=1.6))
        labels.append("Rated Efficiency")
    if has_bep:
        handles.append(Line2D([0],[0], marker="D", linestyle="None", markersize=7,
                               markerfacecolor="red", markeredgecolor="red"))
        labels.append("BEP point")
    if handles:
        ax.legend(handles, labels, loc="lower right")
    fig.tight_layout()
    return fig


def build_power_figure(tdms_path: str, show_points: bool = True,
                       unit_system: str = "Metric", cache: dict = None,
                       hidden_rows: set = None):
    if not MPL_OK:
        return None
    try:
        import unit_converter as uc
    except Exception:
        uc = None; unit_system = "Metric"

    fig = Figure(figsize=(11, 7), dpi=100)
    ax  = fig.add_subplot(111)

    if cache:
        conv = cache.get("perf", {}).get("Converted", {})
        conv_cols = conv.get("columns", [])
        conv_rows = conv.get("rows", [])
    else:
        conv_cols, conv_rows = _get_converted(tdms_path)
    # Filtra righe nascoste
    if hidden_rows and conv_rows:
        hidden_idx = {int(iid.lstrip("p")) - 1 for iid in hidden_rows
                      if iid.lstrip("p").isdigit()}
        conv_rows = [r for i, r in enumerate(conv_rows) if i not in hidden_idx]
    pxs, pys = _extract_series(conv_cols, conv_rows, FLOW_NAME, POWER_NAME)

    from_cache = bool(cache and cache.get("from_cache"))
    if not from_cache and uc and unit_system != "Metric":
        pxs = [uc.convert_value(x, "flow",  "Metric", unit_system) for x in pxs]
        pys = [uc.convert_value(y, "power", "Metric", unit_system) for y in pys]

    flow_unit  = uc.get_unit_label("flow",  unit_system) if uc else "m³/h"
    power_unit = uc.get_unit_label("power", unit_system) if uc else "kW"

    p_line = None
    if pxs and pys:
        ax.scatter(pxs, pys, s=28).set_visible(show_points)
        xs2, ys2 = _dedupe_and_sort_xy(pxs, pys)
        if xs2:
            pa, pb, pc, pd, _ = _poly3_trendline(xs2, ys2)
            if pa is not None and len(xs2) >= 4:
                pxmin, pxmax = min(xs2), max(xs2)
                pnum = max(50, min(400, 10 * len(xs2)))
                px_c = [pxmin + (pxmax-pxmin)*i/(pnum-1) for i in range(pnum)]
                py_c = [pa*x**3 + pb*x**2 + pc*x + pd for x in px_c]
                p_line = ax.plot(px_c, py_c, linewidth=1.8, color="black", label="Absorbed Power")[0]
            else:
                p_line = ax.plot(xs2, ys2, linewidth=1.8, color="black", label="Absorbed Power")[0]

    ax.set_xlabel(f"Capacity [{flow_unit}]")
    ax.set_ylabel(f"Abs Power [{power_unit}]")
    ax.set_ylim(bottom=0)
    ax.grid(True, linestyle=":", linewidth=0.8)
    ax.relim(); ax.autoscale(axis="y")
    _, pymax = ax.get_ylim(); ax.set_ylim(bottom=0, top=pymax * 1.10)
    if p_line:
        ax.legend([p_line], ["Absorbed Power"], loc="lower right")
    fig.tight_layout()
    return fig


def build_curve_figure(tdms_path: str, show_points: bool = True,
                       eff_min: float = 0.0, eff_max: float = 100.0,
                       unit_system: str = "Metric",
                       return_artists: bool = False,
                       cache: dict = None,
                       hidden_rows: set = None):
    if not MPL_OK:
        return (None, {}, None) if return_artists else None
    try:
        import unit_converter as uc
    except Exception:
        uc = None; unit_system = "Metric"

    from_cache = bool(cache and cache.get("from_cache"))

    if cache:
        raw = cache.get("contract", {})
        meta = {
            "capacity":  _contract_get(raw, "Capacity"),
            "tdh":       _contract_get(raw, "TDH"),
            "eff":       _contract_get(raw, "Efficiency"),
            "speed":     _contract_get(raw, "Speed"),
            "sg":        _contract_get(raw, "SG Contract"),
            "fsg_order": raw.get("FSG ORDER", ""),
        }
        conv = cache.get("perf", {}).get("Converted", {})
        conv_cols = conv.get("columns", [])
        conv_rows = conv.get("rows", [])
    else:
        meta = _read_contractual_meta(tdms_path)
        conv_cols, conv_rows = _get_converted(tdms_path)

    # Filtra le righe nascoste (iid p001, p002 -> indici 0, 1, ...)
    if hidden_rows and conv_rows:
        hidden_idx = set()
        for iid in hidden_rows:
            try:
                hidden_idx.add(int(iid.lstrip("p")) - 1)
            except Exception:
                pass
        conv_rows = [r for i, r in enumerate(conv_rows) if i not in hidden_idx]

    fig  = Figure(figsize=(9, 11), dpi=100)
    gs   = fig.add_gridspec(2, 1, height_ratios=[3, 2], hspace=0.20)
    ax   = fig.add_subplot(gs[0])
    axp  = fig.add_subplot(gs[1], sharex=ax)

    xs_raw, ys_raw = _extract_series(conv_cols, conv_rows, FLOW_NAME, TDH_NAME)
    xs_eff, ys_eff = _extract_series(conv_cols, conv_rows, FLOW_NAME, EFF_NAME)

    if not from_cache and uc and unit_system != "Metric":
        xs_raw = [uc.convert_value(x, "flow", "Metric", unit_system) for x in xs_raw]
        ys_raw = [uc.convert_value(y, "head", "Metric", unit_system) for y in ys_raw]
        xs_eff = [uc.convert_value(x, "flow", "Metric", unit_system) for x in xs_eff]

    rated_q   = _to_float(meta.get("capacity", ""), None)
    rated_tdh = _to_float(meta.get("tdh", ""),      None)
    rated_eta = _to_float(meta.get("eff", ""),      None)
    if not from_cache and uc and unit_system != "Metric":
        if rated_q:   rated_q   = uc.convert_value(rated_q,   "flow", "Metric", unit_system)
        if rated_tdh: rated_tdh = uc.convert_value(rated_tdh, "head", "Metric", unit_system)

    has_rated = has_bep = has_rated_eff = False
    artists = {}
    flow_unit  = uc.get_unit_label("flow",  unit_system) if uc else "m³/h"
    head_unit  = uc.get_unit_label("head",  unit_system) if uc else "m"
    power_unit = uc.get_unit_label("power", unit_system) if uc else "kW"

    # TDH
    tdhs_trend = None; x_curve = []
    if xs_raw and ys_raw:
        sc = ax.scatter(xs_raw, ys_raw, s=30, label="_nolegend_")
        sc.set_visible(show_points)
        if return_artists: artists["tdh"] = sc
        xs, ys = _dedupe_and_sort_xy(xs_raw, ys_raw)
        if xs:
            a, b, c, d, _ = _poly3_trendline(xs, ys)
            if a is not None and len(xs) >= 4:
                xmin, xmax = min(xs), max(xs)
                num = max(50, min(400, 10 * len(xs)))
                x_curve = [xmin + (xmax-xmin)*i/(num-1) for i in range(num)]
                y_curve  = [a*x**3 + b*x**2 + c*x + d for x in x_curve]
                tdhs_trend = ax.plot(x_curve, y_curve, linewidth=1.8, label="TDH")[0]
            else:
                tdhs_trend = ax.plot(xs, ys, linewidth=1.8, label="TDH")[0]

    if rated_q is not None and rated_tdh is not None:
        ax.scatter([rated_q], [rated_tdh], marker=RIGHT_ANGLE_TR_MARKER, s=140,
                   facecolors="none", edgecolors="tab:blue", linewidths=1.6, zorder=10)
        has_rated = True

    ax.set_ylabel(f"TDH [{head_unit}]")
    ax.set_ylim(bottom=0); ax.set_xlim(left=0)
    ax.grid(True, linestyle=":", linewidth=0.8)

    # Efficiency
    eta_line = None; ax2 = None
    if xs_eff and ys_eff:
        ax2 = ax.twinx()
        ax.set_zorder(2); ax2.set_zorder(1); ax.patch.set_visible(False)
        ax2.set_ylabel("Efficiency [%]")
        eff_sc = ax2.scatter(xs_eff, ys_eff, s=25, marker="o", label="_nolegend_")
        eff_sc.set_visible(show_points)
        if return_artists: artists["eff"] = eff_sc
        if rated_q is not None and rated_eta is not None:
            ax2.scatter([rated_q], [rated_eta], marker=RIGHT_ANGLE_TR_MARKER, s=140,
                        facecolors="none", edgecolors="tab:orange", linewidths=1.6, zorder=10)
            has_rated_eff = True
        xe, ye = _dedupe_and_sort_xy(xs_eff, ys_eff)
        if xe:
            ea, eb, ec, ed, _ = _poly3_trendline(xe, ye)
            e_x = x_curve or [min(xe)+(max(xe)-min(xe))*i/(max(50,min(400,10*len(xe)))-1)
                               for i in range(max(50, min(400, 10*len(xe))))]
            if ea is not None and len(xe) >= 4:
                e_y = [ea*x**3 + eb*x**2 + ec*x + ed for x in e_x]
                eta_line = ax2.plot(e_x, e_y, linewidth=1.8, color="orange", label="Efficiency")[0]
                try:
                    mi = max(range(len(e_x)), key=lambda k: e_y[k])
                    ax2.scatter([e_x[mi]], [e_y[mi]], s=80, marker="D",
                                color="red", edgecolors="red", zorder=10)
                    has_bep = True
                except Exception:
                    pass
            else:
                eta_line = ax2.plot(xe, ye, linewidth=1.8, color="orange", label="Efficiency")[0]
        ax2.set_ylim(eff_min, eff_max)

    ax.relim(); ax.autoscale(axis="y")
    _, ymax = ax.get_ylim(); ax.set_ylim(bottom=0, top=ymax * 1.10)

    handles, labels = [], []
    if tdhs_trend: handles.append(tdhs_trend); labels.append("TDH")
    if eta_line:   handles.append(eta_line);   labels.append("Efficiency")
    if has_rated:
        handles.append(Line2D([0],[0], marker=RIGHT_ANGLE_TR_MARKER, linestyle="None",
                               markersize=10, markerfacecolor="none",
                               markeredgecolor="tab:blue", markeredgewidth=1.6))
        labels.append("Rated TDH")
    if has_rated_eff:
        handles.append(Line2D([0],[0], marker=RIGHT_ANGLE_TR_MARKER, linestyle="None",
                               markersize=10, markerfacecolor="none",
                               markeredgecolor="tab:orange", markeredgewidth=1.6))
        labels.append("Rated Efficiency")
    if has_bep:
        handles.append(Line2D([0],[0], marker="D", linestyle="None", markersize=7,
                               markerfacecolor="red", markeredgecolor="red"))
        labels.append("BEP point")
    if handles:
        ax.legend(handles, labels, loc="lower right")

    # Power
    pxs, pys = _extract_series(conv_cols, conv_rows, FLOW_NAME, POWER_NAME)
    if uc and unit_system != "Metric":
        pxs = [uc.convert_value(x, "flow",  "Metric", unit_system) for x in pxs]
        pys = [uc.convert_value(y, "power", "Metric", unit_system) for y in pys]

    p_line = None
    if pxs and pys:
        pwr_sc = axp.scatter(pxs, pys, s=28, label="_nolegend_")
        pwr_sc.set_visible(show_points)
        if return_artists: artists["pwr"] = pwr_sc
        xs2, ys2 = _dedupe_and_sort_xy(pxs, pys)
        if xs2:
            pa, pb, pc, pd, _ = _poly3_trendline(xs2, ys2)
            if pa is not None and len(xs2) >= 4:
                pxmin, pxmax = min(xs2), max(xs2)
                pnum = max(50, min(400, 10 * len(xs2)))
                px_c = [pxmin+(pxmax-pxmin)*i/(pnum-1) for i in range(pnum)]
                py_c = [pa*x**3 + pb*x**2 + pc*x + pd for x in px_c]
                p_line = axp.plot(px_c, py_c, linewidth=1.8, color="black", label="Absorbed Power")[0]
            else:
                p_line = axp.plot(xs2, ys2, linewidth=1.8, color="black", label="Absorbed Power")[0]

    axp.set_xlabel(f"Capacity [{flow_unit}]")
    axp.set_ylabel(f"Abs Power [{power_unit}]")
    axp.set_ylim(bottom=0)
    axp.grid(True, linestyle=":", linewidth=0.8)
    axp.relim(); axp.autoscale(axis="y")
    _, pymax = axp.get_ylim(); axp.set_ylim(bottom=0, top=pymax * 1.10)
    if p_line:
        axp.legend([p_line], ["Absorbed Power"], loc="lower right")

    fig.subplots_adjust(top=0.98)
    return (fig, artists, ax2) if return_artists else fig


# ── RENDER PUBBLICO ───────────────────────────────────────────────────────────

def render_curve_tab(parent, tdms_path: str, acquisizione_id: int = None,
                     cache: dict = None):
    """
    Popola il frame `parent` (tab_curva di CertificateUI) con la scheda curva.
    """
    from curve_ui import CurveUI
    # Leggi unit_system dal DB
    try:
        from db import get_unit_system, curve_settings_get, curve_settings_set as _css
        unit_system = get_unit_system(acquisizione_id) if acquisizione_id else "Metric"
    except Exception:
        unit_system = "Metric"
        _css = None

    try:
        import unit_converter as uc
        raw_contract = (cache.get("contract") if cache else None) or                        read_contract_and_loop_data(tdms_path) or {}
        if cache and cache.get("from_cache"):
            data = raw_contract
        else:
            data = uc.convert_contractual_data(raw_contract, "Metric", unit_system)
        fl = uc.get_unit_label("flow",  unit_system)
        hl = uc.get_unit_label("head",  unit_system)
        pl = uc.get_unit_label("power", unit_system)
        tl = uc.get_unit_label("temp",  unit_system)
        nl = uc.get_unit_label("npsh",  unit_system)
    except Exception:
        uc = None
        data = read_contract_and_loop_data(tdms_path) or {}
        fl, hl, pl, tl, nl = "m³/h", "m", "kW", "°C", "m"

    def _g(k, fb="—"):
        return data.get(k, "") or fb

    # ── Istanzia UI ──────────────────────────────────────────────────────────
    ui = CurveUI(parent)

    # ── Blocchi KV ───────────────────────────────────────────────────────────
    contractual_rows = [
        ("FSG ORDER",    _g("FSG ORDER")),
        ("CUSTOMER",     _g("Customer")),
        ("P.O.",         _g("Purchaser Order")),
        ("End User",     _g("End User")),
        ("Item",         _g("Item")),
        ("Pump",         _g("Pump")),
        ("S. N.",        _g("Serial Number_Elenco")),
        ("Imp. Draw.",   _g("Impeller Drawing")),
        ("Imp. Mat.",    _g("Impeller Material")),
        ("Imp Dia [mm]", _g("Diam Nominal")),
        ("Specs",        _g("Applic. Specs.")),
    ]
    rated_rows = [
        (f"Capacity [{fl}]",  _fmt_if_number(_g(f"Capacity [{fl}]", _g("Capacity [m3/h]")))),
        (f"TDH [{hl}]",       _fmt_if_number(_g(f"TDH [{hl}]",      _g("TDH [m]")))),
        ("Efficiency [%]",    _fmt_if_number(_g("Efficiency [%]"))),
        (f"ABS_Power [{pl}]", _fmt_if_number(_g(f"ABS_Power [{pl}]", _g("ABS_Power [kW]")))),
        ("Speed [rpm]",       _fmt_if_number(_g("Speed [rpm]"))),
        ("SG",                _fmt_if_number(_g("SG Contract"))),
        (f"Temperature [{tl}]", _fmt_if_number(_g(f"Temperature [{tl}]", _g("Temperature [°C]")))),
        ("Viscosity [cP]",    _fmt_if_number(_g("Viscosity [cP]"))),
        (f"NPSH [{nl}]",      _fmt_if_number(_g(f"NPSH [{nl}]", _g("NPSH [m]")))),
        ("Liquid",            _g("Liquid")),
    ]
    ui.populate_kv_blocks(contractual_rows, rated_rows)

    # ── Impostazioni salvate ──────────────────────────────────────────────────
    try:
        saved = curve_settings_get(acquisizione_id) if acquisizione_id else None
    except Exception:
        saved = None
    if saved is None:
        saved = {"show_points": True, "eff_min": 0.0, "eff_max": 100.0}

    # Carica righe nascoste dal DB
    hidden_rows = set()
    try:
        from db import hidden_rows_get as _hrg
        hidden_rows = _hrg(acquisizione_id, "PERFORMANCE") if acquisizione_id else set()
    except Exception:
        pass

    ui.entry_eff_min.delete(0, "end")
    ui.entry_eff_min.insert(0, str(int(saved["eff_min"])
                                   if saved["eff_min"] == int(saved["eff_min"])
                                   else saved["eff_min"]))
    ui.entry_eff_max.delete(0, "end")
    ui.entry_eff_max.insert(0, str(int(saved["eff_max"])
                                   if saved["eff_max"] == int(saved["eff_max"])
                                   else saved["eff_max"]))
    ui.show_points_var.set(saved["show_points"])

    # ── Stato canvas ─────────────────────────────────────────────────────────
    state = {"canvas": None, "ax2": None,
             "tdh_sc": None, "eff_sc": None, "pwr_sc": None}

    def _save():
        if _css is None or acquisizione_id is None:
            return
        try:
            _css(acquisizione_id,
                 show_points=bool(ui.show_points_var.get()),
                 eff_min=float(ui.entry_eff_min.get()),
                 eff_max=float(ui.entry_eff_max.get()))
        except Exception:
            pass

    def _regenerate():
        try:
            emin = float(ui.entry_eff_min.get())
            emax = float(ui.entry_eff_max.get())
        except Exception:
            emin, emax = 0.0, 100.0
        return build_curve_figure(
            tdms_path,
            show_points=bool(ui.show_points_var.get()),
            eff_min=emin, eff_max=emax,
            unit_system=unit_system,
            return_artists=True,
            cache=cache,
            hidden_rows=hidden_rows,
        )

    def _apply_eff():
        if state["ax2"] is not None:
            try:
                vmin = float(ui.entry_eff_min.get())
                vmax = float(ui.entry_eff_max.get())
                if vmax > vmin:
                    state["ax2"].set_ylim(vmin, vmax)
                    state["canvas"].draw_idle()
                    _save()
                    return
            except Exception:
                pass
        # fallback: rigenera tutto
        res = _regenerate()
        if res is None or res == (None, {}, None):
            return
        fig, artists, ax2 = res
        for w in ui.right_frame.winfo_children():
            w.destroy()
        cv = FigureCanvasTkAgg(fig, master=ui.right_frame)
        wgt = cv.get_tk_widget()
        wgt.pack(fill="both", expand=True)
        state.update(canvas=cv, ax2=ax2,
                     tdh_sc=artists.get("tdh"),
                     eff_sc=artists.get("eff"),
                     pwr_sc=artists.get("pwr"))
        _save()

    def _toggle_points(*_):
        show = bool(ui.show_points_var.get())
        try:
            for key in ("tdh_sc", "eff_sc", "pwr_sc"):
                if state[key] is not None:
                    state[key].set_visible(show)
            state["canvas"].draw_idle()
            _save()
        except Exception:
            pass

    ui.btn_set_eff.config(command=_apply_eff)

    # ── Render iniziale ───────────────────────────────────────────────────────
    if not MPL_OK:
        import tkinter as tk
        tk.Label(ui.right_frame,
                 text="Matplotlib non disponibile.\nInstalla 'matplotlib'.",
                 justify="left").pack(anchor="nw", padx=10, pady=10)
        return

    res = _regenerate()
    if res is None or res == (None, {}, None):
        import tkinter as tk
        tk.Label(ui.right_frame,
                 text="Impossibile generare il grafico.",
                 justify="left").pack(anchor="nw", padx=10, pady=10)
        return

    fig, artists, ax2 = res
    cv = FigureCanvasTkAgg(fig, master=ui.right_frame)
    wgt = cv.get_tk_widget()
    wgt.pack(fill="both", expand=True)
    wgt.configure(height=1200)
    state.update(canvas=cv, ax2=ax2,
                 tdh_sc=artists.get("tdh"),
                 eff_sc=artists.get("eff"),
                 pwr_sc=artists.get("pwr"))

    wgt.update_idletasks()
    try:
        w_px = ui.right_frame.winfo_width() or wgt.winfo_width()
        h_px = wgt.winfo_height() or 1200
        if w_px > 0 and h_px > 0:
            fig.set_size_inches(w_px / fig.dpi, h_px / fig.dpi, forward=True)
    except Exception:
        pass
    cv.draw()

    # Abilita controlli
    ui.btn_set_eff.config(state="normal")
    ui.chk_show_points.config(state="normal")
    ui.show_points_var.trace_add("write", _toggle_points)

    # Resize live
    def _resize(_e=None):
        try:
            ui.right_frame.update_idletasks()
            w = ui.right_frame.winfo_width()
            h = wgt.winfo_height()
            if w > 0 and h > 0:
                fig.set_size_inches(w / fig.dpi, h / fig.dpi, forward=True)
                cv.draw_idle()
                ui.scroll_canvas.configure(
                    scrollregion=ui.scroll_canvas.bbox("all"))
        except Exception:
            pass

    ui.right_frame.bind("<Configure>", lambda e: _resize())
    # Resize quando il tab diventa visibile
    ui.frame.bind("<Map>", lambda e: ui.frame.after(50, _resize))

    ui.right_frame.update_idletasks()
    ui.scroll_canvas.configure(scrollregion=ui.scroll_canvas.bbox("all"))