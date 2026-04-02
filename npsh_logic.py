"""
npsh_logic.py
Logica della scheda NPSH Curve classica: lettura TDMS, matplotlib, render.
Istanzia NpshUI e popola i frame esposti.
La funzione build_npsh_figure e' riusabile da pdf_report.

Grafico NPSH classico (come certificato Excel):
  - Asse X: FLOW  (Converted Data, test_index=1), ordinato crescente
  - Asse Y: NPSH  (Converted Data, test_index=1)
  - Linea che collega i punti in ordine crescente di FLOW (X_curve)
  - Scatter separato dei punti (X_points), togglabile
  - Punto rated: triangolo (come Performance Curve)
"""
import math

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.lines import Line2D
    from matplotlib.path import Path
    MPL_OK = True
except Exception:
    MPL_OK = False

from tdms_reader import read_performance_tables_dynamic, read_contract_and_loop_data
from ui_format import fmt_if_number as _fmt_if_number
from curve_logic import _poly3_trendline, _dedupe_and_sort_xy


# ── MARKER ────────────────────────────────────────────────────────────────────
def _marker_triangle_right_angle_top_right():
    verts = [(-0.5, 0.5), (0.5, 0.5), (0.5, -0.5), (-0.5, 0.5)]
    codes = [Path.MOVETO, Path.LINETO, Path.LINETO, Path.CLOSEPOLY]
    return Path(verts, codes)

RIGHT_ANGLE_TR_MARKER = _marker_triangle_right_angle_top_right()

NPSH_TEST_INDEX = 1
FLOW_NAME = "FLOW"
NPSH_NAME = "NPSH"


# ── HELPERS ───────────────────────────────────────────────────────────────────

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


def _find_col(columns, base_name):
    """Trova indice colonna per nome base (senza unita')."""
    if not columns:
        return None
    for i, c in enumerate(columns):
        clean = str(c).upper().split("[")[0].strip()
        if clean == base_name.upper():
            return i
    return None


def _get_npsh_converted(tdms_path: str):
    perf = read_performance_tables_dynamic(tdms_path,
                                           test_index=NPSH_TEST_INDEX) or {}
    conv = perf.get("Converted") or {}
    return conv.get("columns") or [], conv.get("rows") or []


# ── BUILD FIGURE ──────────────────────────────────────────────────────────────

