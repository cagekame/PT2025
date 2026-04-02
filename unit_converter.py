# unit_converter.py
"""
Modulo per conversione unità di misura tra Metric (SI) e U.S. Customary.

I dati TDMS sono sempre in Metric (sorgente unica).
Questo modulo converte al volo per visualizzazione UI e PDF.
"""

# ================== FATTORI DI CONVERSIONE ==================

# Flow (portata)
M3H_TO_GPM = 4.40287  # m3/h -> gallons per minute

# Head (prevalenza)
M_TO_FT = 3.28084  # metri -> feet

# Power (potenza)
KW_TO_HP = 1.34102  # kW -> horsepower

# Pressure
M_TO_FT_PRESSURE = 3.28084  # metri colonna d'acqua -> feet

# Temperature (NON lineare!)
def celsius_to_fahrenheit(c):
    """degC -> degF"""
    return (c * 9/5) + 32

def fahrenheit_to_celsius(f):
    """degF -> degC"""
    return (f - 32) * 5/9

# Viscosity
CP_TO_CP = 1.0  # centipoise = centipoise (stessa unita' in entrambi i sistemi)

# Specific Gravity
SG_TO_SG = 1.0  # adimensionale (stessa in entrambi i sistemi)

# Diametro
MM_TO_IN = 0.0393701  # millimetri -> inches


# ================== DIZIONARIO UNITA PER ETICHETTE ==================

UNITS = {
    "Metric": {
        "flow": "m³/h",
        "head": "m",
        "power": "kW",
        "pressure": "m",
        "temp": "°C",
        "visc": "cP",
        "sg": "",  # adimensionale
        "diameter": "mm",
        "suction_discharge": "Inch",  # rimane inch in entrambi (già in pollici nel TDMS)
        "npsh": "m",
        "speed": "rpm",  # rimane rpm in entrambi
    },
    "US": {
        "flow": "GPM",
        "head": "ft",
        "power": "HP",
        "pressure": "ft",
        "temp": "°F",
        "visc": "cP",
        "sg": "",
        "diameter": "in",
        "suction_discharge": "Inch",
        "npsh": "ft",
        "speed": "rpm",
    }
}


# ================== FUNZIONI DI CONVERSIONE ==================

def convert_value(value, param_type: str, from_system: str, to_system: str):
    """
    Converte un valore da un sistema di unità all'altro.
    
    Args:
        value: valore da convertire (numero o stringa)
        param_type: tipo di parametro ('flow', 'head', 'power', 'temp', ecc.)
        from_system: sistema sorgente ('Metric' o 'US')
        to_system: sistema destinazione ('Metric' o 'US')
    
    Returns:
        Valore convertito (stesso tipo dell'input)
    """
    # Se stessa unita, nessuna conversione
    if from_system == to_system:
        return value
    
    # Se valore non numerico, ritorna invariato
    try:
        v = float(value)
    except (ValueError, TypeError):
        return value
    
    # Conversioni Metric -> US
    if from_system == "Metric" and to_system == "US":
        if param_type == "flow":
            result = v * M3H_TO_GPM
        elif param_type == "head":
            result = v * M_TO_FT
        elif param_type == "power":
            result = v * KW_TO_HP
        elif param_type == "pressure":
            result = v * M_TO_FT_PRESSURE
        elif param_type == "npsh":
            result = v * M_TO_FT
        elif param_type == "temp":
            result = celsius_to_fahrenheit(v)
        elif param_type == "diameter":
            result = v * MM_TO_IN
        else:
            # Parametri che non cambiano (sg, visc, speed, suction/discharge)
            result = v
    
    # Conversioni US -> Metric
    elif from_system == "US" and to_system == "Metric":
        if param_type == "flow":
            result = v / M3H_TO_GPM
        elif param_type == "head":
            result = v / M_TO_FT
        elif param_type == "power":
            result = v / KW_TO_HP
        elif param_type == "pressure":
            result = v / M_TO_FT_PRESSURE
        elif param_type == "npsh":
            result = v / M_TO_FT
        elif param_type == "temp":
            result = fahrenheit_to_celsius(v)
        elif param_type == "diameter":
            result = v / MM_TO_IN
        else:
            result = v
    else:
        result = v
    
    # Ritorna nello stesso tipo dell'input
    if isinstance(value, int):
        return int(round(result))
    elif isinstance(value, str):
        return str(result)
    else:
        return result


def get_unit_label(param_type: str, system: str) -> str:
    """
    Ritorna l'etichetta dell'unità di misura per un parametro.
    
    Args:
        param_type: tipo di parametro ('flow', 'head', ecc.)
        system: sistema di unità ('Metric' o 'US')
    
    Returns:
        Stringa con l'unità (es. 'm³/h', 'GPM', 'ft', ecc.)
    """
    return UNITS.get(system, {}).get(param_type, "")


def format_with_unit(value, param_type: str, system: str, decimals: int = 2) -> str:
    """
    Formatta un valore con la sua unità di misura.
    
    Args:
        value: valore numerico
        param_type: tipo di parametro
        system: sistema di unità
        decimals: numero di decimali
    
    Returns:
        Stringa formattata (es. "150.5 m³/h", "663.4 GPM")
    """
    try:
        v = float(value)
        unit = get_unit_label(param_type, system)
        if unit:
            return f"{v:.{decimals}f} {unit}"
        else:
            return f"{v:.{decimals}f}"
    except (ValueError, TypeError):
        return str(value)


# ================== HELPER PER TABELLE PERFORMANCE ==================

