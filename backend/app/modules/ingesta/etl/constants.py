"""CSV ingestion constants; signal names match the original export."""

ORIGEN_CSV = "csv"
MOTIVO_DUPLICADO = "registro duplicado"

REQUIRED_COLUMNS_CSV = [
    "sys_time",
    "lat",
    "long",
    "accuracy",
    "node_id",
    "cid",
    "psc_pci",
    "rssi",
    "rsrq",
    "rssnr",
    "gps",
    "lac_tac",
    "arfcn",
    "net_type",
    # Agregadas al soportar Session_43_20260623_165825.csv (export real de
    # NetMonitor Lite, 86,398 filas): ya estaban presentes en los archivos
    # csv anteriores, pero no se extraían porque nada las necesitaba todavía.
    "report",
    "tech",
    "data_state",
    "call_state",
]

# Columnas que no son de REQUIRED_COLUMNS_CSV pero se extraen si existen.
# `rssi_strongest` (RSRP de NetMonitor, ver docs/migracion_csv_senales.md) es
# opcional para conservar compatibilidad con exportaciones que no la
# incluyan: si falta, `rsrp` queda NULL sin warning de columna ausente.
EXTRA_COLUMNS_CSV = ["rssi_strongest"]

# Obligatorias de verdad: timestamp + identidad de celda. El resto de
# REQUIRED_COLUMNS_CSV es opcional (NULL + un warning si falta).
MANDATORY_COLUMNS_CSV = ["sys_time", "cid"]

# Nombres alternativos aceptados para una columna, además del canónico. La
# comparación ya ignora mayúsculas, tildes, espacios extra y '_' vs ' '
# (extractor.normalize_header), así que aquí solo van nombres realmente
# distintos.
COLUMN_ALIASES_CSV: dict[str, list[str]] = {}

MOTIVO_TIMESTAMP_AUSENTE = "timestamp vacío (no se puede ubicar la medición en el tiempo)"
MOTIVO_CELDA_AUSENTE = "identificador de celda vacío (no se puede identificar la celda)"
# tecnologia es NOT NULL en handover_record: si el archivo no trae la columna
# fuente (`tech`), la fila no se puede guardar (se rechaza con motivo
# explícito, no se inventa un valor).
MOTIVO_TECNOLOGIA_AUSENTE = "tecnología vacía (columna fuente de `tecnologia`, NOT NULL)"
MOTIVO_VALOR_NO_INTERPRETABLE = "valor no interpretable"

# Identidad usada para detectar observaciones duplicadas.
DEDUP_KEY_CSV = ["sys_time", "cid", "lac_tac", "arfcn", "net_type", "lat", "long"]

# Campos donde, si aparece el centinela, el campo se guarda NULL con un
# warning agregado (a diferencia de `cid`, que si trae el centinela rechaza
# todo el registro — ver MOTIVO_CID_CENTINELA).
CAMPOS_CENTINELA_CSV_NULEABLES = ["node_id", "psc_pci", "rssi", "rssi_strongest", "rsrq", "rssnr", "lac_tac", "arfcn"]

SENTINEL_INT32_MAX = 2147483647

# accuracy usa un centinela propio (-1), distinto del resto (2147483647).
ACCURACY_SIN_DATO = -1

LATITUD_SIN_FIX_CSV = -1
LONGITUD_SIN_FIX_CSV = -1

TECNOLOGIA_SIN_SENAL = 0
TECNOLOGIA_LTE = 1
TECNOLOGIA_3G = 2
TECNOLOGIA_2G = 3

# `tecnologia` (csv) se deriva de `tech`, NO de `net_type` — confirmado por
# el usuario tras analizar Session_41..47 (434,631 filas válidas): en 42,382
# (9.8%; 29.4% en S41) net_type y tech discrepan, y la evidencia de radio
# (band, EARFCN/ARFCN, presencia de rsrq/node_id) coincide siempre con
# `tech`. `net_type` es el tipo de red del portador de datos de Android, no
# la tecnología de la celda medida. Se sigue guardando como dato informativo.
TECH_A_TECNOLOGIA = {
    "LTE": 1,    # TECNOLOGIA_LTE
    "WCDMA": 2,  # TECNOLOGIA_3G
    "GSM": 3,    # TECNOLOGIA_2G
}

# net_type ya no decide nada: estos conjuntos solo sirven para el warning de
# auditoría que cuenta filas donde net_type sugiere otra tecnología que tech.
NET_TYPE_LTE = "LTE"
# HSPA (sin '+') confirmado en Session_43_20260623_165825.csv (145 filas
# reales), además de HSPA+/UMTS ya confirmados antes.
NET_TYPE_3G = {"UMTS", "HSPA+", "HSPA"}
# Confirmado en el mismo archivo real (EDGE 466 filas, GPRS 51 filas). 'GSM'
# es un valor de `tech`, no de `net_type` — nunca aparece aquí.
NET_TYPE_2G = {"EDGE", "GPRS"}

MOTIVO_CID_CENTINELA = "cid = 2147483647 (sin dato, equipo de medición)"

# GPS sin fix se conserva con coordenadas NULL:
# confirmado con Session_43_20260623_165825.csv que rechazar por esto tira el
# 92% del archivo (solo 8.0% de las filas trae fix de GPS) y contradice R3
# del módulo de visualización temporal, que no usa coordenadas. Desde esta
# corrección, `cleaner.apply_sentinels_csv` anula lat/long a NULL en vez de
# que `validator.validate_record_csv` rechace el registro; el warning
# agregado se construye en services.py.

TIMEZONE_ORIGEN = "America/Guayaquil"  # UTC-5, sin DST (CSV)

# --- Velocidad calculada (distancia/tiempo entre registros consecutivos) --

# Por encima de esto no se rechaza ni se fuerza a NULL: se guarda tal cual
# y se agrega un warning (podría ser ruido de GPS o un registro desordenado,
# es información de calidad de datos que vale la pena trazar).
VELOCIDAD_MAX_ESPERADA_KMH = 200
