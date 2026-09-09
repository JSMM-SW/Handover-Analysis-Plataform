"""Manual smoke check against the configured database; performs SELECT only.

Run from the project root: venv/Scripts/python.exe tests/check_geoespacial_readonly.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import app
from app.shared.config import settings
from app.shared.db.database import get_db


def main():
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 5})

    def read_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = read_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/geoespacial/ejecuciones")
            print("Executions HTTP:", response.status_code)
            if response.status_code != 200:
                return 1
            executions = response.json()
            print("Completed executions:", len(executions))
            if not executions:
                return 0
            execution_id = executions[0]["execution_id"]
            response = client.get(f"/api/v1/geoespacial/ejecuciones/{execution_id}/hojas")
            assert response.status_code == 200
            sheets = response.json()
            print("Sheets:", len(sheets))
            for sheet in sheets:
                params = {"execution_id": execution_id, "hoja": sheet}
                response = client.get("/api/v1/geoespacial/mediciones", params=params)
                assert response.status_code == 200, "Measurement endpoint failed"
                data = response.json()
                assert data["total"] == len(data["mediciones"])
                assert all(p["hoja_origen"] == sheet for p in data["mediciones"])
                print("Sheet points / segments:", data["total"], len(data["tramos"]))
                if data["mediciones"]:
                    cell = data["mediciones"][0]["cell_id"]
                    filtered = client.get("/api/v1/geoespacial/mediciones", params=params | {"cell_id": cell})
                    assert filtered.status_code == 200
                    assert all(p["cell_id"] == cell for p in filtered.json()["mediciones"])
        print("Read-only geospatial smoke check OK")
        return 0
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
