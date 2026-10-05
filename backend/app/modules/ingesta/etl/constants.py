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
