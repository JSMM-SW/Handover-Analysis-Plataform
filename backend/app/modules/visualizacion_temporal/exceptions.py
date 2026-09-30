"""
Excepciones de dominio del Módulo 2.

Viven dentro del módulo, no en `app.shared`, para que el aislamiento por contrato sea completo
(regla 2 de `CLAUDE.md`). El `router.py` las traduce a códigos HTTP; ninguna capa por debajo del
router conoce FastAPI.
"""


class VisualizacionTemporalError(Exception):
    """Base de los errores de dominio del módulo de visualización temporal."""


class SesionNoEncontrada(VisualizacionTemporalError):
    """La sesión (recorrido) solicitada no existe. El router la traduce a HTTP 404."""

    def __init__(self, sesion_id: str):
        self.sesion_id = sesion_id
        super().__init__(f"No existe la sesión {sesion_id}.")


class SesionSinMediciones(VisualizacionTemporalError):
    """La sesión existe pero no tiene mediciones utilizables. El router lo traduce a HTTP 422."""

    def __init__(self, sesion_id: str):
        self.sesion_id = sesion_id
        super().__init__(f"La sesión {sesion_id} no tiene mediciones con celda identificable.")


class HandoverNoEncontrado(VisualizacionTemporalError):
    """El evento de handover solicitado no existe. El router lo traduce a HTTP 404."""

    def __init__(self, id_evento: str):
        self.id_evento = id_evento
        super().__init__(f"No existe el handover {id_evento}.")


class ParametrosDeteccionInvalidos(VisualizacionTemporalError):
    """Los parámetros del algoritmo están fuera de rango. El router lo traduce a HTTP 422."""
