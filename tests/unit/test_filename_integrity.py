"""Prueba de regresión para el incidente descrito en el diagnóstico de
reconciliación: `etl_execution.filename` / `handover_record.archivo_origen`
aparecieron con un UUID en vez del nombre real en algunas filas históricas.

Investigado y confirmado: NO fue un bug de código. `handle_upload` siempre
ha preservado `original_filename` tal como llega, sin tocarlo; el incidente
fue causado por una prueba manual (Playwright `setInputFiles` apuntando a un
archivo en disco que ya tenía el prefijo UUID de una subida anterior), que
hizo que el propio navegador reportara ese nombre como "el archivo
seleccionado". Esta prueba demuestra que el sistema nunca antepone ni
deriva un UUID sobre `original_filename`/`archivo_origen`: los devuelve
exactamente como se los dieron, incluso en el caso adversarial de un
nombre que ya parece tener un UUID (que es justo lo que ocurrió).
"""

from app.modules.ingesta.services import handle_upload
from app.shared.config import Settings


def test_handle_upload_preserves_arbitrary_filename_verbatim(tmp_path, sample_handover_xlsx_bytes):
    settings = Settings(data_input_dir=tmp_path / "input")

    # Nombre deliberadamente "de riesgo": ya contiene un UUID, como el
    # archivo que causó el incidente real.
    risky_filename = "5db4d5d9-6ac0-4044-bda2-c6770c50a4c1_Datos_Tesis.xlsx"

    response = handle_upload(risky_filename, sample_handover_xlsx_bytes, settings)

    # original_filename debe ser EXACTAMENTE lo que se subió, sin que el
    # sistema le anteponga un uuid propio ni lo modifique de ninguna forma.
    assert response.original_filename == risky_filename

    # stored_filename SÍ lleva un uuid propio (el de esta subida, para no
    # colisionar en disco) — pero es un campo interno, nunca se usa como
    # archivo_origen/filename persistido.
    assert response.stored_filename != risky_filename
    assert response.stored_filename.endswith(f"_{risky_filename}")


def test_handle_upload_preserves_filename_with_space(tmp_path, sample_handover_xlsx_bytes):
    """El otro caso real encontrado en el diagnóstico: nombres con espacios
    (ej. 'Datos Tesis.xlsx' vs 'Datos_Tesis.xlsx') no son un bug — el
    sistema los preserva tal cual, sin normalizar espacios ni guiones."""
    settings = Settings(data_input_dir=tmp_path / "input")

    filename_with_space = "Datos Tesis.xlsx"
    response = handle_upload(filename_with_space, sample_handover_xlsx_bytes, settings)

    assert response.original_filename == filename_with_space
