"""
dashboard_logic.py
Logica applicativa della dashboard: DB, TDMS, stato, callbacks.
Istanzia DashboardUI e aggancia tutti gli eventi.
"""
import os
import sys
import re
import threading
from datetime import date
from tkinter import filedialog, messagebox

import icon_helper
from dashboard_ui import DashboardUI, COLUMNS
from db import (
    init as db_init,
    select_all_acquisizioni,
    update_stato,
    delete_acquisizione,
    note_collaudatore_get,
    note_collaudatore_set,
    note_ingegneria_get,
    note_ingegneria_set,
)
from notes_window import open_notes_window

# ── CONFIG ────────────────────────────────────────────────────────────────────
FOLDER_PATH      = r"C:\Collaudi"
DEFAULT_USERNAME = "Admin"
DEFAULT_RUOLO    = "Admin"

STATO_VALUES = ("Unchecked", "Checked", "Approved", "Rejected", "Inactive")


# ── HELPERS INDIPENDENTI ──────────────────────────────────────────────────────

def parse_tdms_name(fname: str) -> dict | None:
    """
    Estrae metadati dal nome file TDMS.
    Formato atteso:
      DATA-REC_<commessa>_<matricola>_<YYYYMMDD>-<HHMMSS>_<00000>.tdms
    """
    pattern = re.compile(
        r"^DATA-REC_(?P<job>[^_]+)_(?P<matricola>[^_]+)"
        r"_(?P<date>\d{8})-(?P<time>\d{6})_(?P<prog>\d+)\.tdms$",
        re.IGNORECASE,
    )
    m = pattern.match(fname)
    if not m:
        return None
    d = m.group("date")
    return {
        "job":          m.group("job"),
        "matricola":    m.group("matricola"),
        "data_file":    d,
        "data_iso":     f"{d[:4]}-{d[4:6]}-{d[6:]}",
        "ora_file":     m.group("time"),
        "progressivo":  int(m.group("prog")),
    }


def ingest_one_record(rec: dict) -> None:
    """
    Inserisce uno o piu' record nel DB in base ai tipi di test presenti nel TDMS.
    Un file TDMS puo' contenere piu' tipi di test (PERFORMANCE, NPSH, RUNNING):
    viene creato un record separato per ogni tipo trovato.
    """
    from db import insert_acquisizione
    from tdms_reader import read_tdms_fields, detect_test_types

    tdms_vals  = read_tdms_fields(rec["filepath"])
    n_collaudo = tdms_vals.get("n_collaudo", "")
    tipo_pompa = tdms_vals.get("tipo_pompa", "")

    test_types = detect_test_types(rec["filepath"])
    if not test_types:
        test_types = ["PERFORMANCE"]

    for test_type in test_types:
        to_insert = {
            **rec,
            "n_collaudo": n_collaudo,
            "tipo_pompa": tipo_pompa,
            "tipo_test":  test_type,
            "stato":      "Unchecked",
        }
        insert_acquisizione(to_insert)


# ── FUNZIONE PRINCIPALE ───────────────────────────────────────────────────────

