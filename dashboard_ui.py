"""
dashboard_ui.py
Classe DashboardUI: costruisce tutti i widget della dashboard.
Nessuna logica applicativa, nessun import da db/tdms/pdf.
"""
import tkinter as tk
from tkinter import ttk

# ── PALETTE ──────────────────────────────────────────────────────────────────
ACCENT       = "#9a3412"   # arancione scuro — header, btn primari
ACCENT_MID   = "#c2410c"   # tono medio — separatore, status bar
ACCENT_LIGHT = "#fed7aa"   # arancione chiaro — testi secondari header
BG_APP       = "#f4f5f7"   # sfondo finestra
BG_WHITE     = "#ffffff"   # card / toolbar / treeview
BG_THEAD     = "#f8f9fb"   # sfondo header treeview
BORDER       = "#e2e5ea"   # bordi sottili
TEXT_MAIN    = "#111827"
TEXT_SEC     = "#6b7280"
TEXT_WHITE   = "#ffffff"

# Colori righe per stato
TAG_STYLES = {
    "tag_approved":  {"background": "#dcfce7", "foreground": "#166534"},
    "tag_checked":   {"background": "#fff3e0", "foreground": "#7b4400"},
    "tag_unchecked": {"background": "#ffffff",  "foreground": "#374151"},
    "tag_rejected":  {"background": "#fee2e2", "foreground": "#991b1b"},
    "tag_inactive":  {"background": "#f3f4f6", "foreground": "#9ca3af"},
}

COLUMNS = (
    "JOB", "TEST N°", "SERIAL N°", "PUMP TYPE",
    "DATE", "STATUS", "DECISION DATE", "DECIDED BY", "TEST TYPE",
)

COL_WEIGHTS = {
    "JOB": 1.0, "TEST N°": 1.0, "SERIAL N°": 1.0,
    "PUMP TYPE": 1.4, "DATE": 0.9, "STATUS": 0.9,
    "DECISION DATE": 1.2, "DECIDED BY": 1.4, "TEST TYPE": 1.1,
}