def build_npsh_figure(tdms_path: str, show_points: bool = True,
                      unit_system: str = "Metric", cache: dict = None,
                      hidden_rows: set = None):
    """
    Costruisce la figura matplotlib per la curva NPSH classica.
    Logica identica al certificato Excel:
      - linea che collega i punti ordinati per FLOW crescente
      - scatter separato togglabile
      - triangolo rated point
    """
    if not MPL_OK:
        return None, None

    try:
        import unit_converter as uc
    except Exception:
        uc = None
        unit_system = "Metric"

    # ── Leggi dati Converted ─────────────────────────────────────────────────
    if cache and cache.get("perf"):
        conv = cache["perf"].get("Converted") or {}
        conv_cols = conv.get("columns") or []
        conv_rows = conv.get("rows") or []
    else:
        conv_cols, conv_rows = _get_npsh_converted(tdms_path)

    # Filtra righe nascoste PRIMA di estrarre i dati
    if hidden_rows and conv_rows:
        hidden_idx = set()
        for iid in hidden_rows:
            try:
                hidden_idx.add(int(iid.lstrip("p")) - 1)
            except Exception:
                pass
        conv_rows = [r for i, r in enumerate(conv_rows) if i not in hidden_idx]

    ix_flow = _find_col(conv_cols, FLOW_NAME)
    ix_npsh = _find_col(conv_cols, NPSH_NAME)

    xs_raw, ys_raw = [], []
    if ix_flow is not None and ix_npsh is not None:
        for r in conv_rows:
            xv = _to_float(r[ix_flow] if ix_flow < len(r) else None)
            yv = _to_float(r[ix_npsh] if ix_npsh < len(r) else None)
            if xv is not None and yv is not None:
                xs_raw.append(xv)
                ys_raw.append(yv)

    # Converti unita' solo se dati NON dalla cache

    from_cache = bool(cache and cache.get("from_cache"))
    if not from_cache and uc and unit_system != "Metric":
        xs_raw = [uc.convert_value(x, "flow", "Metric", unit_system) for x in xs_raw]
        ys_raw = [uc.convert_value(y, "npsh", "Metric", unit_system) for y in ys_raw]

    # ── Dati contrattuali ─────────────────────────────────────────────────────
    raw_contract = (cache.get("contract") if cache else None) or \
                   read_contract_and_loop_data(tdms_path) or {}
    if from_cache:
        contract = raw_contract
    elif uc:
        contract = uc.convert_contractual_data(raw_contract, "Metric", unit_system)
    else:
        contract = raw_contract

    import re as _re
    def _gc(base, fb=""):
        """Cerca nel contratto per nome base ignorando le unita'."""
        for k, v in contract.items():
            kb = _re.sub(r"\s*\[[^\]]*\]\s*$", "", k).strip().lower()
            if kb == base.lower() and v is not None and str(v).strip():
                return str(v)
        return fb

    flow_unit = uc.get_unit_label("flow", unit_system) if uc else "m³/h"
    npsh_unit = uc.get_unit_label("npsh", unit_system) if uc else "m"

    rated_q    = _to_float(_gc("Capacity"))
    rated_npsh = _to_float(_gc("NPSH"))

    # ── Figura ────────────────────────────────────────────────────────────────
    fig = Figure(figsize=(11, 7), dpi=100)
    ax  = fig.add_subplot(111)

    npsh_line = None
    sc        = None
    has_rated = False

    # Scatter punti (togglabile)
    if xs_raw and ys_raw:
        sc = ax.scatter(xs_raw, ys_raw, s=35, color="tab:blue",
                        zorder=5, label="_nolegend_")
        sc.set_visible(show_points)

    # Trendline polinomiale di grado 3 (stesso approccio di curve_logic)
    if xs_raw and ys_raw:
        xs_d, ys_d = _dedupe_and_sort_xy(xs_raw, ys_raw)
        if xs_d:
            a, b, c, d, _ = _poly3_trendline(xs_d, ys_d)
            if a is not None and len(xs_d) >= 4:
                xmin, xmax = min(xs_d), max(xs_d)
                num = max(50, min(400, 10 * len(xs_d)))
                x_curve = [xmin + (xmax - xmin) * i / (num - 1) for i in range(num)]
                y_curve = [a*x**3 + b*x**2 + c*x + d for x in x_curve]
                npsh_line = ax.plot(x_curve, y_curve,
                                    linewidth=1.8, color="tab:blue", label="NPSH")[0]
            else:
                # Fallback: linea semplice se punti insufficienti
                npsh_line = ax.plot(xs_d, ys_d,
                                    linewidth=1.8, color="tab:blue", label="NPSH")[0]

    # Triangolo rated point
    if rated_q is not None and rated_npsh is not None:
        ax.scatter([rated_q], [rated_npsh],
                   marker=RIGHT_ANGLE_TR_MARKER, s=140,
                   facecolors="none", edgecolors="tab:red",
                   linewidths=1.6, zorder=10)
        has_rated = True

    # Assi e griglia
    ax.set_xlabel(f"Flow [{flow_unit}]")
    ax.set_ylabel(f"NPSH [{npsh_unit}]")
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.grid(True, linestyle=":", linewidth=0.8)

    ax.relim()
    ax.autoscale(axis="y")
    _, ymax = ax.get_ylim()
    ax.set_ylim(bottom=0, top=ymax * 1.15)

    # Legenda
    handles, labels = [], []
    if npsh_line:
        handles.append(npsh_line)
        labels.append("NPSH")
    if has_rated:
        handles.append(
            Line2D([0], [0], marker=RIGHT_ANGLE_TR_MARKER, linestyle="None",
                   markersize=10, markerfacecolor="none",
                   markeredgecolor="tab:red", markeredgewidth=1.6)
        )
        labels.append("Rated NPSH")
    if handles:
        ax.legend(handles, labels, loc="upper right")

    fig.tight_layout()
    return fig, sc   # restituisce anche lo scatter per il toggle


# ── RENDER PUBBLICO ───────────────────────────────────────────────────────────

