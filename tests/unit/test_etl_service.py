from app.shared.exceptions import SchemaValidationError
from app.modules.ingesta.etl.constants import (
    MOTIVO_CID_CENTINELA,
    MOTIVO_DUPLICADO,
)
from app.modules.ingesta.services import run_pipeline
import pytest


def test_pipeline_csv_end_to_end_with_known_rows(tmp_path, sample_handover_csv_bytes):
    path = tmp_path / "handover.csv"
    path.write_bytes(sample_handover_csv_bytes)

    result = run_pipeline(path, archivo_origen="handover.csv", execution_id="test-exec")

    # 5 filas: válida LTE, válida UMTS con rssnr centinela, cid centinela
    # (rechazada), GSM/GPRS con gps sin fix (YA NO se rechaza desde
    # Session_43: se conserva con latitud/longitud NULL), duplicado exacto
    # de la primera.
    assert result.records_read == 5
    assert len(result.valid_records) == 3
    assert len(result.rejected_records) == 2

    motivos = {r["motivo_rechazo"] for r in result.rejected_records}
    assert motivos == {MOTIVO_CID_CENTINELA, MOTIVO_DUPLICADO}

    valid_by_tecnologia = {r["tecnologia"]: r for r in result.valid_records}
    assert valid_by_tecnologia[1]["cell_id"] == 192  # LTE
    assert valid_by_tecnologia[1]["rssi"] == -90  # tech=LTE -> rssi va a rsrp_dbm
    assert valid_by_tecnologia[1]["origen_formato"] == "csv"
    assert valid_by_tecnologia[1]["hoja_origen"] is None
    assert valid_by_tecnologia[1]["cid"] == 192
    assert valid_by_tecnologia[1]["report_index"] == 0
    assert valid_by_tecnologia[1]["net_type"] == "LTE"
    assert valid_by_tecnologia[1]["tech"] == "LTE"

    assert valid_by_tecnologia[2]["cell_id"] == 29296  # UMTS/WCDMA -> 3G
    assert valid_by_tecnologia[2]["rssnr"] is None  # centinela nuleado
    assert valid_by_tecnologia[2]["rssi"] == -79  # tech=WCDMA -> rssi va a rscp_dbm

    # GSM/GPRS con gps sin fix: se conserva (ya no se rechaza), latitud y
    # longitud quedan NULL, el resto del registro (cid/tech/rssi_dbm) intacto.
    assert valid_by_tecnologia[3]["cell_id"] == 209
    assert valid_by_tecnologia[3]["latitud"] is None
    assert valid_by_tecnologia[3]["longitud"] is None
    assert valid_by_tecnologia[3]["rssi"] == -107  # tech=GSM -> rssi va a rssi_dbm
    assert valid_by_tecnologia[3]["net_type"] == "GPRS"
    assert valid_by_tecnologia[3]["tech"] == "GSM"
    assert valid_by_tecnologia[3]["velocidad_kmh"] is None  # sin posición, no se puede calcular

    assert any("rssnr" in w for w in result.warnings)
    assert any("gps sin fix" in w for w in result.warnings)


@pytest.mark.parametrize('strongest, expected', [(-77, -77), (2147483647, None)])
def test_pipeline_preserves_four_signals_without_relabeling(tmp_path, sample_handover_csv_bytes, strongest, expected):
    lines = sample_handover_csv_bytes.decode('utf-8').splitlines()
    lines = [lines[0] + ';rssi_strongest'] + [line + f';{strongest}' for line in lines[1:]]
    path = tmp_path / 'session.csv'
    path.write_text('\n'.join(lines), encoding='utf-8')
    result = run_pipeline(path, path.name, 'test')
    for row in result.valid_records:
        assert row['rsrp'] == expected
        assert not {'rsrp_dbm', 'rscp_dbm', 'rssi_dbm'} & row.keys()
    assert [r['rssi'] for r in result.valid_records] == [-90, -79, -107]