class DashboardUI:
    """
    Costruisce l'intera UI della dashboard.
    I widget pubblici vengono usati da DashboardLogic per agganciare
    callbacks e aggiornare lo stato.

    Attributi pubblici:
        root          — finestra principale (Tk o Toplevel)
        tree          — ttk.Treeview
        status_var    — tk.StringVar della status bar
        btn_open_cert, btn_note, btn_pdf_preview
        btn_load_tdms, btn_unload_tdms, btn_verify_tdms
        stato_combo   — ttk.Combobox inline per cambio stato
    """

    def __init__(self, parent_root, username: str, ruolo: str,
                 folder_path: str, stato_values: tuple, db_path: str = ""):

        # ── Finestra ─────────────────────────────────────────────────────────
        if parent_root:
            self.root = tk.Toplevel(parent_root)
        else:
            self.root = tk.Tk()

        self.root.title("PT2025 — Dashboard Collaudi")
        self.root.geometry("1500x680")
        self.root.minsize(1100, 560)
        self.root.configure(bg=BG_APP)

        # ── Stile ttk ────────────────────────────────────────────────────────
        self._setup_styles()

        # ── Sezioni UI ───────────────────────────────────────────────────────
        self._build_header(username, ruolo, db_path)
        self._build_toolbar()
        self._build_body()
        self._build_statusbar()

        # ── Combobox inline stato (posizionato sulla treeview) ───────────────
        self.stato_combo = ttk.Combobox(
            self.tree, values=stato_values, state="readonly"
        )
        self.stato_combo.place_forget()

    # ─────────────────────────────────────────────────────────────────────────
    # STILI TTK
    # ─────────────────────────────────────────────────────────────────────────
    def _setup_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("PT.Treeview",
            background=BG_WHITE, foreground=TEXT_MAIN,
            rowheight=28, fieldbackground=BG_WHITE,
            font=("Segoe UI", 10), borderwidth=0, relief="flat",
        )
        style.configure("PT.Treeview.Heading",
            background=BG_THEAD, foreground=TEXT_SEC,
            font=("Segoe UI", 9, "bold"),
            relief="flat", borderwidth=0, padding=(8, 7),
        )
        style.map("PT.Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", TEXT_WHITE)],
        )
        style.map("PT.Treeview.Heading",
            background=[("active", BORDER)],
            relief=[("active", "flat")],
        )
        style.configure("Vertical.TScrollbar",
            background=BG_APP, troughcolor=BG_WHITE,
            borderwidth=0, arrowsize=12,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # HEADER
    # ─────────────────────────────────────────────────────────────────────────
    def _build_header(self, username: str, ruolo: str, db_path: str):
        hdr = tk.Frame(self.root, bg=ACCENT, height=52)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        # Logo mark
        tk.Label(hdr, text=" PT ", bg=ACCENT_MID, fg=TEXT_WHITE,
                 font=("Segoe UI", 11, "bold")).pack(
                     side=tk.LEFT, padx=(18, 0), pady=11)

        tk.Label(hdr, text="PT2025", bg=ACCENT, fg=TEXT_WHITE,
                 font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT, padx=(10, 0))
        tk.Label(hdr, text="· Pump Test System", bg=ACCENT,
                 fg=ACCENT_LIGHT, font=("Segoe UI", 10)).pack(
                     side=tk.LEFT, padx=(4, 0))

        # Destra: utente e cartella
        tk.Label(hdr, text=f"{username}  |  {ruolo}", bg=ACCENT,
                 fg="#fde8d0", font=("Segoe UI", 10)).pack(
                     side=tk.RIGHT, padx=(0, 20))

        import os
        db_name = os.path.basename(db_path) if db_path else ""
        if db_name:
            tk.Label(hdr, text=f"Database:  {db_name}", bg=ACCENT,
                     fg="#fdba74", font=("Segoe UI", 9)).pack(
                         side=tk.RIGHT, padx=(20, 8))

        # Linea separatrice
        tk.Frame(self.root, bg=ACCENT_MID, height=1).pack(fill=tk.X)

    # ─────────────────────────────────────────────────────────────────────────
    # TOOLBAR
    # ─────────────────────────────────────────────────────────────────────────
    def _build_toolbar(self):
        toolbar = tk.Frame(self.root, bg=BG_WHITE, height=46)
        toolbar.pack(fill=tk.X)
        toolbar.pack_propagate(False)

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)

        _B = dict(relief="flat", bd=0, cursor="hand2",
                  font=("Segoe UI", 10), padx=12, pady=4)

        # Colori originali per ogni pulsante (usati da set_btn_state)
        self._btn_colors = {
            "open_cert":   (ACCENT,    TEXT_WHITE),
            "note":        (ACCENT,    TEXT_WHITE),
            "pdf_preview": (ACCENT,    TEXT_WHITE),
            "load_tdms":   ("#166534", TEXT_WHITE),
            "unload_tdms": ("#92400e", TEXT_WHITE),
            "verify_tdms": ("#f9a825", "#1a1a1a"),
        }

        # Sinistra
        fl = tk.Frame(toolbar, bg=BG_WHITE)
        fl.pack(side=tk.LEFT, padx=14, pady=7)

        self.btn_open_cert = tk.Button(fl, text="Apri certificato",
                                       bg=ACCENT, fg=TEXT_WHITE, **_B)
        self.btn_open_cert.pack(side=tk.LEFT, padx=(0, 5))

        self.btn_note = tk.Button(fl, text="Note",
                                  bg=ACCENT, fg=TEXT_WHITE, **_B)
        self.btn_note.pack(side=tk.LEFT, padx=(0, 5))

        self.btn_pdf_preview = tk.Button(fl, text="Export PDF",
                                         bg=ACCENT, fg=TEXT_WHITE, **_B)
        self.btn_pdf_preview.pack(side=tk.LEFT)

        # Destra
        fr = tk.Frame(toolbar, bg=BG_WHITE)
        fr.pack(side=tk.RIGHT, padx=14, pady=7)

        self.btn_load_tdms = tk.Button(fr, text="Load TDMS",
                                       bg="#166534", fg=TEXT_WHITE, **_B)
        self.btn_load_tdms.pack(side=tk.RIGHT, padx=5)

        self.btn_unload_tdms = tk.Button(fr, text="Unload TDMS",
                                         bg="#92400e", fg=TEXT_WHITE, **_B)
        self.btn_unload_tdms.pack(side=tk.RIGHT, padx=5)

        self.btn_verify_tdms = tk.Button(fr, text="Verifica TDMS",
                                         bg="#f9a825", fg="#1a1a1a", **_B)
        self.btn_verify_tdms.pack(side=tk.RIGHT, padx=5)

        # Disabilita i pulsanti che richiedono selezione
        for key in ("open_cert", "note", "pdf_preview", "unload_tdms"):
            self.set_btn_state(key, False)

    # ─────────────────────────────────────────────────────────────────────────
    # BODY — card con treeview
    # ─────────────────────────────────────────────────────────────────────────
    def _build_body(self):
        body = tk.Frame(self.root, bg=BG_APP)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        card = tk.Frame(body, bg=BG_WHITE,
                        highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True)

        # Card header
        card_hdr = tk.Frame(card, bg=BG_WHITE)
        card_hdr.pack(fill=tk.X, padx=16, pady=(10, 0))

        tk.Label(card_hdr, text="Collaudi", bg=BG_WHITE,
                 fg=TEXT_MAIN, font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        self._lbl_count = tk.Label(card_hdr, text="", bg=BG_WHITE,
                                   fg=TEXT_SEC, font=("Segoe UI", 9))
        self._lbl_count.pack(side=tk.LEFT, padx=(8, 0))

        tk.Frame(card, bg=BORDER, height=1).pack(fill=tk.X, pady=(8, 0))

        # Treeview
        tree_frame = tk.Frame(card, bg=BG_WHITE)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(tree_frame, columns=COLUMNS,
                                 show="headings", style="PT.Treeview")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                             command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        total_w = sum(COL_WEIGHTS.values())
        for col in COLUMNS:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100, anchor="w",
                             stretch=True, minwidth=70)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # Tag colori stato
        for tag, kw in TAG_STYLES.items():
            self.tree.tag_configure(tag, **kw)

        # Autoresize colonne
        def _autosize(_e=None):
            self.tree.update_idletasks()
            avail = max(self.tree.winfo_width() - 20, 400)
            for col in COLUMNS:
                w = int(avail * COL_WEIGHTS[col] / total_w)
                minw = 120 if col in ("TIPO POMPA", "NOME APPROVATORE") else 80
                self.tree.column(col, width=max(w, minw))

        self.tree.bind("<Configure>", _autosize)
        self.root.after(100, _autosize)

    # ─────────────────────────────────────────────────────────────────────────
    # STATUS BAR
    # ─────────────────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)

        bar = tk.Frame(self.root, bg=BG_WHITE, height=28)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        self.status_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.status_var,
                 bg=BG_WHITE, fg=TEXT_SEC,
                 font=("Segoe UI", 9), anchor="w").pack(
                     side=tk.LEFT, padx=16, fill=tk.Y)

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS PUBBLICI
    # ─────────────────────────────────────────────────────────────────────────
    def set_btn_state(self, key: str, enabled: bool):
        """
        Abilita o disabilita un pulsante cambiando anche il colore di sfondo.
        enabled=True  → colore originale, cliccabile
        enabled=False → grigio #b0b0b0, testo bianco, non cliccabile
        """
        btn_map = {
            "open_cert":   self.btn_open_cert,
            "note":        self.btn_note,
            "pdf_preview": self.btn_pdf_preview,
            "load_tdms":   self.btn_load_tdms,
            "unload_tdms": self.btn_unload_tdms,
            "verify_tdms": self.btn_verify_tdms,
        }
        btn = btn_map.get(key)
        if not btn:
            return
        if enabled:
            orig_bg, orig_fg = self._btn_colors.get(key, ("#cccccc", "#ffffff"))
            btn.config(state="normal", bg=orig_bg, fg=orig_fg,
                       cursor="hand2")
        else:
            btn.config(state="disabled", bg="#b0b0b0", fg="#ffffff",
                       disabledforeground="#ffffff", cursor="")

    def set_record_count(self, n: int):
        self._lbl_count.config(text=f"{n} record")

    def set_status(self, msg: str):
        self.root.after(0, lambda: self.status_var.set(msg))