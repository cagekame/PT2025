"""
npsh_ui.py
Classe NpshUI: costruisce il layout della scheda NPSH Curve.
Stesso pattern di CurveUI — nessuna logica matplotlib, nessun import da db/tdms.
"""
import tkinter as tk
from tkinter import ttk

from certificate_ui import (
    make_block,
    ACCENT, ACCENT_MID, ACCENT_LIGHT,
    BG_APP, BG_WHITE, BORDER,
    TEXT_MAIN, TEXT_SEC, TEXT_WHITE,
)


class NpshUI:
    """
    Costruisce il layout della scheda NPSH Curve.

    Attributi pubblici esposti alla logica:
        frame             — frame root (il parent passato dall'esterno)
        left_col          — colonna sinistra (blocchi KV + controlli)
        right_frame       — frame dove viene embeddato il canvas matplotlib
        scroll_canvas     — tk.Canvas con scrollbar verticale
        show_points_var   — tk.BooleanVar checkbox show points
        chk_show_points   — tk.Checkbutton
    """

    def __init__(self, parent):
        self.frame = parent
        self.frame.configure(bg=BG_APP)

        self._build_grid()
        self._build_left_col()
        self._build_right_col()

    # ─────────────────────────────────────────────────────────────────────────
    # GRIGLIA PRINCIPALE
    # ─────────────────────────────────────────────────────────────────────────
    def _build_grid(self):
        self.frame.grid_columnconfigure(0, weight=0, minsize=360)
        self.frame.grid_columnconfigure(1, weight=1)
        self.frame.grid_rowconfigure(0, weight=1)

    # ─────────────────────────────────────────────────────────────────────────
    # COLONNA SINISTRA
    # ─────────────────────────────────────────────────────────────────────────
    def _build_left_col(self):
        self.left_col = tk.Frame(self.frame, bg=BG_APP)
        self.left_col.grid(row=0, column=0, sticky="nsew",
                           padx=(12, 6), pady=12)
        self.left_col.grid_columnconfigure(0, weight=1)

        # Blocchi KV — popolati dalla logica via populate_kv_blocks()
        self._block_contractual_frame = tk.Frame(self.left_col, bg=BG_APP)
        self._block_contractual_frame.grid(row=0, column=0, sticky="ew")

        self._block_rated_frame = tk.Frame(self.left_col, bg=BG_APP)
        self._block_rated_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        # Checkbox show points
        self._build_show_points()

    def _build_show_points(self):
        outer = tk.Frame(self.left_col, bg=BG_WHITE,
                         highlightbackground=BORDER, highlightthickness=1)
        outer.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        inner = tk.Frame(outer, bg=BG_WHITE)
        inner.pack(fill=tk.X, padx=8, pady=6)

        self.show_points_var = tk.BooleanVar(value=True)
        self.chk_show_points = tk.Checkbutton(
            inner,
            text="Show curve points",
            variable=self.show_points_var,
            bg=BG_WHITE, activebackground=BG_WHITE,
            fg=TEXT_MAIN, font=("Segoe UI", 9),
            state="disabled",
            cursor="hand2",
        )
        self.chk_show_points.pack(anchor="w")

    # ─────────────────────────────────────────────────────────────────────────
    # COLONNA DESTRA — canvas matplotlib scrollabile
    # ─────────────────────────────────────────────────────────────────────────
    def _build_right_col(self):
        card = tk.Frame(self.frame, bg=BORDER)
        card.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=0)
        card.grid_rowconfigure(1, weight=0)
        card.grid_rowconfigure(2, weight=1)

        tk.Label(card, text="NPSH Curve", bg="#f8f9fb", fg=TEXT_MAIN,
                 font=("Segoe UI", 10, "bold"),
                 anchor="w", padx=12, pady=7).grid(
                     row=0, column=0, columnspan=2, sticky="ew")
        tk.Frame(card, bg=BORDER, height=1).grid(
            row=1, column=0, columnspan=2, sticky="ew")

        inner = tk.Frame(card, bg=BG_WHITE)
        inner.grid(row=2, column=0, sticky="nsew", padx=1, pady=(0, 1))
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_rowconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        self.scroll_canvas = tk.Canvas(inner,
                                       highlightthickness=0, bg=BG_WHITE)
        vbar = ttk.Scrollbar(inner, orient="vertical",
                              command=self.scroll_canvas.yview)
        self.scroll_canvas.configure(yscrollcommand=vbar.set)
        self.scroll_canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")

        self.right_frame = tk.Frame(self.scroll_canvas, bg=BG_WHITE)
        self._win_id = self.scroll_canvas.create_window(
            (0, 0), window=self.right_frame, anchor="nw")

        self.right_frame.bind("<Configure>",
            lambda _e: self.scroll_canvas.configure(
                scrollregion=self.scroll_canvas.bbox("all")))
        self.scroll_canvas.bind("<Configure>",
            lambda e: self.scroll_canvas.itemconfig(
                self._win_id, width=e.width))

        def _on_wheel(event):
            if event.num == 4:
                self.scroll_canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.scroll_canvas.yview_scroll(1, "units")
            else:
                self.scroll_canvas.yview_scroll(
                    int(-event.delta / 120), "units")

        def _bind(_e):
            self.scroll_canvas.bind_all("<MouseWheel>", _on_wheel)
            self.scroll_canvas.bind_all("<Button-4>",   _on_wheel)
            self.scroll_canvas.bind_all("<Button-5>",   _on_wheel)

        def _unbind(_e):
            self.scroll_canvas.unbind_all("<MouseWheel>")
            self.scroll_canvas.unbind_all("<Button-4>")
            self.scroll_canvas.unbind_all("<Button-5>")

        self.scroll_canvas.bind("<Enter>", _bind)
        self.scroll_canvas.bind("<Leave>", _unbind)
        self.right_frame.bind("<Enter>", _bind)
        self.right_frame.bind("<Leave>", _unbind)

    # ─────────────────────────────────────────────────────────────────────────
    # HELPER PUBBLICO — popola i blocchi KV
    # ─────────────────────────────────────────────────────────────────────────
    def populate_kv_blocks(self, contractual_rows: list, rated_rows: list):
        """
        Chiamato dalla logica dopo aver letto i dati TDMS.
        contractual_rows / rated_rows: lista di (label, value).
        """
        for w in self._block_contractual_frame.winfo_children():
            w.destroy()
        for w in self._block_rated_frame.winfo_children():
            w.destroy()

        b1 = make_block(self._block_contractual_frame,
                        "CONTRACTUAL DATA", contractual_rows)
        b1.pack(fill=tk.X)

        b2 = make_block(self._block_rated_frame,
                        "RATED POINT", rated_rows)
        b2.pack(fill=tk.X)