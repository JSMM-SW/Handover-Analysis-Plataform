"""Manual smoke check of real saved sessions. Database transaction is read-only."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.shared.config import settings
from app.modules.visualizacion_geoespacial.repository import GeoespacialRepository
from app.modules.visualizacion_geoespacial.services import prepare_map


def main():
    engine = create_engine(settings.database_url, connect_args={'connect_timeout': 5})
    try:
        with Session(engine) as db:
            db.execute(text('SET TRANSACTION READ ONLY'))
            repository = GeoespacialRepository(db)
            executions = repository.executions()
            selected = [row['execution_id'] for row in executions]
            records = repository.measurements(selected, None)
            result = prepare_map(records)
            assert len(result.radios_base) <= result.resumen_radios_base.grupos_evaluados
            result.model_dump_json()  # Validate JSON serialization of actual data.
            for execution in executions:
                stations = [p for p in result.radios_base if p.execution_id == execution['execution_id']]
                print(execution['filename'], str(execution['execution_id']), 'estimaciones:', len(stations))
            print('Mediciones:', result.total, 'Handovers:', result.total_handovers)
            print('Resumen:', result.resumen_radios_base.model_dump_json())
            print('Estimaciones totales:', len(result.radios_base))
            print('Solo lectura: no se guardaron estimaciones.')
    finally:
        engine.dispose()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Comprobacion fallida:', type(exc).__name__)
        sys.exit(1)
