"""
certificate_ui.py
Classe CertificateUI: costruisce tutti i widget del certificato.
Nessuna logica applicativa, nessun import da db/tdms/pdf.
"""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# ── PALETTE (stessa di dashboard_ui.py) ──────────────────────────────────────
ACCENT       = "#9a3412"
ACCENT_MID   = "#c2410c"
ACCENT_LIGHT = "#fed7aa"
BG_APP       = "#f4f5f7"
BG_WHITE     = "#ffffff"
BG_THEAD     = "#f8f9fb"
BORDER       = "#e2e5ea"
TEXT_MAIN    = "#111827"
TEXT_SEC     = "#6b7280"
TEXT_WHITE   = "#ffffff"


def setup_cert_styles(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure("TNotebook",
        background=BG_APP, borderwidth=0, tabmargins=0)
    style.configure("TNotebook.Tab",
        background="#e2e5ea", foreground=TEXT_SEC,
        font=("Segoe UI", 10), padding=(14, 6), borderwidth=0)
    style.map("TNotebook.Tab",
        background=[("selected", BG_WHITE)],
        foreground=[("selected", ACCENT)],
        expand=[("selected", [1, 1, 1, 0])],
    )
    style.configure("Cert.Treeview",
        background=BG_WHITE, foreground=TEXT_MAIN,
        rowheight=22, fieldbackground=BG_WHITE,
        font=("Segoe UI", 9), borderwidth=0,
    )
    style.configure("Cert.Treeview.Heading",
        background=BG_THEAD, foreground=TEXT_SEC,
        font=("Segoe UI", 8, "bold"),
        relief="flat", borderwidth=0, padding=(6, 5),
    )
    style.map("Cert.Treeview",
        background=[("selected", ACCENT)],
        foreground=[("selected", TEXT_WHITE)],
    )
    style.map("Cert.Treeview.Heading",
        background=[("active", BORDER)],
        relief=[("active", "flat")],
    )


# ── HELPERS UI ────────────────────────────────────────────────────────────────

def kv_row(parent, label, value="-"):
    """Riga key-value con sfondo alternato gestito dal chiamante."""
    row = tk.Frame(parent, bg=parent.cget("bg"))
    row.pack(fill="x")
    tk.Label(row, text=label, width=22, anchor="w",
             bg=parent.cget("bg"), fg=TEXT_SEC,
             font=("Segoe UI", 9)).pack(side="left", padx=(8, 0), pady=3)
    tk.Frame(row, bg=BORDER, width=1).pack(side="left", fill="y", pady=2)
    tk.Label(row, text=value if value else "-", anchor="w",
             bg=parent.cget("bg"), fg=TEXT_MAIN,
             font=("Segoe UI", 9, "bold"),
             padx=8).pack(side="left", fill="x", expand=True)
    return row


def make_block(parent, title, rows):
    """
    Crea un blocco key-value con titolo arancione.
    Sostituisce LabelFrame con header colorato.
    """
    outer = tk.Frame(parent, bg=BORDER)

    tk.Label(outer, text=title, bg=ACCENT, fg=TEXT_WHITE,
             font=("Segoe UI", 9, "bold"),
             anchor="w", padx=10, pady=5).pack(fill=tk.X)

    inner = tk.Frame(outer, bg=BG_WHITE)
    inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=(0, 1))

    for i, (label, value) in enumerate(rows):
        row_bg = BG_WHITE if i % 2 == 0 else "#fafafa"
        row = tk.Frame(inner, bg=row_bg)
        row.pack(fill=tk.X)
        tk.Label(row, text=label, bg=row_bg, fg=TEXT_SEC,
                 font=("Segoe UI", 9), width=18, anchor="w",
                 padx=8, pady=3).pack(side=tk.LEFT)
        tk.Frame(row, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, pady=2)
        tk.Label(row, text=value if value else "-", bg=row_bg, fg=TEXT_MAIN,
                 font=("Segoe UI", 9, "bold"),
                 anchor="w", padx=8).pack(side=tk.LEFT, fill=tk.X, expand=True)
        if i < len(rows) - 1:
            tk.Frame(inner, bg="#f3f4f6", height=1).pack(fill=tk.X)

    return outer


def measure_title(widget, text: str) -> int:
    try:
        style = ttk.Style()
        font_name = style.lookup("Treeview.Heading", "font") or "TkDefaultFont"
    except Exception:
        font_name = "TkDefaultFont"
    fnt = tkfont.nametofont(font_name)
    return fnt.measure(text if text else " ") + 16


def spread_even_in_tv(tv, cols, minwidths, total_target, *, stretch=False):
    if not cols:
        mw = max(minwidths[0], total_target)
        tv.column("-", width=mw, minwidth=minwidths[0],
                  stretch=stretch, anchor="center")
        return
    base_sum = sum(minwidths)
    extra = max(0, total_target - base_sum)
    n = len(cols)
    add_each = extra // n
    rem = extra % n
    for i, (c, wmin) in enumerate(zip(cols, minwidths)):
        w = wmin + add_each + (1 if i < rem else 0)
        tv.column(c, width=w, minwidth=wmin, stretch=stretch, anchor="center")


# ── CLASSE PRINCIPALE ─────────────────────────────────────────────────────────