def launch_dashboard(
    folder_path: str,
    username: str,
    ruolo: str,
    parent_root=None,
    on_close_callback=None,
    db_path: str = "",
):
    db_init()

    # ── Istanzia la UI ────────────────────────────────────────────────────────
    ui = DashboardUI(
        parent_root=parent_root,
        username=username,
        ruolo=ruolo,
        folder_path=folder_path,
        stato_values=STATO_VALUES,
        db_path=db_path,
    )
    root = ui.root
    tree = ui.tree
    stato_combo = ui.stato_combo

    icon_helper.set_window_icon(root)

    def on_closing():
        root.destroy()
        if on_close_callback:
            on_close_callback()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    # Dizionario iid → metadati riga (id, _FilePath, _FileName)
    data_by_iid: dict = {}

    # ── Helpers stato ─────────────────────────────────────────────────────────

    def tag_for_status(st: str) -> str:
        s = (st or "").strip().lower()
        if s == "approved":  return "tag_approved"
        if s == "rejected":  return "tag_rejected"
        if s == "inactive":  return "tag_inactive"
        if s == "checked":   return "tag_checked"
        return "tag_unchecked"

    def _selected_state() -> str:
        sel = tree.focus()
        if not sel:
            return ""
        vals = tree.item(sel, "values")
        return vals[5] if vals and len(vals) > 5 else ""

    def get_sel_row_meta() -> dict | None:
        sel = tree.focus()
        return data_by_iid.get(sel) if sel else None

    # ── Refresh DB → Treeview ─────────────────────────────────────────────────

    def refresh_from_db():
        tree.delete(*tree.get_children())
        data_by_iid.clear()

        rows = select_all_acquisizioni()
        for idx, r in enumerate(rows, start=1):
            acq_id = r[0]
            raw_vals = r[1:10]
            values = tuple("" if v is None else v for v in raw_vals)
            iid = f"row_{idx}"
            tree.insert("", "end", iid=iid,
                        values=values,
                        tags=(tag_for_status(values[5]),))
            data_by_iid[iid] = {
                "id": acq_id,
                "_FilePath": r[11],
                "_FileName": r[12],
            }

        ui.set_record_count(len(rows))
        ui.set_status(f"Record caricati: {len(rows)}")
        on_tree_select()

    # ── Aggiornamento pulsanti alla selezione ─────────────────────────────────

    def on_tree_select(_=None):
        sel = tree.focus()
        has_sel = bool(sel)

        ui.set_btn_state("open_cert",   has_sel)
        ui.set_btn_state("note",        has_sel)
        ui.set_btn_state("unload_tdms", has_sel and ruolo == "Admin")

        stato_cur = _selected_state()
        ui.set_btn_state("pdf_preview",
                         has_sel and stato_cur in ("Approved", "Rejected"))

        # Aggiorna status bar con info riga selezionata
        if has_sel:
            vals = tree.item(sel, "values")
            if vals:
                ui.set_status(
                    f"Selezionato: {vals[1]}  —  {vals[3]}"
                    f"  ·  Stato: {vals[5]}"
                    f"  ·  {len(data_by_iid)} record"
                )
        else:
            ui.set_status(f"{len(data_by_iid)} record caricati")

    # ── Editor inline stato ───────────────────────────────────────────────────

    def on_tree_click(event):
        item   = tree.identify_row(event.y)
        col_id = tree.identify_column(event.x)

        if not item or col_id != "#6":
            stato_combo.place_forget()
            return

        bbox = tree.bbox(item, column=col_id)
        if not bbox:
            stato_combo.place_forget()
            return

        x, y, w, h = bbox
        current_values = list(tree.item(item, "values"))
        current_stato  = current_values[5] if len(current_values) > 5 else ""
        stato_combo.set(current_stato if current_stato in STATO_VALUES else "")
        stato_combo.place(x=x, y=y, width=w, height=h)

        def on_sel(_e=None):
            new_val = stato_combo.get()
            meta = data_by_iid.get(item)
            if not (meta and new_val in STATO_VALUES):
                stato_combo.place_forget()
                return

            current_stato_local = current_values[5] if len(current_values) > 5 else ""

            if new_val == current_stato_local:
                stato_combo.place_forget()
                return

            # Blocchi cambio stato non consentiti
            if new_val == "Unchecked":
                messagebox.showwarning("Cambio non consentito",
                    "Non è possibile riportare un collaudo allo stato UNCHECKED.")
                stato_combo.set(current_stato_local)
                stato_combo.place_forget()
                return

            if new_val == "Checked" and current_stato_local in ("Approved", "Rejected"):
                messagebox.showwarning("Cambio non consentito",
                    "Non è possibile riportare da APPROVED/REJECTED a CHECKED.")
                stato_combo.set(current_stato_local)
                stato_combo.place_forget()
                return

            # Controlli per ruolo
            if ruolo == "Visualizzatore":
                messagebox.showwarning("Permesso negato",
                    "Con il ruolo Visualizzatore non puoi modificare lo stato.")
                stato_combo.set(current_stato_local)
                stato_combo.place_forget()
                return

            if ruolo == "Collaudatore":
                if not (current_stato_local == "Unchecked" and new_val == "Checked"):
                    messagebox.showwarning("Permesso negato",
                        "Come collaudatore puoi solo passare lo stato da UNCHECKED a CHECKED.")
                    stato_combo.set(current_stato_local)
                    stato_combo.place_forget()
                    return
                note_coll = (note_collaudatore_get(meta["id"]) or "").strip()
                if not note_coll:
                    messagebox.showwarning("Nota mancante",
                        "Per passare lo stato a CHECKED devi prima inserire una nota (pulsante NOTE).")
                    stato_combo.set(current_stato_local)
                    stato_combo.place_forget()
                    return
                # Verifica Test Cell e Hydraulic
                try:
                    from db import get_loop_detail as _gld
                    _ld = _gld(meta["id"])
                    if not _ld.get("test_cell", "").strip():
                        messagebox.showwarning("Test Cell mancante",
                            "Per passare lo stato a CHECKED devi compilare il campo TEST CELL nel certificato.")
                        stato_combo.set(current_stato_local)
                        stato_combo.place_forget()
                        return
                    if not _ld.get("hydraulic", "").strip():
                        messagebox.showwarning("Hydraulic mancante",
                            "Per passare lo stato a CHECKED devi compilare il campo HYDRAULIC nel certificato.")
                        stato_combo.set(current_stato_local)
                        stato_combo.place_forget()
                        return
                except Exception:
                    pass

            elif ruolo == "Ingegneria":
                if not (current_stato_local == "Checked" and new_val in ("Approved", "Rejected")):
                    messagebox.showwarning("Permesso negato",
                        "Con il ruolo Ingegneria puoi cambiare stato solo da CHECKED a APPROVED o REJECTED.")
                    stato_combo.set(current_stato_local)
                    stato_combo.place_forget()
                    return
                note_ing = (note_ingegneria_get(meta["id"]) or "").strip()
                if not note_ing:
                    messagebox.showwarning("Nota mancante",
                        "Per passare lo stato a APPROVED o REJECTED devi prima inserire una nota di ingegneria.")
                    stato_combo.set(current_stato_local)
                    stato_combo.place_forget()
                    return

            elif ruolo == "Admin":
                if new_val in ("Approved", "Rejected"):
                    note_ing = (note_ingegneria_get(meta["id"]) or "").strip()
                    if not note_ing:
                        messagebox.showwarning("Nota mancante",
                            "Per passare lo stato a APPROVED o REJECTED devi prima inserire una nota di ingegneria.")
                        stato_combo.set(current_stato_local)
                        stato_combo.place_forget()
                        return

            if new_val == "Inactive" and ruolo != "Admin":
                messagebox.showwarning("Permesso negato",
                    "Solo un Admin può impostare lo stato a INACTIVE.")
                stato_combo.set(current_stato_local)
                stato_combo.place_forget()
                return

            # Aggiorna DB e UI
            change_date = date.today().isoformat()
            update_stato(meta["id"], new_val, change_date, username, ruolo)

            current_values[5] = new_val
            current_values[6] = change_date
            current_values[7] = username

            tree.item(item, values=tuple(current_values))
            tree.item(item, tags=(tag_for_status(new_val),))
            stato_combo.place_forget()
            on_tree_select()

        stato_combo.unbind("<<ComboboxSelected>>")
        stato_combo.bind("<<ComboboxSelected>>", on_sel)

    # ── Azioni pulsanti ───────────────────────────────────────────────────────

    def do_note():
        meta = get_sel_row_meta()
        if not meta:
            messagebox.showwarning("Selezione", "Seleziona una riga.")
            return
        sel  = tree.focus()
        vals = tree.item(sel, "values")
        open_notes_window(
            root,
            acq_id=meta["id"],
            filename=meta["_FileName"],
            ruolo=ruolo,
            stato_cur=vals[5] if vals and len(vals) > 5 else "",
            note_collaudatore_get=note_collaudatore_get,
            note_collaudatore_set=note_collaudatore_set,
            note_ingegneria_get=note_ingegneria_get,
            note_ingegneria_set=note_ingegneria_set,
        )

    def do_open_cert():
        meta = get_sel_row_meta()
        if not meta:
            messagebox.showwarning("Selezione", "Seleziona una riga.")
            return
        sel  = tree.focus()
        vals = tree.item(sel, "values")
        tipo_test = vals[8] if vals and len(vals) > 8 else "PERFORMANCE"
        from certificate_logic import open_detail_window
        open_detail_window(root, COLUMNS, vals, meta, tipo_test=tipo_test)

    def do_pdf_preview():
        meta = get_sel_row_meta()
        if not meta:
            messagebox.showwarning("Selezione", "Seleziona una riga.")
            return
        sel  = tree.focus()
        vals = tree.item(sel, "values")
        stato_cur = vals[5] if vals and len(vals) > 5 else ""
        if stato_cur not in ("Approved", "Rejected"):
            messagebox.showinfo("PDF non disponibile",
                "Il PDF è disponibile solo per collaudi APPROVED o REJECTED.")
            return
        change_date = vals[6] if vals and len(vals) > 6 else date.today().isoformat()
        tipo_test = vals[8] if vals and len(vals) > 8 else "PERFORMANCE"

        # Controlla ptcache prima di lanciare il thread
        _tdms_path = meta.get("_FilePath", "") if isinstance(meta, dict) else ""
        if _tdms_path:
            try:
                import ptcache as _pc
                if not _pc.exists(_tdms_path):
                    messagebox.showwarning(
                        "Cache non trovata",
                        "Il file cache (.ptcache) non esiste per questo collaudo.\n\n"
                        "Il PDF verrà generato leggendo direttamente il file TDMS — "
                        "potrebbe richiedere più tempo.\n\n"
                        "Per aggiornare la cache, aprire il certificato dalla dashboard."
                    )
                else:
                    from ptcache import PTCACHE_VERSION
                    import json
                    try:
                        with open(_pc.get_path(_tdms_path), encoding="utf-8") as _f:
                            _v = json.load(_f).get("version", 0)
                        if _v != PTCACHE_VERSION:
                            messagebox.showwarning(
                                "Cache obsoleta",
                                f"Il file cache (.ptcache) è alla versione {_v} "
                                f"(attesa {PTCACHE_VERSION}).\n\n"
                                "Il PDF verrà generato leggendo direttamente il file TDMS — "
                                "potrebbe richiedere più tempo.\n\n"
                                "Per aggiornare la cache, aprire il certificato dalla dashboard."
                            )
                    except Exception:
                        pass
            except Exception:
                pass

        # Genera PDF su thread separato per non bloccare la UI
        from progress_window import ProgressWindow
        pw_pdf = ProgressWindow(root, title="Generating PDF...")
        pw_pdf.set(10, "Preparing data...")

        _pdf_result = [None]

        def _pdf_thread():
            try:
                from pdf_report import preview_pdf_report
                preview_pdf_report(
                    root,
                    meta_dict=meta,
                    values_tuple=vals,
                    change_date=change_date,
                    username=username,
                    note_collaudatore_get=note_collaudatore_get,
                    note_ingegneria_get=note_ingegneria_get,
                    tipo_test=tipo_test,
                    on_progress=lambda p, m: root.after(0, lambda: pw_pdf.set(p, m)),
                )
                _pdf_result[0] = True
            except Exception as e:
                _pdf_result[0] = str(e)
            root.after(0, _pdf_done)

        def _pdf_done():
            pw_pdf.close()
            if _pdf_result[0] is not True:
                messagebox.showerror("Errore PDF",
                    f"Impossibile generare il PDF:\n{_pdf_result[0]}")

        import threading
        threading.Thread(target=_pdf_thread, daemon=True).start()

    def do_load_tdms():
        initial_dir = folder_path if os.path.isdir(folder_path) else os.path.expanduser("~")
        path = filedialog.askopenfilename(
            title="Seleziona file TDMS",
            initialdir=initial_dir,
            filetypes=[("TDMS files", "*.tdms"), ("Tutti i file", "*.*")],
        )
        if not path:
            return
        fname = os.path.basename(path)
        meta_name = parse_tdms_name(fname)
        if not meta_name:
            messagebox.showwarning("Formato non valido",
                "Il nome del file non rispetta il formato richiesto:\n"
                "DATA-REC_<commessa>_<matricola>_<YYYYMMDD>-<HHMMSS>_<00000>.tdms")
            return

        rec = {**meta_name, "filepath": path, "filename": fname, "created_by": username}

        # ── Progress window con Cancel ────────────────────────────────────────
        from progress_window import ProgressWindow
        pw = ProgressWindow(root, title="Loading TDMS...")
        pw.set(10, "Reading TDMS file...")

        _cancelled = [False]
        _result    = [None]   # None = in corso, True = ok, str = errore

        def _load():
            try:
                ingest_one_record(rec)
                # Genera il ptcache dopo l'ingest (TDMS e' ancora locale = veloce)
                if not _cancelled[0]:
                    import ptcache
                    ptcache.generate(
                        path,
                        on_progress=lambda p, m: root.after(
                            0, lambda p=p, m=m: pw.set(p, m))
                    )
                _result[0] = True
            except Exception as e:
                _result[0] = str(e)
            if not _cancelled[0]:
                root.after(0, _on_done)

        def _on_done():
            pw.close()
            if _cancelled[0]:
                return
            if _result[0] is True:
                ui.set_status("TDMS importato correttamente.")
                refresh_from_db()
            elif _result[0] == "UNIQUE constraint failed" or                  "UNIQUE constraint failed" in str(_result[0]):
                messagebox.showinfo("Già presente",
                    "Questo file è già presente in archivio.")
            else:
                messagebox.showerror("Errore import",
                    f"Non è stato possibile importare il file:\n{_result[0]}")

        def _on_cancel():
            _cancelled[0] = True
            pw.close()
            ui.set_status("Caricamento annullato.")

        pw.set_cancel_callback(_on_cancel)
        threading.Thread(target=_load, daemon=True).start()

    def do_unload_tdms():
        meta = get_sel_row_meta()
        if not meta:
            messagebox.showwarning("Selezione", "Seleziona una riga da rimuovere.")
            return
        if ruolo != "Admin":
            messagebox.showwarning("Permesso negato",
                "Solo Admin può rimuovere record dal database.")
            return
        if not messagebox.askyesno("Conferma rimozione",
                "Vuoi rimuovere la riga selezionata dal database?\n"
                "L'eventuale nota associata verrà eliminata."):
            return
        try:
            delete_acquisizione(meta["id"])
            ui.set_status("Record rimosso dal database.")
            refresh_from_db()
        except Exception as e:
            messagebox.showerror("Errore rimozione",
                f"Impossibile rimuovere il record:\n{e}")

    def do_verify_tdms():
        try:
            import tkinter as _tk
            import ptcache as _ptcache

            all_rows = select_all_acquisizioni()
            results  = []  # (nome_tdms, path, tdms_ok, json_ok)
            for row in all_rows:
                tdms_path = row[11] if row and len(row) > 11 else None
                if not tdms_path:
                    continue
                nome     = os.path.basename(tdms_path)
                tdms_ok  = os.path.exists(tdms_path)
                json_ok  = _ptcache.exists(tdms_path) if tdms_ok else False
                results.append((nome, tdms_path, tdms_ok, json_ok))

            # Ordina per nome
            results.sort(key=lambda x: x[0].lower())

            # ── Finestra risultati ───────────────────────────────────────────
            win = _tk.Toplevel(root)
            win.title("Verifica TDMS")
            win.minsize(900, 500)
            win.configure(bg="#f4f5f7")

            # Header
            hdr = _tk.Frame(win, bg="#9a3412", height=42)
            hdr.pack(fill=_tk.X)
            hdr.pack_propagate(False)
            _tk.Label(hdr, text="  Verifica file TDMS e cache JSON",
                      bg="#9a3412", fg="white",
                      font=("Segoe UI", 11, "bold")).pack(side=_tk.LEFT,
                                                           padx=12, pady=8)

            # Sommario
            n_tot   = len(results)
            n_tdms  = sum(1 for r in results if r[2])
            n_json  = sum(1 for r in results if r[3])
            n_miss  = n_tot - n_tdms
            summary = _tk.Frame(win, bg="#ffffff",
                                highlightbackground="#e2e5ea",
                                highlightthickness=1)
            summary.pack(fill=_tk.X, padx=12, pady=(10, 0))
            for txt, col in [
                (f"Totale: {n_tot}", "#111827"),
                (f"TDMS trovati: {n_tdms}", "#166534"),
                (f"TDMS mancanti: {n_miss}", "#991b1b" if n_miss else "#6b7280"),
                (f"Cache JSON presenti: {n_json}", "#1e40af"),
            ]:
                _tk.Label(summary, text=txt, bg="#ffffff", fg=col,
                          font=("Segoe UI", 9, "bold"),
                          padx=16, pady=6).pack(side=_tk.LEFT)

            # Treeview
            from tkinter import ttk as _ttk
            frame = _tk.Frame(win, bg="#f4f5f7")
            frame.pack(fill=_tk.BOTH, expand=True, padx=12, pady=10)

            cols = ("nome", "path", "tdms", "json")
            tv   = _ttk.Treeview(frame, columns=cols, show="headings",
                                  selectmode="browse")
            tv.heading("nome", text="Nome TDMS")
            tv.heading("path", text="Percorso")
            tv.heading("tdms", text="TDMS")
            tv.heading("json", text="Cache JSON")
            tv.column("nome", width=260, minwidth=180)
            tv.column("path", width=420, minwidth=200)
            tv.column("tdms", width=80,  minwidth=60,  anchor="center")
            tv.column("json", width=100, minwidth=60,  anchor="center")

            tv.tag_configure("ok",      background="#f0fdf4")
            tv.tag_configure("missing", background="#fef2f2")
            tv.tag_configure("no_json", background="#fffbeb")

            vsb = _ttk.Scrollbar(frame, orient="vertical",   command=tv.yview)
            hsb = _ttk.Scrollbar(frame, orient="horizontal", command=tv.xview)
            tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

            tv.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            frame.grid_rowconfigure(0, weight=1)
            frame.grid_columnconfigure(0, weight=1)

            for nome, path, tdms_ok, json_ok in results:
                tdms_lbl = "✓" if tdms_ok else "✗ mancante"
                json_lbl = "✓" if json_ok else ("— n/d" if not tdms_ok else "✗ assente")
                if not tdms_ok:
                    tag = "missing"
                elif not json_ok:
                    tag = "no_json"
                else:
                    tag = "ok"
                tv.insert("", "end",
                          values=(nome, path, tdms_lbl, json_lbl),
                          tags=(tag,))

            # Pulsante chiudi
            _tk.Button(win, text="Chiudi", command=win.destroy,
                       bg="#9a3412", fg="white",
                       font=("Segoe UI", 9), relief="flat",
                       padx=16, pady=5).pack(pady=(0, 10))

        except Exception as e:
            messagebox.showerror("Errore verifica",
                f"Impossibile verificare i file:\n{e}")

    # ── Wiring ────────────────────────────────────────────────────────────────
    ui.btn_open_cert.config(command=do_open_cert)
    ui.btn_note.config(command=do_note)
    ui.btn_pdf_preview.config(command=do_pdf_preview)
    ui.btn_load_tdms.config(command=do_load_tdms)
    ui.btn_unload_tdms.config(command=do_unload_tdms)
    ui.btn_verify_tdms.config(command=do_verify_tdms)

    tree.bind("<<TreeviewSelect>>", on_tree_select)
    tree.bind("<Button-1>", on_tree_click)

    # ── Avvio ─────────────────────────────────────────────────────────────────
    refresh_from_db()

    if not parent_root:
        root.mainloop()


# ── Standalone ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else FOLDER_PATH
    launch_dashboard(folder, DEFAULT_USERNAME, DEFAULT_RUOLO)