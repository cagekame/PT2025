"""
certificate_logic.py
Logica del certificato: lettura TDMS, render blocchi/tabelle, sync scroll.
Istanzia CertificateUI e popola i frame esposti.
"""
import os
import logging
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from ui_format import fmt_if_number as _fmt_if_number
from tdms_reader import read_all_data
from progress_window import ProgressWindow
from certificate_ui import (
    CertificateUI,
    make_block,
    measure_title,
    kv_row,
    ACCENT, BG_WHITE, BG_APP, BORDER, TEXT_SEC, TEXT_MAIN,
)

logger = logging.getLogger(__name__)

TEST_INDEX_MAP = {"PERFORMANCE": 0, "NPSH": 1, "RUNNING": 2}


# ── HELPERS DB ────────────────────────────────────────────────────────────────

def find_missing_tdms(old_path: str):
    old_filename = os.path.basename(old_path) if old_path else "file.tdms"
    new_path = filedialog.askopenfilename(
        title=f"Cerca: {old_filename}",
        filetypes=[("TDMS files", "*.tdms"), ("All files", "*.*")],
        initialfile=old_filename,
    )
    if new_path:
        new_filename = os.path.basename(new_path)
        if new_filename != old_filename:
            if not messagebox.askyesno("Nome file diverso",
                    f"File originale: {old_filename}\n"
                    f"File selezionato: {new_filename}\n\n"
                    "Sei sicuro che sia lo stesso file?"):
                return None
    return new_path


def update_tdms_path(acquisizione_id, new_path: str) -> bool:
    if not acquisizione_id:
        return False
    try:
        import db
        with db.connect() as conn:
            conn.cursor().execute(
                "UPDATE acquisizioni SET filepath = ? WHERE id = ?",
                (new_path, acquisizione_id)
            )
            conn.commit()
        return True
    except Exception as e:
        messagebox.showerror("Errore DB",
            f"Impossibile aggiornare il percorso:\n{e}")
        return False


# ── CACHE TDMS ───────────────────────────────────────────────────────────────

def _build_cache(tdms_path: str, test_index: int,
                 on_progress=None, unit_system: str = "Metric") -> dict:
    """
    Restituisce i dati necessari per blocchi, tabelle e curve.
    Legge dal .ptcache se disponibile (veloce su rete),
    altrimenti legge direttamente dal TDMS.
    on_progress: callable(percent, message) opzionale per aggiornare UI.
    """
    empty = {
        "contract":        {},
        "perf":            {"Recorded": {"columns": [], "rows": []},
                            "Calc":     {"columns": [], "rows": []},
                            "Converted":{"columns": [], "rows": []}},
        "power_calc_type": "-",
    }
    if not tdms_path:
        return empty

    # ── Prova a leggere dal ptcache (veloce su rete) ────────────────────────
    try:
        import ptcache
        if ptcache.exists(tdms_path):
            if on_progress:
                on_progress(10, "Loading from cache...")
            cached = ptcache.load(tdms_path, test_index=test_index,
                                       unit_system=unit_system)
            if cached:
                if on_progress:
                    on_progress(55, "Cache loaded.")
                cached["from_cache"] = True
                return cached
    except Exception:
        pass

    # ── Fallback: leggi dal TDMS e genera ptcache ────────────────────────────
    if on_progress:
        on_progress(5, "Opening TDMS file...")
    try:
        from tdms_reader import read_all_data
        result = read_all_data(tdms_path, test_index=test_index,
                               on_progress=on_progress)

        # Genera il ptcache in background solo se non esiste gia'
        def _generate_cache():
            try:
                import ptcache
                import threading
                if ptcache.exists(tdms_path):
                    return
                def _gen():
                    try:
                        ptcache.generate(tdms_path)
                    except Exception:
                        pass
                threading.Thread(target=_gen, daemon=True).start()
            except Exception:
                pass
        _generate_cache()

        return result
    except Exception:
        return empty


# ── RENDER BLOCCHI ────────────────────────────────────────────────────────────

