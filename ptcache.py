"""
ptcache.py
Gestione del file .ptcache — cache JSON dei dati elaborati dal TDMS.

Il file .ptcache viene creato nella stessa cartella del TDMS con lo stesso
nome e estensione .ptcache. Contiene i dati gia' processati (medie, valori
finali) pronti per la visualizzazione nel certificato.

API pubblica:
    generate(tdms_path, test_index)  -> bool
    load(tdms_path, test_index)      -> dict | None
    exists(tdms_path)                -> bool
    get_path(tdms_path)              -> str
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

PTCACHE_VERSION = 7   # v7: % finale -> [%] nei nomi canali


# ── Utility ───────────────────────────────────────────────────────────────────

def get_path(tdms_path: str) -> str:
    """Restituisce il path del .ptcache corrispondente al TDMS."""
    base = os.path.splitext(tdms_path)[0]
    return base + ".ptcache"


def exists(tdms_path: str) -> bool:
    """Controlla se il .ptcache esiste per il TDMS dato."""
    return os.path.isfile(get_path(tdms_path))


# ── Serializzazione ───────────────────────────────────────────────────────────

def _serialize_value(v):
    """Converte un valore in tipo JSON-serializzabile, arrotondando a 2 decimali."""
    if v is None or v == "":
        return None
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        # Prova a convertire stringhe numeriche e arrotondare
        try:
            f = float(v.replace(",", "."))
            return round(f, 2)
        except (ValueError, AttributeError):
            return v
    return str(v)


def _serialize_rows(rows: list) -> list:
    """Serializza le righe della tabella."""
    result = []
    for row in rows:
        result.append([_serialize_value(v) for v in row])
    return result


def _serialize_perf(perf: dict) -> dict:
    """Serializza il dizionario perf (Recorded/Calc/Converted)."""
    out = {}
    for kind in ("Recorded", "Calc", "Converted"):
        data = perf.get(kind, {})
        out[kind] = {
            "columns": data.get("columns", []),
            "rows":    _serialize_rows(data.get("rows", [])),
        }
    return out


# Colonne NPSH non gestite da convert_performance_table — conversione manuale
_NPSH_HEAD_COLS = {"TDH 1st STAGE RED", "TDH 1st STAGE FULL", "DELTA"}

def _convert_npsh_extra_cols(cols, rows, from_sys, to_sys):
    """Converte colonne NPSH specifiche non gestite da convert_performance_table."""
    if from_sys == to_sys:
        return cols, rows
    try:
        import unit_converter as uc
        factor = None
        try:
            factor = uc.convert_value(1.0, "head", from_sys, to_sys)
        except Exception:
            return cols, rows
        if factor is None:
            return cols, rows
        suffix = uc.get_unit_label("head", to_sys)
        new_cols = []
        convert_idx = []
        for i, c in enumerate(cols):
            base = str(c).split("[")[0].strip()
            if base in _NPSH_HEAD_COLS:
                new_cols.append(f"{base} [{suffix}]")
                convert_idx.append(i)
            else:
                new_cols.append(c)
        if not convert_idx:
            return cols, rows
        new_rows = []
        for row in rows:
            new_row = list(row)
            for i in convert_idx:
                if i < len(new_row) and new_row[i] != "" and new_row[i] is not None:
                    try:
                        new_row[i] = round(float(new_row[i]) * factor, 2)
                    except Exception:
                        pass
            new_rows.append(tuple(new_row))
        return new_cols, new_rows
    except Exception:
        return cols, rows


def _convert_and_serialize_perf(perf: dict, from_sys: str, to_sys: str) -> dict:
    """Converte le tabelle perf nel sistema target e serializza."""
    try:
        import unit_converter as uc
        out = {}
        for kind in ("Recorded", "Calc", "Converted"):
            data = perf.get(kind, {})
            cols = data.get("columns", [])
            rows = data.get("rows", [])
            if kind in ("Calc", "Converted") and rows:
                cols, rows = uc.convert_performance_table(
                    cols, rows, from_sys, to_sys)
                # Converti anche colonne NPSH specifiche
                cols, rows = _convert_npsh_extra_cols(cols, rows, from_sys, to_sys)
            out[kind] = {
                "columns": cols,
                "rows":    _serialize_rows(rows),
            }
        return out
    except Exception:
        return _serialize_perf(perf)


def _convert_and_serialize_contract(contract: dict,
                                     from_sys: str, to_sys: str) -> dict:
    """Converte i dati contrattuali nel sistema target e serializza."""
    try:
        import unit_converter as uc
        converted = uc.convert_contractual_data(contract, from_sys, to_sys)
        return {k: _serialize_value(v) for k, v in converted.items()}
    except Exception:
        return contract


# ── Generate ──────────────────────────────────────────────────────────────────

def generate(tdms_path: str, on_progress=None) -> bool:
    """
    Legge il TDMS e genera il file .ptcache nella stessa cartella.

    Salva i dati di tutti i test type presenti (PERFORMANCE, NPSH, RUNNING).
    I valori sono gia' processati (medie dei campionamenti).

    Args:
        tdms_path:   path del file TDMS
        on_progress: callable(percent, message) opzionale

    Returns:
        True se generato con successo, False altrimenti
    """
    def _prog(p, m):
        if on_progress:
            try:
                on_progress(p, m)
            except Exception:
                pass

    if not tdms_path or not os.path.exists(tdms_path):
        logger.warning(f"ptcache.generate: file non trovato: {tdms_path}")
        return False

    try:
        from tdms_reader import read_all_data, detect_test_types

        _prog(5, "Detecting test types...")
        test_types = detect_test_types(tdms_path)
        if not test_types:
            test_types = ["PERFORMANCE"]   # fallback

        TEST_INDEX_MAP = {"PERFORMANCE": 0, "NPSH": 1, "RUNNING": 2}

        cache_data = {
            "version":    PTCACHE_VERSION,
            "tdms_path":  tdms_path,
            "test_types": test_types,
            "tests":      {},
        }

        n = len(test_types)
        for i, test_type in enumerate(test_types):
            test_index = TEST_INDEX_MAP.get(test_type, 0)
            pct_start  = 10 + int(i / n * 80)
            pct_end    = 10 + int((i + 1) / n * 80)

            _prog(pct_start, f"Reading {test_type} data...")

            def _sub_progress(p, m):
                # Mappa il progresso di read_all_data nel range pct_start..pct_end
                mapped = pct_start + int((p / 100) * (pct_end - pct_start))
                _prog(mapped, m)

            data = read_all_data(tdms_path, test_index=test_index,
                                 on_progress=_sub_progress)

            contract_metric = data.get("contract", {})
            perf_metric     = data.get("perf", {})

            # Serializza metric con arrotondamento a 2 decimali
            # _serialize_value gestisce sia float che stringhe numeriche
            contract_metric_serial = {
                k: _serialize_value(v)
                for k, v in contract_metric.items()
            }

            # Converte e serializza anche in US (una volta sola)
            cache_data["tests"][test_type] = {
                "contract_metric": contract_metric_serial,
                "contract_us":     _convert_and_serialize_contract(
                                       contract_metric, "Metric", "US"),
                "perf_metric":     _serialize_perf(perf_metric),
                "perf_us":         _convert_and_serialize_perf(
                                       perf_metric, "Metric", "US"),
                "power_calc_type": data.get("power_calc_type", "-"),
            }

        _prog(92, "Writing cache file...")

        # Scrivi il file ptcache
        out_path = get_path(tdms_path)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

        _prog(100, "Cache ready.")
        logger.info(f"ptcache generato: {out_path}")
        return True

    except Exception as e:
        logger.error(f"ptcache.generate error: {e}", exc_info=True)
        return False


# ── Load ──────────────────────────────────────────────────────────────────────

def load(tdms_path: str, test_index: int = 0,
         unit_system: str = "Metric") -> dict | None:
    """
    Carica i dati dal .ptcache per il test_index e unit_system richiesti.

    Returns:
        dict con chiavi contract, perf, power_calc_type, from_cache=True
        oppure None se il ptcache non esiste o e' corrotto
    """
    cache_path = get_path(tdms_path)
    if not os.path.isfile(cache_path):
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Verifica versione — se obsoleta, cancella e forza rigenerazione
        file_version = data.get("version", 0)
        if file_version != PTCACHE_VERSION:
            logger.info(f"ptcache versione {file_version} obsoleta "
                        f"(attesa {PTCACHE_VERSION}), rigenerazione...")
            try:
                os.remove(cache_path)
            except Exception:
                pass
            return None

        # Trova il test type per l'index richiesto
        INDEX_TEST_MAP = {0: "PERFORMANCE", 1: "NPSH", 2: "RUNNING"}
        test_type = INDEX_TEST_MAP.get(test_index, "PERFORMANCE")

        tests = data.get("tests", {})
        if test_type not in tests:
            logger.warning(f"ptcache: test_type '{test_type}' non trovato in {cache_path}")
            return None

        test_data = tests[test_type]

        # Seleziona il sistema di unita' richiesto
        suffix = "_us" if unit_system == "US" else "_metric"
        contract_key = f"contract{suffix}"
        perf_key     = f"perf{suffix}"

        # Fallback a metric se il sistema richiesto non e' presente
        # (ptcache generato con versione precedente)
        contract_raw = test_data.get(contract_key) or                        test_data.get("contract_metric") or                        test_data.get("contract", {})
        perf_raw     = test_data.get(perf_key) or                        test_data.get("perf_metric") or                        test_data.get("perf", {})

        # Ricostruisci le righe come tuple
        perf = {}
        for kind in ("Recorded", "Calc", "Converted"):
            kind_data = perf_raw.get(kind, {})
            cols = kind_data.get("columns", [])
            rows = [tuple(v if v is not None else "" for v in row)
                    for row in kind_data.get("rows", [])]
            perf[kind] = {"columns": cols, "rows": rows}

        return {
            "contract":        contract_raw,
            "perf":            perf,
            "power_calc_type": test_data.get("power_calc_type", "-"),
            "from_cache":      True,
            "unit_system":     unit_system,
        }

    except Exception as e:
        logger.error(f"ptcache.load error: {e}", exc_info=True)
        return None


def load_test_types(tdms_path: str) -> list:
    """
    Carica solo i test_types dal ptcache senza caricare tutti i dati.
    Utile per la dashboard.
    """
    cache_path = get_path(tdms_path)
    if not os.path.isfile(cache_path):
        return []
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("test_types", [])
    except Exception:
        return []