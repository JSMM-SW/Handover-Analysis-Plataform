"""
Downsampling LTTB — *Largest Triangle Three Buckets*.

Por qué hace falta
------------------
El dataset real tiene 86.398 mediciones por sesión (24 h a 1 Hz). Enviarlas crudas al navegador
serían varios megabytes por serie y ECharts no puede dibujar tantos puntos de forma fluida. Pero
un muestreo ingenuo (una de cada N) **borra los picos y valles**, que es justo lo que interesa
mirar alrededor de un handover.

LTTB conserva la **forma visual** de la curva: divide la serie en tantos cubos como puntos se
quieran, y de cada cubo elige el punto que forma el triángulo de mayor área con el punto ya
elegido del cubo anterior y el promedio del cubo siguiente. Los extremos y los picos sobreviven.

Referencia: Sveinn Steinarsson (2013), *Downsampling Time Series for Visual Representation*,
Universidad de Islandia.

Este módulo es **puro**: no importa nada del proyecto y no hace I/O.
"""

from __future__ import annotations

import math

#: Mínimo de puntos que tiene sentido pedir: los dos extremos más uno intermedio.
MINIMO_PUNTOS_LTTB = 3


def _rellenar_hacia_delante(valores: list[float | None]) -> list[float]:
    """Sustituye los `None` por el último valor conocido, para poder calcular áreas.

    En datos reales muchos parámetros faltan la mayor parte del tiempo (RSRQ llega al 16 % de
    cobertura), así que la serie de referencia puede tener huecos internos. El relleno solo se usa
    para **elegir qué índices conservar**; los valores que se devuelven al cliente siguen siendo
    los originales, con sus `None` intactos.
    """
    rellenados: list[float] = []
    ultimo = 0.0
    visto = False

    for valor in valores:
        if valor is not None:
            ultimo = float(valor)
            visto = True
        rellenados.append(ultimo if visto else 0.0)

    # Si la serie empieza con None, se rellena hacia atrás con el primer valor conocido.
    if visto:
        primero = next((v for v in valores if v is not None), None)
        if primero is not None:
            for i, valor in enumerate(valores):
                if valor is not None:
                    break
                rellenados[i] = float(primero)

    return rellenados


def seleccionar_indices_lttb(
    xs: list[float],
    ys: list[float | None],
    max_puntos: int,
) -> list[int]:
    """Devuelve los índices que conservan la forma de la serie.

    Se devuelven **índices** y no puntos a propósito: el endpoint de series envía varios
    parámetros en arrays paralelos, y todos deben quedar alineados con el mismo eje de tiempos.
    Se eligen una vez sobre una serie de referencia y se aplican a todas.

    Garantías:

    - El primer y el último punto siempre se conservan.
    - Nunca se devuelven más de `max_puntos` índices.
    - Los índices salen ordenados y sin repetir.
    - Es determinista: la misma entrada da siempre la misma salida.

    Si la serie ya cabe en `max_puntos`, se devuelve entera sin tocar.
    """
    n = len(xs)
    if n != len(ys):
        raise ValueError("xs e ys deben tener la misma longitud")
    if max_puntos < 1:
        raise ValueError("max_puntos debe ser >= 1")

    if n <= max_puntos:
        return list(range(n))
    if max_puntos == 1:
        return [0]
    if max_puntos == 2:
        return [0, n - 1]

    valores = _rellenar_hacia_delante(ys)

    seleccionados = [0]
    tamano_cubo = (n - 2) / (max_puntos - 2)
    indice_anterior = 0

    for cubo in range(max_puntos - 2):
        # Promedio del cubo siguiente: el tercer vértice del triángulo.
        inicio_siguiente = math.floor((cubo + 1) * tamano_cubo) + 1
        fin_siguiente = min(math.floor((cubo + 2) * tamano_cubo) + 1, n)

        if inicio_siguiente >= fin_siguiente:
            inicio_siguiente, fin_siguiente = n - 1, n

        cuenta = fin_siguiente - inicio_siguiente
        x_promedio = sum(xs[inicio_siguiente:fin_siguiente]) / cuenta
        y_promedio = sum(valores[inicio_siguiente:fin_siguiente]) / cuenta

        # Cubo actual: se busca en él el punto de área máxima.
        inicio = math.floor(cubo * tamano_cubo) + 1
        fin = min(math.floor((cubo + 1) * tamano_cubo) + 1, n - 1)
        if inicio >= fin:
            continue

        x_ancla, y_ancla = xs[indice_anterior], valores[indice_anterior]

        mejor_indice = inicio
        mejor_area = -1.0
        for indice in range(inicio, fin):
            area = abs(
                (x_ancla - x_promedio) * (valores[indice] - y_ancla)
                - (x_ancla - xs[indice]) * (y_promedio - y_ancla)
            )
            if area > mejor_area:
                mejor_area = area
                mejor_indice = indice

        seleccionados.append(mejor_indice)
        indice_anterior = mejor_indice

    seleccionados.append(n - 1)

    # El reparto en cubos puede repetir un índice en los bordes; se normaliza.
    return sorted(set(seleccionados))


def indice_de_mejor_cobertura(series: dict[str, list[float | None]]) -> str | None:
    """Nombre de la serie con más valores medidos, para usarla como referencia del muestreo.

    Elegir una serie casi vacía como referencia haría que LTTB decidiera sobre ruido. Con datos
    reales importa: RSRP llega al 90 % de cobertura y RSRQ al 16 %.
    """
    if not series:
        return None

    # Más cobertura primero; a igualdad, el primero por orden alfabético. El desempate debe ser
    # determinista o el muestreo cambiaría entre peticiones idénticas.
    return min(
        series,
        key=lambda nombre: (
            -sum(1 for valor in series[nombre] if valor is not None),
            nombre,
        ),
    )