def _render_blocks(ui: CertificateUI, cache: dict,
                   unit_system: str, job: str, values: tuple,
                   acquisizione_id=None):
    """Popola ui.blocks con i tre card KV (Contractual / Rated / Loop)."""
    for w in ui.blocks.winfo_children():
        w.destroy()

    # Valori di default
    cap = tdh = eff = abs_pow = speed = sg = temp = visc = npsh = liquid = "-"
    cust = po = end_user = specs = "-"
    item = pump = sn = imp_draw = imp_mat = imp_dia = "-"
    suction = discharge = watt_const = atmpress = knpsh = watertemp = kventuri = "-"
    power_calc_type = "-"

    uc = None
    data = {}
    try:
        import unit_converter as uc
        if cache.get("from_cache"):
            # Dati gia' nel sistema corretto dal ptcache
            data = cache.get("contract", {})
        else:
            data = uc.convert_contractual_data(
                cache.get("contract", {}), "Metric", unit_system)
    except Exception:
        uc = None

    power_calc_type = cache.get("power_calc_type", "-") or "-"

    # Chiavi dinamiche per unità
    def _ul(q): return uc.get_unit_label(q, unit_system) if uc else {
        "flow": "m³/h", "head": "m", "power": "kW",
        "temp": "°C", "npsh": "m", "pressure": "m"
    }[q]

    cap_key  = f"Capacity [{_ul('flow')}]"
    tdh_key  = f"TDH [{_ul('head')}]"
    pow_key  = f"ABS_Power [{_ul('power')}]"
    temp_key = f"Temperature [{_ul('temp')}]"
    npsh_key = f"NPSH [{_ul('npsh')}]"
    atm_key  = f"AtmPress [{_ul('pressure')}]"
    knpsh_key = f"KNPSH [{_ul('npsh')}]"
    wt_key   = f"WaterTemp [{_ul('temp')}]"

    cap     = _fmt_if_number(data.get(cap_key,
              data.get("Capacity [m3/h]", data.get("Capacity [m³/h]", ""))))
    tdh     = _fmt_if_number(data.get(tdh_key, ""))
    eff     = _fmt_if_number(data.get("Efficiency [%]", ""))
    abs_pow = _fmt_if_number(data.get(pow_key, ""))
    speed   = _fmt_if_number(data.get("Speed [rpm]", ""))
    sg      = _fmt_if_number(data.get("SG Contract", ""))
    temp    = _fmt_if_number(data.get(temp_key,
              data.get("Temperature [°C]", data.get("Temperature [C]", ""))))
    visc    = _fmt_if_number(data.get("Viscosity [cP]", ""))
    npsh    = _fmt_if_number(data.get(npsh_key, ""))
    liquid  = data.get("Liquid", "") or "-"

    cust     = data.get("Customer", "") or "-"
    po       = data.get("Purchaser Order", "") or "-"
    end_user = data.get("End User", "") or "-"
    specs    = data.get("Applic. Specs.", "") or "-"
    item     = data.get("Item", "") or "-"
    pump     = data.get("Pump", "") or "-"
    sn       = data.get("Serial Number_Elenco", "") or "-"
    imp_draw = data.get("Impeller Drawing", "") or "-"
    imp_mat  = data.get("Impeller Material", "") or "-"
    imp_dia  = data.get("Diam Nominal", "") or "-"

    suction    = _fmt_if_number(data.get("Suction [Inch]", ""))
    discharge  = _fmt_if_number(data.get("Discharge [Inch]", ""))
    watt_const = _fmt_if_number(data.get("Wattmeter Const.", ""))

    # Leggi test_cell e hydraulic dal DB
    _loop_detail = {"test_cell": "", "hydraulic": ""}
    try:
        from db import get_loop_detail, set_loop_detail as _set_loop_detail
        _loop_detail = get_loop_detail(acquisizione_id)
    except Exception:
        _set_loop_detail = None
    atmpress   = _fmt_if_number(data.get(atm_key, data.get("AtmPress [m]", "")))
    knpsh      = _fmt_if_number(data.get(knpsh_key, data.get("KNPSH [m]", "")))
    watertemp  = _fmt_if_number(data.get(wt_key,
                 data.get("WaterTemp [°C]", data.get("WaterTemp [C]", ""))))
    kventuri   = _fmt_if_number(data.get("KVenturi", ""))

    flow_unit  = _ul("flow"); head_unit = _ul("head")
    power_unit = _ul("power"); temp_unit = _ul("temp"); npsh_unit = _ul("npsh")

    pump_model = pump if pump and pump != "-" else (
        values[3] if len(values) > 3 else "-")

    # --- Contractual Data ---
    b1 = make_block(ui.blocks, "CONTRACTUAL DATA", [
        ("FSG ORDER",    job if job and job != "-" else "-"),
        ("CUSTOMER",     cust),
        ("P.O.",         po),
        ("End User",     end_user),
        ("Item",         item),
        ("Pump",         pump_model),
        ("S. N.",        sn),
        ("Imp. Draw.",   imp_draw),
        ("Imp. Mat.",    imp_mat),
        ("Imp Dia [mm]", imp_dia),
        ("Specs",        specs),
    ])
    b1.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

    # --- Rated Point ---
    b2 = make_block(ui.blocks, "RATED POINT", [
        (f"Capacity [{flow_unit}]",  cap),
        (f"TDH [{head_unit}]",       tdh),
        ("Efficiency [%]",           eff),
        (f"ABS_Power [{power_unit}]", abs_pow),
        ("Speed [rpm]",              speed),
        ("SG",                       sg),
        (f"Temperature [{temp_unit}]", temp),
        ("Viscosity [cP]",           visc),
        (f"NPSH [{npsh_unit}]",      npsh),
        ("Liquid",                   liquid),
    ])
    b2.grid(row=0, column=1, sticky="nsew", padx=6)

    # --- Loop Details ---
    outer = tk.Frame(ui.blocks, bg=BORDER)
    tk.Label(outer, text="LOOP DETAILS", bg=ACCENT, fg="white",
             font=("Segoe UI", 9, "bold"),
             anchor="w", padx=10, pady=5).pack(fill=tk.X)
    inner = tk.Frame(outer, bg=BG_WHITE)
    inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=(0, 1))

    # Riga "Test performed with" (label bold)
    test_f = tk.Frame(inner, bg=BG_WHITE)
    test_f.pack(fill="x")
    tk.Label(test_f, text="Test performed", bg=BG_WHITE, fg=TEXT_SEC,
             font=("Segoe UI", 9), width=18, anchor="w",
             padx=8, pady=3).pack(side=tk.LEFT)
    tk.Frame(test_f, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, pady=2)
    tk.Label(test_f, text=power_calc_type or "-", bg=BG_WHITE, fg=TEXT_MAIN,
             font=("Segoe UI", 9, "bold"),
             anchor="w", padx=8).pack(side=tk.LEFT, fill=tk.X, expand=True)
    tk.Frame(inner, bg="#f3f4f6", height=1).pack(fill=tk.X)

    loop_rows = [
        ("Suction [Inch]",    suction),
        ("Discharge [Inch]",  discharge),
        ("Wattmeter Const.",  watt_const),
        (f"AtmPress [{head_unit}]", atmpress),
        (f"KNPSH [{npsh_unit}]",    knpsh),
        (f"WaterTemp [{temp_unit}]", watertemp),
        ("Kventuri",          kventuri),
    ]
    for i, (lbl, val) in enumerate(loop_rows):
        row_bg = BG_WHITE if i % 2 == 0 else "#fafafa"
        row = tk.Frame(inner, bg=row_bg)
        row.pack(fill="x")
        tk.Label(row, text=lbl, bg=row_bg, fg=TEXT_SEC,
                 font=("Segoe UI", 9), width=18, anchor="w",
                 padx=8, pady=3).pack(side=tk.LEFT)
        tk.Frame(row, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, pady=2)
        tk.Label(row, text=val or "-", bg=row_bg, fg=TEXT_MAIN,
                 font=("Segoe UI", 9, "bold"),
                 anchor="w", padx=8).pack(side=tk.LEFT, fill=tk.X, expand=True)
        if i < len(loop_rows) - 1:
            tk.Frame(inner, bg="#f3f4f6", height=1).pack(fill=tk.X)

    # Separatore
    tk.Frame(inner, bg="#f3f4f6", height=1).pack(fill=tk.X)

    # ── Test Cell (combobox) ──────────────────────────────────────────────────
    _TEST_CELLS = [
        "HPX1","HPX2","HPX3","HPX4","HPX5","HPX6","HPX 7",
        "OH1","OH2","OH3","OH4","OH5","OH6","OH9",
        "C1 R5","C1 R4","C2 R3","C2 R2","C2 R1",
        "VDX1","VDX2","VDX3","VSX1","VSX2","VSX3",
        "R1","R2","V8","V6","HE1","HE2","HF",
        "STRING AREA",'40" HF',"C5","R3","OH7",
    ]
    row_tc = tk.Frame(inner, bg=BG_WHITE)
    row_tc.pack(fill="x")
    tk.Label(row_tc, text="Test Cell", bg=BG_WHITE, fg=TEXT_SEC,
             font=("Segoe UI", 9), width=18, anchor="w",
             padx=8, pady=3).pack(side=tk.LEFT)
    tk.Frame(row_tc, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, pady=2)
    import tkinter.ttk as _ttk
    _tc_var = tk.StringVar(value=_loop_detail.get("test_cell", ""))
    _tc_cb  = _ttk.Combobox(row_tc, textvariable=_tc_var,
                              values=_TEST_CELLS, width=18, state="normal",
                              font=("Segoe UI", 9))
    _tc_cb.pack(side=tk.LEFT, padx=8, pady=2)

    tk.Frame(inner, bg="#f3f4f6", height=1).pack(fill=tk.X)

    # ── Hydraulic (entry libera) ──────────────────────────────────────────────
    row_hy = tk.Frame(inner, bg="#fafafa")
    row_hy.pack(fill="x")
    tk.Label(row_hy, text="Hydraulic", bg="#fafafa", fg=TEXT_SEC,
             font=("Segoe UI", 9), width=18, anchor="w",
             padx=8, pady=3).pack(side=tk.LEFT)
    tk.Frame(row_hy, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, pady=2)
    _hy_var = tk.StringVar(value=_loop_detail.get("hydraulic", ""))
    _hy_entry = tk.Entry(row_hy, textvariable=_hy_var, width=20,
                          font=("Segoe UI", 9), relief="flat",
                          bg="#fafafa", fg=TEXT_MAIN)
    _hy_entry.pack(side=tk.LEFT, padx=8, pady=2)

    # Salva automaticamente al cambio valore
    def _save_loop_detail(*_):
        if _set_loop_detail and acquisizione_id:
            try:
                _set_loop_detail(acquisizione_id,
                                 _tc_var.get().strip(),
                                 _hy_var.get().strip())
            except Exception:
                pass

    _tc_var.trace_add("write", _save_loop_detail)
    _hy_var.trace_add("write", _save_loop_detail)

    outer.grid(row=0, column=2, sticky="nsew", padx=(6, 0))


