"""Constantes del dominio de handover, confirmadas contra el archivo real
(Datos_Tesis.xlsx, 3 hojas, 495 registros). No modificar sin volver a
analizar datos reales o sin confirmación explícita del usuario.
"""

REQUIRED_COLUMNS = [
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

TIMEZONE_ORIGEN = "America/Guayaquil"  # UTC-5, sin DST

MOTIVO_CELL_ID_CERO = "cell_id = 0 (desconexión/error de medición)"
MOTIVO_RSRP_CENTINELA = "rsrp = 99 (centinela de error del equipo de medición)"
MOTIVO_GPS_SIN_FIX = "gps sin fix"
MOTIVO_RSRP_FUERA_DE_RANGO = "rsrp fuera de rango físico"
MOTIVO_COORDENADAS_FUERA_DE_RANGO = "coordenadas fuera del rango esperado para Ecuador"
MOTIVO_DUPLICADO = "registro duplicado"
