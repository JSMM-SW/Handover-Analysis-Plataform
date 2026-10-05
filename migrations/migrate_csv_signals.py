"""Back up affected tables, apply migration 007 and restore original CSV signals.

Run from the project root with the virtualenv Python. No writes without --apply.
Backups contain private measurements and are excluded from Git.
"""
import argparse
import gzip
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.shared.config import settings
from app.modules.ingesta.services import run_pipeline


def observation_key(row):
    return (row["timestamp_medicion"], row["cell_id"], row.get("node_id"), row.get("earfcn"))


def read_originals(sessions, directories):
    files = [path for directory in directories for path in directory.glob("*.csv")]
    originals = {}
    for execution_id, filename in sessions:
        candidates = [p for p in files if p.name == filename or p.name.endswith("_" + filename)]
        if not candidates:
            print(f"Original unavailable: {filename}")
            continue
        hashes = {hashlib.sha256(p.read_bytes()).hexdigest() for p in candidates}
        if len(hashes) != 1:
            raise RuntimeError(f"Different originals share a filename: {filename}")
        result = run_pipeline(candidates[0], filename, "migration-preview")
        index = defaultdict(list)
        for row in result.valid_records:
            index[observation_key(row)].append(row)
        originals[execution_id] = index
    return originals


def backup_table(conn, table, directory):
    path = directory / f"{table}.jsonl.gz"
    count = 0
    with gzip.open(path, "wt", encoding="utf-8") as output:
        for row in conn.execute(text(f"SELECT row_to_json(t)::text FROM {table} t")):
            output.write(row[0] + "\n")
            count += 1
    with gzip.open(path, "rt", encoding="utf-8") as backup:
        assert sum(1 for line in backup if json.loads(line)) == count
    return {"rows": count, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--raw-dir", type=Path, action="append", default=[])
    args = parser.parse_args()
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        sessions = conn.execute(text("SELECT execution_id, filename FROM etl_execution WHERE status='completed'" )).all()
    originals = read_originals(sessions, [ROOT / "data/input", *args.raw_dir])
    print(f"Original CSV available for {len(originals)}/{len(sessions)} sessions")
    if not args.apply:
        print("Preview only. Use --apply to back up and migrate.")
        return
    directory = ROOT / "backups" / ("csv_signals_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {"status": "backup", "tables": {}}
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '15s'"))
        conn.execute(text("LOCK TABLE handover_record, etl_execution, eventos_handover IN ACCESS EXCLUSIVE MODE"))
        for table in ("handover_record", "etl_execution", "eventos_handover"):
            manifest["tables"][table] = backup_table(conn, table, directory)
        manifest["columns"] = [dict(row) for row in conn.execute(text(
            "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='handover_record' ORDER BY ordinal_position"
        )).mappings()]
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Verified backup: {directory}", flush=True)
        # The transaction is owned by SQLAlchemy; exclude the SQL file's wrapper.
        sql = (ROOT / "schema_migration_007_csv_signals.sql").read_text(encoding="utf-8")
        sql = sql.replace("BEGIN;", "").replace("COMMIT;", "")
        conn.exec_driver_sql(sql)
        updates = []
        for row in conn.execute(text("SELECT id_registro, execution_id, timestamp_medicion, cell_id, node_id, earfcn, report_index FROM handover_record WHERE origen_formato='csv'")).mappings():
            candidates = originals.get(row["execution_id"], {}).get(observation_key(row), [])
            if row["report_index"] is not None:
                candidates = [c for c in candidates if c["report_index"] == row["report_index"]]
            signals = {(c["rssi"], c["rsrp"], c["rsrq"], c["rssnr"]) for c in candidates}
            if len(signals) == 1:
                updates.append((row["id_registro"], *next(iter(signals))))
        conn.execute(text("CREATE TEMP TABLE csv_signal_updates (id uuid PRIMARY KEY, rssi smallint, strongest smallint, rsrq smallint, rssnr smallint) ON COMMIT DROP"))
        with conn.connection.driver_connection.cursor() as cursor:
            with cursor.copy("COPY csv_signal_updates FROM STDIN") as copy:
                for values in updates:
                    copy.write_row(values)
        conn.execute(text("UPDATE handover_record h SET rssi=u.rssi, rssi_strongest=u.strongest, rsrq=u.rsrq, rssnr=u.rssnr FROM csv_signal_updates u WHERE h.id_registro=u.id"))
        # Stored event deltas may have used the old, unsupported interpretation.
        conn.execute(text("UPDATE eventos_handover SET delta_rsrp_db=NULL, delta_rscp_db=NULL WHERE sesion_id IN (SELECT execution_id FROM etl_execution)"))
        rsrp_sql = (ROOT / "schema_migration_008_netmonitor_rsrp.sql").read_text(encoding="utf-8")
        conn.exec_driver_sql(rsrp_sql.replace("BEGIN;", "").replace("COMMIT;", ""))
        rename_sql = (ROOT / "schema_migration_009_rsrp_column.sql").read_text(encoding="utf-8")
        conn.exec_driver_sql(rename_sql.replace("BEGIN;", "").replace("COMMIT;", ""))
        count = conn.execute(text("SELECT count(*) FROM handover_record")).scalar_one()
        assert count == manifest["tables"]["handover_record"]["rows"]
        manifest.update(status="committed", restored_from_csv=len(updates), records=count)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"backup": str(directory), "records": count, "restored_from_csv": len(updates)}))


if __name__ == "__main__":
    main()
