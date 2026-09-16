"""Constantes del dominio de handover, confirmadas contra datos reales de dos
orígenes distintos. No modificar sin volver a analizar datos reales o sin
confirmación explícita del usuario.

Origen 'xlsx' — Datos_Tesis.xlsx, 3 hojas, 495 registros.
Origen 'csv'  — Network Cell Info, dataset_unificado.csv, 11,954 registros.
"""

ORIGEN_XLSX = "xlsx"
ORIGEN_CSV = "csv"

# --- Origen xlsx --------------------------------------------------------

REQUIRED_COLUMNS_XLSX = [
    "Fecha",
    "Hora",
    "Cell ID/ECI",
    "TAC/LAC",
    "EARFCN",
    "Tecnología",
    "Latitud",
    "Longitud",
    "RSRP",
]

# Mismas columnas se usan como llave de deduplicación (fila cruda completa).
DEDUP_KEY_XLSX = REQUIRED_COLUMNS_XLSX

# Columnas presentes en el Excel real que se descartan explícitamente
# (no se extraen, no se guardan en ningún lado): PCI/PSC, Column10, Column12,
# "Dirección - distancia GPS".

RSRP_MIN_VALID = -140
RSRP_MAX_VALID = -1
RSRP_STRONG_SIGNAL_THRESHOLD = -44  # por encima de esto: warning, no rechazo

LATITUD_MIN = -5
LATITUD_MAX = 2
LONGITUD_MIN = -92
LONGITUD_MAX = -75

MOTIVO_CELL_ID_CERO = "cell_id = 0 (desconexión/error de medición)"
MOTIVO_RSRP_CENTINELA = "rsrp = 99 (centinela de error del equipo de medición)"
MOTIVO_GPS_SIN_FIX = "gps sin fix"
MOTIVO_RSRP_FUERA_DE_RANGO = "rsrp fuera de rango físico"
MOTIVO_COORDENADAS_FUERA_DE_RANGO = "coordenadas fuera del rango esperado para Ecuador"
MOTIVO_DUPLICADO = "registro duplicado"

# --- Origen csv (Network Cell Info) -------------------------------------

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
]

# Equivalente csv de DEDUP_KEY_XLSX: mismas 7 columnas de negocio que ya se
# usan para xlsx (timestamp/celda/tac/earfcn/tecnología/coordenadas). El csv
# no tiene un campo equivalente a RSRP (usa rssi/rsrq/rssnr en su lugar), por
# eso la llave tiene 7 columnas en vez de 9.
DEDUP_KEY_CSV = ["sys_time", "cid", "lac_tac", "arfcn", "net_type", "lat", "long"]

# Campos donde, si aparece el centinela, el campo se guarda NULL con un
# warning agregado (a diferencia de `cid`, que si trae el centinela rechaza
# todo el registro — ver MOTIVO_CID_CENTINELA).
CAMPOS_CENTINELA_CSV_NULEABLES = ["node_id", "psc_pci", "rssi", "rsrq", "rssnr", "lac_tac", "arfcn"]

SENTINEL_INT32_MAX = 2147483647

# accuracy usa un centinela propio (-1), distinto del resto (2147483647).
ACCURACY_SIN_DATO = -1

LATITUD_SIN_FIX_CSV = -1
LONGITUD_SIN_FIX_CSV = -1

TECNOLOGIA_SIN_SENAL = 0
TECNOLOGIA_LTE = 1
TECNOLOGIA_3G = 2

NET_TYPE_LTE = "LTE"
NET_TYPE_3G = {"UMTS", "HSPA+"}

MOTIVO_CID_CENTINELA = "cid = 2147483647 (sin dato, equipo de medición)"
MOTIVO_GPS_SIN_FIX_CSV = "gps sin fix (centinela lat/long = -1)"

TIMEZONE_ORIGEN = "America/Guayaquil"  # UTC-5, sin DST (xlsx y csv)

# --- Velocidad calculada (distancia/tiempo entre registros consecutivos) --

# Por encima de esto no se rechaza ni se fuerza a NULL: se guarda tal cual
# y se agrega un warning (podría ser ruido de GPS o un registro desordenado,
# es información de calidad de datos que vale la pena trazar).
VELOCIDAD_MAX_ESPERADA_KMH = 200
