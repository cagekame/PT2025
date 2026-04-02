"""
create_fresh_db.py
==================
Crea un database collaudi.db completamente nuovo con tutte le tabelle e FK corrette.

Uso:
    python create_fresh_db.py                        # crea collaudi.db nella cartella corrente
    python create_fresh_db.py "C:/path/collaudi.db"  # path esplicito

ATTENZIONE: Se il file esiste già, viene SOVRASCRITTO (con backup automatico)!
"""

import sqlite3
import sys
import os
from datetime import datetime


def create_database(db_path: str, make_backup: bool = True) -> bool:
    """
    Crea un database SQLite con lo schema completo per l'applicazione collaudi.
    
    Args:
        db_path: percorso dove creare il database
        make_backup: se True e il file esiste, crea backup prima di sovrascrivere
    
    Returns:
        True se creazione OK, False altrimenti
    
    Raises:
        Exception: in caso di errore durante la creazione
    """
    # Se esiste, fai backup
    if os.path.exists(db_path) and make_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = db_path + f".backup_{ts}"
        import shutil
        shutil.copy2(db_path, backup)
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    cur = conn.cursor()


    # ================================================================
    # TABELLA UTENTI (compatibile con login.py esistente)
    # ================================================================
    cur.execute("""
        CREATE TABLE Utenti (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Username TEXT UNIQUE NOT NULL,
            Password TEXT NOT NULL,
            Ruolo TEXT NOT NULL
        )
    """)

    # ================================================================
    # TABELLA ACQUISIZIONI (principale)
    # ================================================================
    cur.execute("""
        CREATE TABLE acquisizioni (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job TEXT,
            n_collaudo TEXT,
            matricola TEXT,
            tipo_pompa TEXT,
            data TEXT,
            stato TEXT,
            data_approvazione TEXT,
            nome_approvatore TEXT,
            tipo_test TEXT,
            taglio_girante TEXT,
            filepath TEXT,
            filename TEXT,
            data_file TEXT,
            ora_file TEXT,
            progressivo INTEGER,
            unit_system TEXT DEFAULT 'Metric',
            created_at TEXT DEFAULT (datetime('now')),
            created_by TEXT,
            checked_by TEXT,
            checked_at TEXT,
            engineering_user TEXT,
            engineering_at TEXT,
            test_cell TEXT DEFAULT '',
            hydraulic TEXT DEFAULT '',
            UNIQUE(filepath, tipo_test)
        )
    """)

    # Indici per performance
    cur.execute("""
        CREATE INDEX idx_acq_sort 
        ON acquisizioni(data_file, ora_file, progressivo)
    """)
    cur.execute("CREATE INDEX idx_acq_job ON acquisizioni(job)")
    cur.execute("CREATE INDEX idx_acq_matricola ON acquisizioni(matricola)")

    # ================================================================
    # TABELLA NOTES (note collaudatore + ingegneria)
    # ================================================================
    cur.execute("""
        CREATE TABLE notes (
            acquisizione_id INTEGER PRIMARY KEY,
            note_collaudatore TEXT DEFAULT '',
            note_ingegneria TEXT DEFAULT '',
            FOREIGN KEY(acquisizione_id) 
                REFERENCES acquisizioni(id) 
                ON DELETE CASCADE
        )
    """)

    # ================================================================
    # TABELLA CURVE_SETTINGS (impostazioni visualizzazione curve)
    # ================================================================
    cur.execute("""
        CREATE TABLE curve_settings (
            acquisizione_id INTEGER PRIMARY KEY,
            show_points INTEGER DEFAULT 1,
            eff_min REAL DEFAULT 0.0,
            eff_max REAL DEFAULT 100.0,
            FOREIGN KEY(acquisizione_id) 
                REFERENCES acquisizioni(id) 
                ON DELETE CASCADE
        )
    """)

    # ================================================================
    # TABELLA HIDDEN_ROWS (righe nascoste nelle tabelle)
    # ================================================================
    cur.execute("""
        CREATE TABLE hidden_rows (
            acquisizione_id INTEGER NOT NULL,
            test_type TEXT NOT NULL,
            row_iid TEXT NOT NULL,
            PRIMARY KEY (acquisizione_id, test_type, row_iid),
            FOREIGN KEY(acquisizione_id)
                REFERENCES acquisizioni(id)
                ON DELETE CASCADE
        )
    """)

    # ================================================================
    # UTENTE ADMIN DI DEFAULT (password in chiaro: admin)
    # ================================================================
    cur.execute("""
        INSERT INTO Utenti(Username, Password, Ruolo)
        VALUES('admin', 'admin', 'Admin')
    """)

    # ================================================================
    # COMMIT E CHIUSURA
    # ================================================================
    conn.commit()
    conn.close()

    
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = os.path.join(os.getcwd(), "collaudi.db")

    
    try:
        create_database(path, make_backup=True)
    except Exception as e:
        sys.exit(1)