# ── RENDER TABELLE ────────────────────────────────────────────────────────────

def _render_tables(ui: CertificateUI, cache: dict,
                   unit_system: str, test_index: int,
                   acquisizione_id=None, refresh_curve=None):
    """Popola ui.tables_row con le tre Treeview."""
    for w in ui.tables_row.winfo_children():
        w.destroy()

    uc = None
    try:
        import unit_converter as uc
        perf = cache.get("perf") or {
            "Recorded":  {"columns": [], "rows": []},
            "Calc":      {"columns": [], "rows": []},
            "Converted": {"columns": [], "rows": []},
        }
    except Exception:
        perf = {
            "Recorded":  {"columns": [], "rows": []},
            "Calc":      {"columns": [], "rows": []},
            "Converted": {"columns": [], "rows": []},
        }
        uc = None

    rec_cols,  rec_rows  = perf["Recorded"]["columns"],  perf["Recorded"]["rows"]
    calc_cols, calc_rows = perf["Calc"]["columns"],      perf["Calc"]["rows"]
    conv_cols, conv_rows = perf["Converted"]["columns"], perf["Converted"]["rows"]

    # Normalizza unita' per le colonne Recorded:
    # PERFORMANCE (test_index=0): unita' gia' nel nome canale, solo replace ASCII->Unicode
    # NPSH/RUNNING (test_index!=0): nessuna unita' nel canale, le aggiunge dalla column_map
    try:
        from unit_converter import normalize_recorded_columns
        rec_cols = normalize_recorded_columns(
            rec_cols,
            unit_system=unit_system,
            has_units=(test_index == 0),
        )
    except Exception:
        pass

    def _prune_empty(cols, rows):
        if not cols or not rows:
            return [], []
        keep = []
        for i in range(len(cols)):
            for r in rows:
                v = r[i] if i < len(r) else None
                if v is None:
                    continue
                s = str(v).strip()
                if not s:
                    continue
                try:
                    if abs(float(s.replace(",", "."))) > 1e-12:
                        keep.append(i); break
                except Exception:
                    keep.append(i); break
        if not keep:
            return [], []
        return ([cols[i] for i in keep],
                [tuple((r[i] if i < len(r) else "") for i in keep) for r in rows])

    if uc:
        if cache.get("from_cache"):
            # Dati dalla cache: valori gia' nel sistema corretto
            # ma le colonne Metric non hanno unita' — aggiungiamole
            # chiamando convert_performance_table con stesso sistema (aggiunge solo header)
            calc_cols, calc_rows = uc.convert_performance_table(
                calc_cols, calc_rows, unit_system, unit_system)
            conv_cols, conv_rows = uc.convert_performance_table(
                conv_cols, conv_rows, unit_system, unit_system)
        else:
            # Dati dal TDMS: converti da Metric al sistema richiesto
            calc_cols, calc_rows = uc.convert_performance_table(
                calc_cols, calc_rows, "Metric", unit_system)
            conv_cols, conv_rows = uc.convert_performance_table(
                conv_cols, conv_rows, "Metric", unit_system)

    rec_cols,  rec_rows  = _prune_empty(rec_cols  or [], rec_rows  or [])
    calc_cols, calc_rows = _prune_empty(calc_cols or [], calc_rows or [])
    conv_cols, conv_rows = _prune_empty(conv_cols or [], conv_rows or [])

    def _make_table(parent, title, cols, mode):
        outer = tk.Frame(parent, bg=BORDER)

        # Titolo tabella
        tk.Label(outer, text=title, bg="#f8f9fb", fg=TEXT_MAIN,
                 font=("Segoe UI", 9, "bold"),
                 anchor="w", padx=10, pady=6).pack(fill=tk.X)
        tk.Frame(outer, bg=BORDER, height=1).pack(fill=tk.X)

        inner = tk.Frame(outer, bg=BG_WHITE)
        inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=(0, 1))
        inner.rowconfigure(0, weight=1)
        inner.columnconfigure(0, weight=1)
        inner.columnconfigure(1, weight=0)

        tv = ttk.Treeview(inner, columns=cols or ("-",),
                          show="headings", style="Cert.Treeview",
                          selectmode="browse")
        vsb = ttk.Scrollbar(inner, orient="vertical")

        minwidths = []
        if not cols:
            tv.heading("-", text="-")
            mw = measure_title(tv, "-")
            tv.column("-", minwidth=mw, width=mw,
                      anchor="center", stretch=True)
            minwidths = [mw]
        else:
            for c in cols:
                tv.heading(c, text=c)
                mw = measure_title(tv, c)
                tv.column(c, minwidth=mw, width=mw,
                          anchor="center", stretch=True)
                minwidths.append(mw)

        tv.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        return outer, tv, vsb, (cols if cols else ["-"]), minwidths

    lf_l, tv_l, vsb_l, l_cols, l_mins = _make_table(
        ui.tables_row, "Recorded Data",    rec_cols,  "left")
    lf_m, tv_m, vsb_m, m_cols, m_mins = _make_table(
        ui.tables_row, "Calculated Values", calc_cols, "center")
    lf_r, tv_r, vsb_r, r_cols, r_mins = _make_table(
        ui.tables_row, "Converted Values",  conv_cols, "right")

    lf_l.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    lf_m.grid(row=0, column=1, sticky="nsew", padx=6)
    lf_r.grid(row=0, column=2, sticky="nsew", padx=(6, 0))

    # Popola righe
    # Se i dati vengono dal ptcache sono gia' arrotondati — nessuna formattazione
    # Se vengono dal TDMS sono float raw — applica fmt_if_number
    _fmt = (lambda v: str(v) if v not in (None, "") else "—")            if cache.get("from_cache") else _fmt_if_number

    for idx, vals in enumerate(rec_rows, 1):
        tv_l.insert("", "end", iid=f"p{idx:03d}",
                    values=[_fmt(v) for v in vals])
    for idx, vals in enumerate(calc_rows, 1):
        tv_m.insert("", "end", iid=f"p{idx:03d}",
                    values=[_fmt(v) for v in vals])
    for idx, vals in enumerate(conv_rows, 1):
        tv_r.insert("", "end", iid=f"p{idx:03d}",
                    values=[_fmt(v) for v in vals])

    # ── Layout colonne: possibilita' 1 ───────────────────────────────────────
    # Larghezza minima = titolo colonna.
    # Spazio extra distribuito flat su TUTTE le colonne delle 3 tabelle.
    # Al ridimensionamento finestra: ricalcolo dinamico.
    # Minsize finestra = somma di tutti i minimi + padding.

    # Raggruppa tutte le info per il calcolo globale
    _tables = [
        (tv_l, l_cols, l_mins),
        (tv_m, m_cols, m_mins),
        (tv_r, r_cols, r_mins),
    ]
    _total_cols = sum(len(mins) for _, _, mins in _tables)
    _total_mins = sum(sum(mins) for _, _, mins in _tables)
    # Padding: 2 gap da 6px tra le 3 tabelle + 2px bordi per tabella * 3
    _PAD_BETWEEN = 6 * 2 + 6
    # Ogni tabella ha una scrollbar verticale (~18px ciascuna)
    _SCROLLBAR_W = 18 * 3
    # Minsize finestra basata sulla somma di tutti i minimi + scrollbar
    _WIN_MIN_W = _total_mins + _PAD_BETWEEN + _SCROLLBAR_W + 200  # 200 = margini finestra
    _WIN_MIN_H = 800

    def _distribute_extra(avail_w):
        """
        Distribuisce lo spazio disponibile flat su tutte le colonne.
        avail_w: larghezza totale disponibile per le 3 tabelle insieme.
        """
        if _total_cols == 0:
            return
        extra = max(0, avail_w - _total_mins)
        extra_per_col = extra // _total_cols
        remainder = extra % _total_cols
        col_idx = 0
        for tv, cols, mins in _tables:
            if not cols or cols == ["-"]:
                continue
            for i, (c, m) in enumerate(zip(cols, mins)):
                add = extra_per_col + (1 if col_idx < remainder else 0)
                tv.column(c, width=m + add, minwidth=m)
                col_idx += 1

    def _on_resize(_e=None):
        """Ricalcola le larghezze al ridimensionamento della finestra."""
        try:
            ui.win.update_idletasks()
        except Exception:
            return
        # Larghezza finestra meno margini, padding tabelle e scrollbar (18px x 3)
        avail = ui.win.winfo_width() - 48 - _PAD_BETWEEN - _SCROLLBAR_W
        _distribute_extra(avail)

    # Applica minsize e layout iniziale
    def _apply_minsize():
        ui.win.minsize(_WIN_MIN_W, _WIN_MIN_H)
        if ui.win.winfo_width() < _WIN_MIN_W:
            ui.win.geometry(f"{_WIN_MIN_W}x{_WIN_MIN_H}")
        _on_resize()

    ui.tables_row.bind("<Configure>", _on_resize)
    ui.win.after_idle(_apply_minsize)
    ui.win.after_idle(lambda: ui.win.after_idle(_apply_minsize))

    # ── Sincronizzazione selezione ────────────────────────────────────────────
    _sync = {"busy": False, "iid": None}

    def _apply_sync(iid, src):
        for tv in (tv_l, tv_m, tv_r):
            if tv is src:
                continue
            try:
                if tv.exists(iid):
                    tv.selection_set(iid); tv.focus(iid); tv.see(iid)
            except Exception:
                pass

    def _on_sel(src, _e=None):
        if _sync["busy"]:
            return
        sel = src.selection()
        iid = sel[0] if sel else None
        if not iid or _sync["iid"] == iid:
            return
        _sync["busy"] = True
        _sync["iid"]  = iid
        ui.win.after_idle(lambda: (
            _apply_sync(iid, src), _sync.update(busy=False)))

    for tv in (tv_l, tv_m, tv_r):
        tv.bind("<<TreeviewSelect>>", lambda e, s=tv: _on_sel(s, e))

    # ── Sincronizzazione scroll ───────────────────────────────────────────────
    _scr = {"busy": False}

    def _sync_scroll(*args):
        if _scr["busy"]:
            return
        _scr["busy"] = True
        first = args[0]
        for vsb, tv in [(vsb_l, tv_l), (vsb_m, tv_m), (vsb_r, tv_r)]:
            tv.yview_moveto(first)
            vsb.set(args[0], args[1])
        _scr["busy"] = False

    def _on_vsb(tv_target, *args):
        if _scr["busy"]:
            return
        _scr["busy"] = True
        tv_target.yview(*args)
        first, last = tv_target.yview()
        for vsb, tv in [(vsb_l, tv_l), (vsb_m, tv_m), (vsb_r, tv_r)]:
            if tv is not tv_target:
                tv.yview_moveto(first)
            vsb.set(first, last)
        _scr["busy"] = False

    tv_l.configure(yscrollcommand=_sync_scroll)
    tv_m.configure(yscrollcommand=_sync_scroll)
    tv_r.configure(yscrollcommand=_sync_scroll)
    vsb_l.configure(command=lambda *a: _on_vsb(tv_l, *a))
    vsb_m.configure(command=lambda *a: _on_vsb(tv_m, *a))
    vsb_r.configure(command=lambda *a: _on_vsb(tv_r, *a))

    # ── Menu contestuale tasto destro (nascondi/mostra righe) ───────────────
    _test_type_str = {0: "PERFORMANCE", 1: "NPSH", 2: "RUNNING"}.get(test_index, "PERFORMANCE")
    _acq_id = acquisizione_id   # parametro locale per closure
    try:
        from db import hidden_rows_get, hidden_rows_set as _hrs
        _hidden_rows = hidden_rows_get(_acq_id, _test_type_str)
    except Exception:
        _hrs = None
        _hidden_rows = set()

    def _apply_hidden():
        """Applica le righe nascoste alle treeview."""
        for iid in list(_hidden_rows):
            for tv in (tv_l, tv_m, tv_r):
                try:
                    tv.detach(iid)
                except Exception:
                    pass

    def _save_hidden():
        """Salva le righe nascoste nel DB."""
        if _hrs and _acq_id:
            try:
                _hrs(_acq_id, _test_type_str, _hidden_rows)
            except Exception:
                pass

    def _hide_row(iid):
        """Nasconde la riga iid in tutte e tre le tabelle e salva nel DB."""
        _hidden_rows.add(iid)
        for tv in (tv_l, tv_m, tv_r):
            try:
                tv.detach(iid)
            except Exception:
                pass
        _save_hidden()
        if refresh_curve:
            refresh_curve()

    def _show_all_rows():
        """Ripristina tutte le righe nascoste e aggiorna il DB."""
        for iid in sorted(_hidden_rows):
            for tv in (tv_l, tv_m, tv_r):
                try:
                    tv.reattach(iid, "", "end")
                except Exception:
                    pass
        _hidden_rows.clear()
        for tv in (tv_l, tv_m, tv_r):
            children = sorted(tv.get_children())
            for i, iid in enumerate(children):
                tv.move(iid, "", i)
        _save_hidden()
        if refresh_curve:
            refresh_curve()

    def _on_right_click(event, src_tv):
        """Mostra il menu contestuale sul tasto destro."""
        row_id = src_tv.identify_row(event.y)
        if not row_id:
            if not _hidden_rows:
                return
            menu = tk.Menu(ui.win, tearoff=0)
            menu.add_command(
                label=f"Show all rows ({len(_hidden_rows)} hidden)",
                command=_show_all_rows)
            menu.tk_popup(event.x_root, event.y_root)
            return

        src_tv.selection_set(row_id)
        menu = tk.Menu(ui.win, tearoff=0)
        menu.add_command(
            label="Hide row",
            command=lambda: _hide_row(row_id))
        if _hidden_rows:
            menu.add_separator()
            menu.add_command(
                label=f"Show all rows ({len(_hidden_rows)} hidden)",
                command=_show_all_rows)
        menu.tk_popup(event.x_root, event.y_root)

    for tv in (tv_l, tv_m, tv_r):
        tv.bind("<Button-3>", lambda e, s=tv: _on_right_click(e, s))

    # Applica righe nascoste caricate dal DB
    _apply_hidden()

    # Selezione iniziale
    first = next(iter(tv_l.get_children()), None)
    if first:
        tv_l.selection_set(first); tv_l.focus(first)