class CertificateUI:
    """
    Costruisce l'intera UI del certificato.

    Attributi pubblici esposti alla logica:
        win           — tk.Toplevel
        nb            — ttk.Notebook
        tab_cert      — frame tab Certificato
        tab_curva     — frame tab Curva
        tab_npsh      — frame tab NPSH Curve (visibile solo per test NPSH)
        blocks        — frame container per i tre blocchi KV
        tables_row    — frame container per le tre tabelle
        unit_var      — tk.StringVar (Metric / US)
        unit_combo    — ttk.Combobox
    """

    def __init__(self, root, cert_num: str, test_date: str,
                 job: str, pump: str, tipo_test: str):

        self.win = tk.Toplevel(root)
        self.win.title("Test Certificate")
        self.win.minsize(400, 900)
        self.win.configure(bg=BG_APP)

        setup_cert_styles(self.win)

        self._build_header_bar(job, pump, tipo_test)
        self._build_notebook()
        self._build_cert_tab(cert_num, test_date, tipo_test)

    # ─────────────────────────────────────────────────────────────────────────
    # STRISCIA HEADER (arancione, stile dashboard)
    # ─────────────────────────────────────────────────────────────────────────
    def _build_header_bar(self, job: str, pump: str, tipo_test: str):
        hdr = tk.Frame(self.win, bg=ACCENT, height=46)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        tk.Label(hdr, text=" PT ", bg=ACCENT_MID, fg=TEXT_WHITE,
                 font=("Segoe UI", 10, "bold")).pack(
                     side=tk.LEFT, padx=(16, 0), pady=9)
        tk.Label(hdr, text="Test Certificate", bg=ACCENT, fg=TEXT_WHITE,
                 font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT, padx=(10, 0))
        tk.Label(hdr, text=f"· {job}  /  {pump}  /  {tipo_test}",
                 bg=ACCENT, fg=ACCENT_LIGHT,
                 font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(6, 0))

        tk.Frame(self.win, bg=ACCENT_MID, height=1).pack(fill=tk.X)

    # ─────────────────────────────────────────────────────────────────────────
    # NOTEBOOK
    # ─────────────────────────────────────────────────────────────────────────
    def _build_notebook(self):
        self.nb = ttk.Notebook(self.win)
        self.nb.pack(fill=tk.BOTH, expand=True)

        self.tab_cert  = tk.Frame(self.nb, bg=BG_APP)
        self.tab_curva = tk.Frame(self.nb, bg=BG_APP)
        self.tab_npsh  = tk.Frame(self.nb, bg=BG_APP)
        self.nb.add(self.tab_cert,  text="  Certificate  ")
        self.nb.add(self.tab_curva, text="  Performance Curve  ")
        # tab NPSH aggiunta ma nascosta di default; abilitata da certificate_logic
        # solo quando il tipo di test e' NPSH
        self.nb.add(self.tab_npsh,  text="  NPSH Curve  ")
        self.nb.hide(self.tab_npsh)

    # ─────────────────────────────────────────────────────────────────────────
    # TAB CERTIFICATO
    # ─────────────────────────────────────────────────────────────────────────
    def _build_cert_tab(self, cert_num: str, test_date: str, tipo_test: str):
        tab = self.tab_cert
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        # ── Sub-header bianco ────────────────────────────────────────────────
        sub_hdr = tk.Frame(tab, bg=BG_WHITE,
                           highlightbackground=BORDER, highlightthickness=1)
        sub_hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 0))

        left = tk.Frame(sub_hdr, bg=BG_WHITE)
        left.pack(side=tk.LEFT, padx=16, pady=12)

        tk.Label(left, text="TEST CERTIFICATE", bg=BG_WHITE, fg=TEXT_MAIN,
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Frame(left, bg=ACCENT, height=3, width=52).pack(anchor="w", pady=(4, 0))
        tk.Label(left, text=f"{tipo_test}",
                 bg=BG_WHITE, fg=TEXT_SEC,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 0))

        right = tk.Frame(sub_hdr, bg=BG_WHITE)
        right.pack(side=tk.RIGHT, padx=16, pady=12)

        def _meta_row(lbl, val):
            f = tk.Frame(right, bg=BG_WHITE)
            f.pack(anchor="e", pady=1)
            tk.Label(f, text=lbl, bg=BG_WHITE, fg=TEXT_SEC,
                     font=("Segoe UI", 8), width=12, anchor="e").pack(side=tk.LEFT)
            tk.Label(f, text=val, bg=BG_WHITE, fg=TEXT_MAIN,
                     font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(4, 0))

        _meta_row("N. Cert.:", cert_num)
        _meta_row("Test Date:", test_date)

        # Combo unità
        unit_f = tk.Frame(right, bg=BG_WHITE)
        unit_f.pack(anchor="e", pady=(4, 0))
        tk.Label(unit_f, text="U.M. System:", bg=BG_WHITE, fg=TEXT_SEC,
                 font=("Segoe UI", 8), anchor="e").pack(side=tk.LEFT)
        self.unit_var = tk.StringVar(value="Metric")
        self.unit_combo = ttk.Combobox(
            unit_f, textvariable=self.unit_var,
            values=["Metric", "US"], state="readonly",
            width=8, font=("Segoe UI", 9))
        self.unit_combo.pack(side=tk.LEFT, padx=(6, 0))

        # ── Body ─────────────────────────────────────────────────────────────
        body = tk.Frame(tab, bg=BG_APP)
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=10)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        # Container blocchi
        self.blocks = tk.Frame(body, bg=BG_APP)
        self.blocks.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.blocks.columnconfigure(0, weight=1)
        self.blocks.columnconfigure(1, weight=1)
        self.blocks.columnconfigure(2, weight=1)

        # Container tabelle
        self.tables_row = tk.Frame(body, bg=BG_APP)
        self.tables_row.grid(row=1, column=0, sticky="nsew")
        self.tables_row.grid_columnconfigure(0, weight=1)
        self.tables_row.grid_columnconfigure(1, weight=1)
        self.tables_row.grid_columnconfigure(2, weight=1)
        self.tables_row.grid_rowconfigure(0, weight=1)