def convert_performance_table(columns: list, rows: list, from_system: str, to_system: str) -> tuple:
    """
    Converte un'intera tabella di performance (Calculated o Converted).
    
    Args:
        columns: lista nomi colonne
        rows: lista di liste (righe dati)
        from_system: sistema sorgente
        to_system: sistema destinazione
    
    Returns:
        (columns_converted, rows_converted) con nuove etichette unità e valori convertiti
    """
    import re as _re

    def _col_base(col):
        """Estrae il nome base della colonna rimuovendo le unita' tra []."""
        return _re.sub(r"\[[^\]]*\]", "", col).strip().upper()

    # Mappa nome base ESATTO -> tipo parametro
    column_map = {
        "FLOW":             "flow",
        "CAPACITY":         "flow",
        "Q":                "flow",
        "TDH":              "head",
        "HEAD":             "head",
        "KIN SUCT.":        "head",
        "KIN DISCH.":       "head",
        "SUCTION PRESS":    "pressure",
        "DISCHARGE PRESS":  "pressure",
        "ATMPRESS":         "pressure",
        "POWER":            "power",
        "ABS_POWER":        "power",
        "ABSORBED POWER":   "power",
        "EFF":              None,
        "EFFICIENCY":       None,
        "NPSH":             "npsh",
        "KNPSH":            "npsh",
        "TEMP":             "temp",
        "TEMPERATURE":      "temp",
        "WATERTEMP":        "temp",
        "SPEED":            "speed",
        "RPM":              "speed",
        "VISC":             "visc",
        "VISCOSITY":        "visc",
        "SG":               "sg",
        "SPECIFIC GRAVITY": "sg",
    }

    # Converti header colonne: rimuovi unita' esistenti e aggiungi quelle corrette
    new_columns = []
    for col in columns:
        base = _col_base(col)
        param_type = column_map.get(base)
        if param_type:
            new_unit = get_unit_label(param_type, to_system)
            # Rimuovi qualsiasi unita' esistente tra [] e appendi quella nuova
            clean = _re.sub(r"\[[^\]]*\]", "", col).strip()
            new_col = f"{clean} [{new_unit}]" if new_unit else clean
        else:
            # Caso speciale: efficienza senza unità → aggiungi [%]
            if base in ("EFF", "EFFICIENCY") and "[" not in col:
                new_col = f"{col} [%]"
            else:
                new_col = col
        new_columns.append(new_col)

    # Converti valori nelle righe
    new_rows = []
    for row in rows:
        new_row = []
        for i, val in enumerate(row):
            col_name = columns[i] if i < len(columns) else ""
            base = _col_base(col_name)
            param_type = column_map.get(base)
            new_row.append(convert_value(val, param_type, from_system, to_system) if param_type else val)
        new_rows.append(new_row)

    return new_columns, new_rows


def convert_contractual_data(data: dict, from_system: str, to_system: str) -> dict:
    """
    Converte i dati contrattuali (Rated Point, Loop Details, ecc.).
    
    Args:
        data: dizionario con chiavi tipo "Capacity [m3/h]", "TDH [m]", ecc.
        from_system: sistema sorgente
        to_system: sistema destinazione
    
    Returns:
        Nuovo dizionario con valori convertiti e chiavi aggiornate
    """
    if from_system == to_system:
        return data
    
    # Mapping chiavi -> tipo parametro
    key_map = {
        "Capacity [m3/h]": "flow",
        "TDH [m]": "head",
        "Efficiency [%]": None,
        "ABS_Power [kW]": "power",
        "Speed [rpm]": "speed",
        "Temperature [°C]": "temp",
        "WaterTemp [°C]": "temp",
        "Viscosity [cP]": "visc",
        "NPSH [m]": "npsh",
        "KNPSH [m]": "npsh",
        "AtmPress [m]": "pressure",
        "SG Contract": "sg",
        "Diam Nominal": "diameter",
    }
    
    converted = {}
    for key, value in data.items():
        param_type = key_map.get(key)
        
        if param_type:
            # Converti valore
            new_value = convert_value(value, param_type, from_system, to_system)
            
            # Aggiorna etichetta chiave
            old_unit = get_unit_label(param_type, from_system)
            new_unit = get_unit_label(param_type, to_system)
            if old_unit and new_unit and old_unit in key:
                new_key = key.replace(old_unit, new_unit)
            else:
                new_key = key
            
            converted[new_key] = new_value
        else:
            converted[key] = value
    
    return converted

# ================== NORMALIZZAZIONE COLONNE RECORDED ==================

def normalize_recorded_columns(columns: list, unit_system: str = "Metric", has_units: bool = True) -> list:
    """
    Normalizza le unita' di misura nelle intestazioni delle colonne Recorded.

    - has_units=True  (PERFORMANCE): i canali hanno gia' le unita' nel nome
      -> semplice replace ASCII->Unicode (m3/h->m³/h, [C]->[°C])
    - has_units=False (NPSH, RUNNING): i canali non hanno unita'
      -> aggiunge le unita' tramite convert_performance_table (stessa logica
         usata per Calc e Converted)
    """
    if not columns:
        return columns

    if has_units:
        # PERFORMANCE: replace ASCII -> Unicode
        result = []
        for col in columns:
            col = col.replace("m3/h", "m³/h")
            col = col.replace("[C]", "[°C]")
            result.append(col)
        return result
    else:
        # NPSH / RUNNING: aggiunge unita' dalla column_map
        new_cols, _ = convert_performance_table(columns, [], "Metric", unit_system)
        return new_cols