# ── FUNZIONE PUBBLICA ─────────────────────────────────────────────────────────

def open_detail_window(root, columns, values, meta, tipo_test="PERFORMANCE"):
    test_index = TEST_INDEX_MAP.get((tipo_test or "").upper(), 0)

    cert_num  = values[1] if len(values) > 1 else "-"
    test_date = values[4] if len(values) > 4 else "-"
    job       = values[0] if len(values) > 0 else "-"
    pump      = values[3] if len(values) > 3 else "-"

    tdms_path       = meta.get("_FilePath") if isinstance(meta, dict) else None
    acquisizione_id = meta.get("id")        if isinstance(meta, dict) else None

    state = {"tdms_path": tdms_path or "", "acquisizione_id": acquisizione_id}

    # ── Istanzia UI ──────────────────────────────────────────────────────────
    ui = CertificateUI(root, cert_num, test_date, job, pump, tipo_test)
    ui.win.withdraw()   # nasconde finché non è pronta

    try:
        import icon_helper
        icon_helper.set_window_icon(ui.win)
    except Exception:
        pass

    # ── Carica unit_system dal DB ─────────────────────────────────────────────
    try:
        from db import get_unit_system, set_unit_system
        current_system = get_unit_system(acquisizione_id) if acquisizione_id else "Metric"
    except Exception:
        current_system = "Metric"
        set_unit_system = None

    ui.unit_var.set(current_system)

    # ── Leggi TDMS in background (thread separato) ───────────────────────────
    pw = ProgressWindow(root, title="Loading Certificate...")
    pw.set(2, "Checking cache...")

    _cache_result = [None]   # lista per passare il risultato dal thread
    _cancelled    = [False]  # flag per annullare il caricamento

    def _progress(p, m):
        """Aggiorna la progress window dal thread tramite after()."""
        if _cancelled[0]:
            return
        try:
            root.after(0, lambda: pw.set(p, m))
        except Exception:
            pass

    def _load_thread():
        """Legge il TDMS in background."""
        _cache_result[0] = _build_cache(
            state["tdms_path"], test_index,
            on_progress=_progress,
            unit_system=current_system)
        if not _cancelled[0]:
            try:
                root.after(0, _on_cache_ready)
            except Exception:
                pass

    def _on_cancel():
        """Chiamato dal pulsante Cancel — annulla il caricamento."""
        _cancelled[0] = True
        pw.close()
        try:
            ui.win.destroy()
        except Exception:
            pass

    pw.set_cancel_callback(_on_cancel)

    def _on_cache_ready():
        """Chiamata dal thread UI quando _load_thread ha finito."""
        nonlocal cache
        cache = _cache_result[0] or {}

        # ── Visibilita' tab curve in base al tipo di test ──────────────────
        is_npsh        = (test_index == 1)
        is_performance = (test_index == 0)

        def _set_tab(tab, visible: bool):
            try:
                if visible:
                    ui.nb.add(tab)
                else:
                    ui.nb.hide(tab)
            except Exception:
                pass

        _set_tab(ui.tab_curva, is_performance)
        _set_tab(ui.tab_npsh,  is_npsh)

        def _render_curva(tdms_p: str):
            if not is_performance:
                return
            for w in ui.tab_curva.winfo_children():
                w.destroy()
            if tdms_p and os.path.exists(tdms_p):
                try:
                    from curve_logic import render_curve_tab
                    render_curve_tab(ui.tab_curva, tdms_p,
                                     acquisizione_id=acquisizione_id,
                                     cache=cache)
                except Exception as e:
                    tk.Label(ui.tab_curva,
                             text=f"Curva non disponibile: {e}",
                             bg=BG_APP, justify="left").pack(
                                 anchor="w", padx=12, pady=12)

        def _render_npsh_curva(tdms_p: str):
            if not is_npsh:
                return
            for w in ui.tab_npsh.winfo_children():
                w.destroy()
            if tdms_p and os.path.exists(tdms_p):
                try:
                    from npsh_logic import render_npsh_tab
                    render_npsh_tab(ui.tab_npsh, tdms_p,
                                    acquisizione_id=acquisizione_id,
                                    cache=cache)
                except Exception as e:
                    tk.Label(ui.tab_npsh,
                             text=f"Curva NPSH non disponibile: {e}",
                             bg=BG_APP, justify="left").pack(
                                 anchor="w", padx=12, pady=12)

        # ── Render blocchi e tabelle ───────────────────────────────────────
        pw.set(65, "Rendering blocks...")
        _render_blocks(ui, cache, current_system, job, values, acquisizione_id=acquisizione_id)
        def _refresh_curve_and_reload(_ignored=None):
            """Rigenera la curva — stesso processo per Performance e NPSH."""
            tdms_p = state.get("tdms_path", "")
            if is_performance:
                _curve_loaded["performance"] = False
                _render_curva(tdms_p)
                _curve_loaded["performance"] = True
            else:
                _curve_loaded["npsh"] = False
                _render_npsh_curva(tdms_p)
                _curve_loaded["npsh"] = True

        pw.set(80, "Rendering tables...")
        _render_tables(ui, cache, current_system, test_index, acquisizione_id=acquisizione_id,
                       refresh_curve=_refresh_curve_and_reload)
        pw.set(95, "Almost ready...")

        # ── Placeholder nei tab curva ──────────────────────────────────────
        def _show_curve_placeholder(tab, loading=False):
            for w in tab.winfo_children():
                w.destroy()
            frame = tk.Frame(tab, bg=BG_APP)
            frame.pack(fill=tk.BOTH, expand=True)
            if loading:
                tk.Label(frame, text="⏳  Generating curve, please wait...",
                         bg=BG_APP, fg=ACCENT,
                         font=("Segoe UI", 11)).pack(expand=True)
            else:
                tk.Label(frame, text="⏳  Please wait, curve is loading...",
                         bg=BG_APP, fg="#6b7280",
                         font=("Segoe UI", 11)).pack(expand=True)

        if is_performance:
            _show_curve_placeholder(ui.tab_curva)
        if is_npsh:
            _show_curve_placeholder(ui.tab_npsh)

        # Flag per sapere se la curva e' gia' stata generata
        _curve_loaded     = {"performance": False, "npsh": False}

        def _on_tab_changed(_event=None):
            """Genera la curva al primo click sul tab."""
            try:
                current = ui.nb.select()
                current_tab = ui.win.nametowidget(current)
            except Exception:
                return

            tdms_p = state["tdms_path"]

            if is_performance and current_tab is ui.tab_curva                     and not _curve_loaded["performance"]:
                _curve_loaded["performance"] = True
                _show_curve_placeholder(ui.tab_curva, loading=True)
                ui.win.update_idletasks()
                _render_curva(tdms_p)

            elif is_npsh and current_tab is ui.tab_npsh                     and not _curve_loaded["npsh"]:
                _curve_loaded["npsh"] = True
                _show_curve_placeholder(ui.tab_npsh, loading=True)
                ui.win.update_idletasks()
                _render_npsh_curva(tdms_p)

        ui.nb.bind("<<NotebookTabChanged>>", _on_tab_changed)

        pw.close()
        ui.win.deiconify()

        # ── Callback cambio unita' ─────────────────────────────────────────
        def on_unit_change(_e=None):
            nonlocal cache
            new_system = ui.unit_var.get()
            if acquisizione_id and set_unit_system:
                try:
                    set_unit_system(acquisizione_id, new_system)
                except Exception:
                    logger.warning("Salvataggio unit_system fallito", exc_info=True)

            # Se i dati vengono dalla cache, ricarica il sistema richiesto
            # dal JSON — nessuna riconversione runtime
            if cache.get("from_cache"):
                try:
                    import ptcache
                    new_cache = ptcache.load(
                        state["tdms_path"], test_index=test_index,
                        unit_system=new_system)
                    if new_cache:
                        cache = new_cache
                except Exception:
                    pass

            _render_blocks(ui, cache, new_system, job, values, acquisizione_id=acquisizione_id)
            _render_tables(ui, cache, new_system, test_index, acquisizione_id=acquisizione_id,
                       refresh_curve=_refresh_curve_and_reload)
            # Resetta i flag — il cambio unita' richiede di rigenerare le curve
            _curve_loaded["performance"] = False
            _curve_loaded["npsh"]        = False
            if is_performance:
                _show_curve_placeholder(ui.tab_curva)
            if is_npsh:
                _show_curve_placeholder(ui.tab_npsh)

        ui.unit_combo.bind("<<ComboboxSelected>>", on_unit_change)

    # ── Placeholder cache + lancio thread ───────────────────────────────────
    cache = {}   # sara' popolato da _on_cache_ready quando il thread finisce
    threading.Thread(target=_load_thread, daemon=True).start()

    # ── Controllo TDMS mancante ───────────────────────────────────────────────
    def _check_tdms():
        current_path = state.get("tdms_path") or ""
        if not current_path or os.path.exists(current_path):
            return
        risposta = messagebox.askyesnocancel(
            "(!) File TDMS non trovato",
            f"Il file:\n{current_path}\n\nnon esiste più.\n\n"
            "Vuoi cercarlo in un'altra posizione?\n\n"
            "- SI: Seleziona nuova posizione\n"
            "- NO: Continua senza dati\n"
            "- ANNULLA: Chiudi certificato",
        )
        if risposta is None:
            ui.win.destroy()
        elif risposta:
            new_path = find_missing_tdms(current_path)
            if new_path and update_tdms_path(acquisizione_id, new_path):
                new_meta = dict(meta) if isinstance(meta, dict) else {}
                new_meta["_FilePath"] = new_path
                ui.win.destroy()
                open_detail_window(root, columns, values, new_meta, tipo_test)

    ui.win.after_idle(_check_tdms)