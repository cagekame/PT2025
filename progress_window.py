"""
progress_window.py
Finestra di progresso standalone per operazioni lunghe.
Supporta pulsante Cancel tramite set_cancel_callback().
"""
import tkinter as tk
from tkinter import ttk

ACCENT      = "#9a3412"
ACCENT_MID  = "#c2410c"
BG_APP      = "#f4f5f7"
BORDER      = "#e2e5ea"
TEXT_MAIN   = "#111827"
TEXT_SEC    = "#6b7280"
TEXT_WHITE  = "#ffffff"


class ProgressWindow:
    """
    Finestra di progresso modale centrata sul parent.

    Metodi pubblici:
        set(percent, message)          — aggiorna barra e testo
        set_cancel_callback(callback)  — abilita pulsante Cancel
        close()                        — chiude la finestra
    """

    def __init__(self, parent, title: str = "Loading..."):
        self._parent          = parent
        self._closed          = False
        self._dots            = 0
        self._after_id        = None
        self._cancel_callback = None

        self._win = tk.Toplevel(parent)
        self._win.title(title)
        self._win.resizable(False, False)
        self._win.configure(bg=BG_APP)
        self._win.transient(parent)
        self._win.grab_set()
        self._win.protocol("WM_DELETE_WINDOW", self._on_cancel)

        try:
            import icon_helper
            icon_helper.set_window_icon(self._win)
        except Exception:
            pass

        # Header
        hdr = tk.Frame(self._win, bg=ACCENT, height=46)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(hdr, text=" PT ", bg=ACCENT_MID, fg=TEXT_WHITE,
                 font=("Segoe UI", 10, "bold")).pack(
                     side=tk.LEFT, padx=(16, 0), pady=9)
        tk.Label(hdr, text=title, bg=ACCENT, fg=TEXT_WHITE,
                 font=("Segoe UI", 13, "bold")).pack(
                     side=tk.LEFT, padx=(10, 0))
        tk.Frame(self._win, bg=ACCENT_MID, height=1).pack(fill=tk.X)

        body = tk.Frame(self._win, bg=BG_APP)
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        # Messaggio
        self._msg_var = tk.StringVar(value="Opening TDMS file")
        tk.Label(body, textvariable=self._msg_var,
                 bg=BG_APP, fg=TEXT_MAIN,
                 font=("Segoe UI", 10), anchor="w").pack(fill=tk.X, pady=(0, 2))

        # Puntini animati
        self._dots_var = tk.StringVar(value=".")
        tk.Label(body, textvariable=self._dots_var,
                 bg=BG_APP, fg=ACCENT,
                 font=("Segoe UI", 14, "bold"), anchor="w").pack(fill=tk.X, pady=(0, 8))

        # Barra progresso
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Progress.Horizontal.TProgressbar",
                         troughcolor=BORDER, background=ACCENT,
                         bordercolor=BORDER, lightcolor=ACCENT,
                         darkcolor=ACCENT_MID)

        self._bar = ttk.Progressbar(
            body, style="Progress.Horizontal.TProgressbar",
            orient="horizontal", length=340,
            mode="determinate", maximum=100, value=0)
        self._bar.pack(fill=tk.X, pady=(0, 6))

        self._pct_var = tk.StringVar(value="0%")
        tk.Label(body, textvariable=self._pct_var,
                 bg=BG_APP, fg=TEXT_SEC,
                 font=("Segoe UI", 9), anchor="e").pack(fill=tk.X)

        # Footer con pulsante Cancel — sempre visibile, disabilitato finche'
        # non viene chiamato set_cancel_callback()
        self._footer = tk.Frame(self._win, bg=BG_APP)
        self._footer.pack(fill=tk.X, padx=24, pady=(0, 16))

        self._btn_cancel = tk.Button(
            self._footer, text="Cancel",
            bg="#d1d5db", fg="#9ca3af",
            font=("Segoe UI", 9), relief="flat",
            cursor="arrow", padx=14, pady=6,
            state="disabled",
            command=self._on_cancel)
        self._btn_cancel.pack(side=tk.RIGHT)

        # Centra sul parent
        self._win.update_idletasks()
        w = self._win.winfo_reqwidth()
        h = self._win.winfo_reqheight()
        try:
            root = parent.winfo_toplevel()
            px = root.winfo_rootx() + root.winfo_width()  // 2 - w // 2
            py = root.winfo_rooty() + root.winfo_height() // 2 - h // 2
        except Exception:
            px = parent.winfo_rootx() + parent.winfo_width()  // 2 - w // 2
            py = parent.winfo_rooty() + parent.winfo_height() // 2 - h // 2
        self._win.geometry(f"{w}x{h}+{px}+{py}")
        self._win.update()

        # Avvia animazione puntini
        self._animate()

    def _animate(self):
        if self._closed:
            return
        self._dots = (self._dots + 1) % 4
        self._dots_var.set("." * max(1, self._dots))
        self._after_id = self._win.after(400, self._animate)

    def _on_cancel(self):
        """Chiamato dal pulsante Cancel o dalla X della finestra."""
        if self._cancel_callback:
            self._cancel_callback()
        else:
            # Se non c'e' callback (es. certificato), ignora la X
            pass

    # ── API pubblica ──────────────────────────────────────────────────────────

    def set(self, percent: int, message: str = ""):
        """Aggiorna barra e messaggio."""
        if self._closed:
            return
        percent = max(0, min(100, int(percent)))
        try:
            self._bar["value"] = percent
            self._pct_var.set(f"{percent}%")
            if message:
                self._msg_var.set(message)
        except Exception:
            pass

    def set_cancel_callback(self, callback):
        """
        Abilita il pulsante Cancel e registra il callback da chiamare.
        """
        self._cancel_callback = callback
        try:
            self._btn_cancel.config(
                state="normal",
                bg="#6b7280", fg=TEXT_WHITE,
                cursor="hand2")
            self._win.update_idletasks()
        except Exception:
            pass

    def close(self):
        """Chiude la finestra."""
        if self._closed:
            return
        self._closed = True
        if self._after_id:
            try:
                self._win.after_cancel(self._after_id)
            except Exception:
                pass
        try:
            self._win.grab_release()
            self._win.destroy()
        except Exception:
            pass