def render_npsh_tab(parent, tdms_path: str, acquisizione_id: int = None,
                    cache: dict = None):
    """
    Popola il frame `parent` (tab_npsh di CertificateUI) con la scheda
    NPSH Curve classica.
    cache: dizionario con dati TDMS gia' letti (evita riapertura file).
    """
    from npsh_ui import NpshUI
    import tkinter as tk

    try:
        from db import get_unit_system
        unit_system = get_unit_system(acquisizione_id) if acquisizione_id else "Metric"
    except Exception:
        unit_system = "Metric"

    # ── Dati contrattuali per i blocchi KV ────────────────────────────────────
    try:
        import unit_converter as uc
        raw_contract = (cache.get("contract") if cache else None) or                        read_contract_and_loop_data(tdms_path) or {}
        if cache and cache.get("from_cache"):
            data = raw_contract
        else:
            data = uc.convert_contractual_data(raw_contract, "Metric", unit_system)
        fl = uc.get_unit_label("flow",  unit_system)
        nl = uc.get_unit_label("npsh",  unit_system)
        tl = uc.get_unit_label("temp",  unit_system)
    except Exception:
        uc   = None
        data = (cache.get("contract") if cache else None) or                read_contract_and_loop_data(tdms_path) or {}
        fl, nl, tl = "m³/h", "m", "°C"

    def _g(k, fb="—"):
        return data.get(k, "") or fb

    ui = NpshUI(parent)

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
        (f"Capacity [{fl}]",    _fmt_if_number(_g(f"Capacity [{fl}]",
                                                   _g("Capacity [m3/h]")))),
        (f"NPSH [{nl}]",        _fmt_if_number(_g(f"NPSH [{nl}]",
                                                   _g("NPSH [m]")))),
        ("Speed [rpm]",         _fmt_if_number(_g("Speed [rpm]"))),
        ("SG",                  _fmt_if_number(_g("SG Contract"))),
        (f"Temperature [{tl}]", _fmt_if_number(_g(f"Temperature [{tl}]",
                                                   _g("Temperature [°C]")))),
        ("Viscosity [cP]",      _fmt_if_number(_g("Viscosity [cP]"))),
        ("Liquid",              _g("Liquid")),
    ]
    ui.populate_kv_blocks(contractual_rows, rated_rows)

    # ── Render grafico ────────────────────────────────────────────────────────
    if not MPL_OK:
        tk.Label(ui.right_frame,
                 text="Matplotlib non disponibile.\nInstalla 'matplotlib'.",
                 justify="left").pack(anchor="nw", padx=10, pady=10)
        return

    # Carica righe nascoste dal DB
    _hidden_rows_npsh = set()
    try:
        from db import hidden_rows_get as _hrg2
        _hidden_rows_npsh = _hrg2(acquisizione_id, "NPSH") if acquisizione_id else set()
    except Exception:
        pass

    fig, sc = build_npsh_figure(
        tdms_path,
        show_points=bool(ui.show_points_var.get()),
        unit_system=unit_system,
        cache=cache,
        hidden_rows=_hidden_rows_npsh,
    )

    if fig is None:
        tk.Label(ui.right_frame,
                 text="Dati NPSH non disponibili.",
                 justify="left").pack(anchor="nw", padx=10, pady=10)
        return

    cv  = FigureCanvasTkAgg(fig, master=ui.right_frame)
    wgt = cv.get_tk_widget()
    wgt.pack(fill="both", expand=True)
    wgt.configure(height=800)
    cv.draw()

    # ── Toggle punti ─────────────────────────────────────────────────────────
    def _toggle_points(*_):
        if sc is not None:
            sc.set_visible(bool(ui.show_points_var.get()))
            cv.draw_idle()

    ui.chk_show_points.config(state="normal")
    ui.show_points_var.trace_add("write", _toggle_points)

    # ── Resize live ───────────────────────────────────────────────────────────
    def _resize(_e=None):
        try:
            ui.right_frame.update_idletasks()
            w = ui.right_frame.winfo_width() or ui.scroll_canvas.winfo_width()
            h = wgt.winfo_height() or 800
            if w > 50 and h > 50:
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