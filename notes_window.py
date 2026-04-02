# notes_window.py
import tkinter as tk
from tkinter import ttk, messagebox

# ── PALETTE ───────────────────────────────────────────────────────────────────
ACCENT       = "#9a3412"
ACCENT_MID   = "#c2410c"
ACCENT_LIGHT = "#fed7aa"
BG_APP       = "#f4f5f7"
BG_WHITE     = "#ffffff"
BORDER       = "#e2e5ea"
TEXT_MAIN    = "#111827"
TEXT_SEC     = "#6b7280"
TEXT_WHITE   = "#ffffff"
BTN_SAVE     = "#166534"


def open_notes_window(
    parent,
    *,
    acq_id: int,
    filename: str,
    ruolo: str,
    stato_cur: str,
    note_collaudatore_get,
    note_collaudatore_set,
    note_ingegneria_get,
    note_ingegneria_set,
):
    if acq_id is None:
        messagebox.showwarning("Errore", "ID acquisizione non valido per la gestione note.")
        return

    stato_cur = (stato_cur or "").strip()
    ruolo     = (ruolo     or "").strip()

    can_edit_coll = (ruolo == "Collaudatore" and stato_cur == "Unchecked")
    can_edit_ing  = (ruolo in ("Ingegneria", "Admin") and stato_cur == "Checked")

    # ── Finestra ──────────────────────────────────────────────────────────────
    win = tk.Toplevel(parent)
    win.title(f"Note — {filename}")
    win.geometry("920x540")
    win.minsize(760, 440)
    win.configure(bg=BG_APP)
    win.transient(parent)
    try:
        import icon_helper
        icon_helper.set_window_icon(win)
    except Exception:
        pass
    win.grab_set()

    win.columnconfigure(0, weight=1)
    win.columnconfigure(1, weight=1)
    win.rowconfigure(1, weight=1)

    # ── Header arancione ──────────────────────────────────────────────────────
    hdr = tk.Frame(win, bg=ACCENT, height=46)
    hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
    hdr.grid_propagate(False)

    tk.Label(hdr, text=" PT ", bg=ACCENT_MID, fg=TEXT_WHITE,
             font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(16, 0), pady=9)
    tk.Label(hdr, text="Note", bg=ACCENT, fg=TEXT_WHITE,
             font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT, padx=(10, 0))

    fn_display = filename if len(filename) <= 48 else f"…{filename[-48:]}"
    tk.Label(hdr, text=f"· {fn_display}", bg=ACCENT, fg=ACCENT_LIGHT,
             font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(6, 0))

    tk.Label(hdr, text=f"{stato_cur}  ·  {ruolo}", bg=ACCENT, fg=ACCENT_LIGHT,
             font=("Segoe UI", 9)).pack(side=tk.RIGHT, padx=16)

    tk.Frame(win, bg=ACCENT_MID, height=1).grid(
        row=0, column=0, columnspan=2, sticky="sew")

    # ── Pannelli note ─────────────────────────────────────────────────────────
    def make_note_box(col, title, editable):
        card = tk.Frame(win, bg=BORDER)
        card.grid(row=1, column=col,
                  padx=(12 if col == 0 else 6, 6 if col == 0 else 12),
                  pady=12, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)

        # Titolo
        hdr_bg = ACCENT if editable else "#6b7280"
        title_f = tk.Frame(card, bg=hdr_bg)
        title_f.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(title_f, text=title, bg=hdr_bg, fg=TEXT_WHITE,
                 font=("Segoe UI", 9, "bold"),
                 anchor="w", padx=10, pady=5).pack(side=tk.LEFT)
        badge = "modificabile" if editable else "sola lettura"
        badge_fg = ACCENT_LIGHT if editable else "#d1d5db"
        tk.Label(title_f, text=badge, bg=hdr_bg, fg=badge_fg,
                 font=("Segoe UI", 8), anchor="e", padx=8).pack(side=tk.RIGHT)

        # Testo
        txt_bg = BG_WHITE if editable else "#f8f9fb"
        txt = tk.Text(card, wrap="word", font=("Segoe UI", 10), undo=True,
                      bg=txt_bg, fg=TEXT_MAIN, relief="flat", bd=0,
                      padx=10, pady=8, insertbackground=ACCENT)
        txt.grid(row=1, column=0, sticky="nsew", padx=1, pady=(0, 1))

        scr = ttk.Scrollbar(card, orient="vertical", command=txt.yview)
        scr.grid(row=1, column=1, sticky="ns", pady=(0, 1))
        txt.configure(yscrollcommand=scr.set)
        return txt

    txt_coll = make_note_box(0, "Note Collaudo",   can_edit_coll)
    txt_ing  = make_note_box(1, "Note Ingegneria", can_edit_ing)

    try:
        txt_coll.insert(tk.END, note_collaudatore_get(acq_id) or "")
    except Exception as e:
        txt_coll.insert(tk.END, f"[ERRORE lettura: {e}]")

    try:
        txt_ing.insert(tk.END, note_ingegneria_get(acq_id) or "")
    except Exception as e:
        txt_ing.insert(tk.END, f"[ERRORE lettura: {e}]")

    if not can_edit_coll:
        txt_coll.config(state="disabled")
    if not can_edit_ing:
        txt_ing.config(state="disabled")

    # ── Footer ────────────────────────────────────────────────────────────────
    tk.Frame(win, bg=BORDER, height=1).grid(
        row=2, column=0, columnspan=2, sticky="ew")

    footer = tk.Frame(win, bg=BG_WHITE)
    footer.grid(row=3, column=0, columnspan=2, sticky="ew")
    footer.columnconfigure(0, weight=1)

    perm = [
        "Collaudo: MODIFICA"      if can_edit_coll else "Collaudo: sola lettura",
        "Ingegneria: MODIFICA"    if can_edit_ing  else "Ingegneria: sola lettura",
    ]
    tk.Label(footer, text="  " + "  ·  ".join(perm),
             bg=BG_WHITE, fg=TEXT_SEC,
             font=("Segoe UI", 9), anchor="w").pack(side=tk.LEFT, pady=10)

    def _btn(text, bg, cmd):
        return tk.Button(footer, text=text, bg=bg, fg=TEXT_WHITE,
                         font=("Segoe UI", 9), relief="flat", bd=0,
                         cursor="hand2", padx=14, pady=6,
                         activebackground=ACCENT_MID,
                         activeforeground=TEXT_WHITE,
                         command=cmd)

    def save(txt_widget, setter, label):
        if str(txt_widget.cget("state")) == "disabled":
            return
        try:
            setter(acq_id, txt_widget.get("1.0", tk.END).strip())
            messagebox.showinfo("Successo", f"{label} salvate.")
        except Exception as e:
            messagebox.showwarning("Errore", f"Impossibile salvare {label}:\n{e}")

    _btn("Chiudi", "#4b5563", win.destroy).pack(
        side=tk.RIGHT, padx=(8, 16), pady=8)

    if can_edit_ing:
        _btn("Salva Ingegneria", BTN_SAVE,
             lambda: save(txt_ing, note_ingegneria_set, "Note Ingegneria")
             ).pack(side=tk.RIGHT, padx=(0, 6), pady=8)

    if can_edit_coll:
        _btn("Salva Collaudo", BTN_SAVE,
             lambda: save(txt_coll, note_collaudatore_set, "Note Collaudo")
             ).pack(side=tk.RIGHT, padx=(0, 6), pady=8)