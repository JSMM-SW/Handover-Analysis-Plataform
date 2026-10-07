"""
Pruebas del rótulo PCI/PSC de la secuencia de radiobases y del histograma.

La interfaz muestra las celdas por su identificador físico (PCI en LTE, PSC en WCDMA), pero los
tramos y los handovers se siguen formando por celda (ECI). Se protege:

- el rótulo de cada tecnología, incluido GSM, que no tiene PCI ni PSC;
- que el PCI se resuelva por celda: un tramo suelto sin PCI no cambia de rótulo;
- que dos celdas con el mismo PCI compartan altura sin dejar de ser dos celdas;
- que el histograma por PCI/PSC cuente una racha seguida del mismo PCI como una sola visita.
"""

from datetime import datetime, timedelta, timezone

from app.modules.visualizacion_temporal.detector import Medicion
from app.modules.visualizacion_temporal.schemas import FiltrosTemporales
from app.modules.visualizacion_temporal.services import (
    etiqueta_pci_psc,
    obtener_celdas_repetidas,
    obtener_tramos_celda,
)

T0 = datetime(2026, 9, 28, 21, 24, 0, tzinfo=timezone.utc)


def medicion(segundo, *, node_id=28024, cid=203, pci=407, arfcn=700, tech="LTE"):
    return Medicion(
        id_medicion=f"m{segundo}",
        sesion_id="s",
        timestamp_medicion=T0 + timedelta(seconds=segundo),
        cid=cid,
        node_id=node_id if tech == "LTE" else None,
        psc_pci=pci,
        lac_tac=35191,
        tech=tech,
        arfcn=arfcn,
    )


class Repositorio:
    def __init__(self, mediciones):
        self.mediciones = mediciones

    def existe_sesion(self, sesion_id):
        return True

    def obtener_mediciones_filtradas(self, filtros):
        return self.mediciones


FILTROS = FiltrosTemporales(sesion_ids=["s"])

# Misma antena en dos bandas (PCI 407 en los canales 700 y 850) y una vecina con PCI 32.
CELDA_700 = dict(cid=203, pci=407, arfcn=700)
CELDA_850 = dict(cid=210, pci=407, arfcn=850)
VECINA = dict(cid=71, pci=32, arfcn=9435)


def tramo(desde, hasta, celda):
    return [medicion(s, **celda) for s in range(desde, hasta)]


# ------------------------------------------------------------------------------ rótulo


def test_el_rotulo_es_pci_en_lte_psc_en_wcdma_y_cid_solo_en_gsm():
    assert etiqueta_pci_psc("LTE", 407, 203) == "PCI 407"
    assert etiqueta_pci_psc("WCDMA", 97, 30405) == "PSC 97"
    # GSM no tiene PCI ni PSC: el CID es lo único que lo identifica.
    assert etiqueta_pci_psc("GSM", None, 11048) == "GSM CID 11048"


def test_una_celda_lte_o_wcdma_sin_pci_no_se_rotula_con_el_cid():
    assert etiqueta_pci_psc("LTE", None, 70) == "Sin PCI"
    assert etiqueta_pci_psc("WCDMA", None, 11751) == "Sin PSC"


# ------------------------------------------------------------------------------ secuencia


def test_con_eje_pci_dos_celdas_con_el_mismo_pci_comparten_altura():
    mediciones = tramo(0, 5, CELDA_700) + tramo(5, 10, CELDA_850) + tramo(10, 15, VECINA)

    salida = obtener_tramos_celda(FILTROS, eje="psc_pci", repository=Repositorio(mediciones))

    assert [t.etiqueta for t in salida.tramos] == ["PCI 407", "PCI 407", "PCI 32"]
    alturas = [t.valor_normalizado for t in salida.tramos]
    assert alturas[0] == alturas[1] != alturas[2]
    # Siguen siendo tres celdas y tres tramos: el cambio de celda no se pierde.
    assert salida.celdas_distintas == 3


def test_con_eje_eci_cada_celda_tiene_su_altura():
    mediciones = tramo(0, 5, CELDA_700) + tramo(5, 10, CELDA_850)

    salida = obtener_tramos_celda(FILTROS, eje="celda_clave", repository=Repositorio(mediciones))

    assert salida.tramos[0].valor_normalizado != salida.tramos[1].valor_normalizado
    assert salida.tramos[0].etiqueta == "LTE:7174347"


def test_el_pci_se_resuelve_por_celda_y_un_tramo_suelto_sin_pci_no_cambia_de_rotulo():
    # La celda de 700 informa su PCI, pero en un tramo de una sola medición llega vacío.
    sin_pci = dict(CELDA_700, pci=None)
    mediciones = tramo(0, 5, CELDA_700) + tramo(5, 10, VECINA) + [medicion(10, **sin_pci)]

    salida = obtener_tramos_celda(FILTROS, eje="psc_pci", repository=Repositorio(mediciones))

    assert [t.etiqueta for t in salida.tramos] == ["PCI 407", "PCI 32", "PCI 407"]
    assert salida.tramos[2].psc_pci == 407
    assert all("CID" not in t.etiqueta for t in salida.tramos)


# ------------------------------------------------------------------------------ histograma


def test_el_histograma_por_celda_trae_el_rotulo_pci_psc():
    mediciones = tramo(0, 5, CELDA_700) + [
        medicion(s, cid=11048, pci=None, arfcn=62, tech="GSM") for s in range(5, 10)
    ]

    salida = obtener_celdas_repetidas(FILTROS, repository=Repositorio(mediciones))
    por_clave = {c.celda_clave: c for c in salida.bins[0].celdas}

    assert por_clave["LTE:7174347"].etiqueta == "PCI 407"
    assert por_clave["GSM:35191:11048"].etiqueta == "GSM CID 11048"


def test_por_pci_una_racha_seguida_del_mismo_pci_es_una_sola_visita():
    # 700 → 850 (mismo PCI) → vecina → 700: el PCI 407 se deja una vez y se vuelve una vez.
    mediciones = (
        tramo(0, 5, CELDA_700)
        + tramo(5, 10, CELDA_850)
        + tramo(10, 15, VECINA)
        + tramo(15, 20, CELDA_700)
    )

    salida = obtener_celdas_repetidas(FILTROS, eje="psc_pci", repository=Repositorio(mediciones))
    por_rotulo = {c.etiqueta: c for c in salida.bins[0].celdas}

    assert set(por_rotulo) == {"PCI 407", "PCI 32"}
    assert por_rotulo["PCI 407"].n_visitas == 2
    assert por_rotulo["PCI 407"].n_mediciones == 15
    assert sorted(por_rotulo["PCI 407"].canales) == [700, 850]
    assert sorted(por_rotulo["PCI 407"].celdas_incluidas) == ["LTE:7174347", "LTE:7174354"]
    assert salida.total_celdas == 2


def test_por_celda_las_mismas_mediciones_dan_una_barra_por_celda():
    mediciones = (
        tramo(0, 5, CELDA_700)
        + tramo(5, 10, CELDA_850)
        + tramo(10, 15, VECINA)
        + tramo(15, 20, CELDA_700)
    )

    salida = obtener_celdas_repetidas(FILTROS, repository=Repositorio(mediciones))

    assert salida.total_celdas == 3
    assert {c.celda_clave: c.n_visitas for c in salida.bins[0].celdas}["LTE:7174347"] == 2
