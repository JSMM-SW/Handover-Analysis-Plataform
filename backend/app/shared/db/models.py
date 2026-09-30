"""
Modelos SQLAlchemy que mapean exactamente las tablas de `schema.sql`.

IMPORTANTE: `schema.sql` es la fuente de verdad del esquema (se aplica
manualmente en el SQL Editor de Supabase). Estos modelos NO crean tablas
(no se usa Base.metadata.create_all en producción); solo reflejan lo que
`schema.sql` ya define. Si cambias una columna o un CHECK, actualiza los
dos archivos y mantenlos sincronizados manualmente hasta que se introduzca
Alembic en una iteración futura (ver sección 11 del plan de tesis).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.shared.db.database import Base


class EtlExecution(Base):
    """Trazabilidad de cada corrida del pipeline ETL (Objetivo 5 del plan de tesis)."""

    __tablename__ = "etl_execution"

    execution_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Identity(always=True) le indica a SQLAlchemy que esta columna es
    # GENERATED ALWAYS AS IDENTITY en Postgres: la excluye del INSERT (nunca
    # manda un valor, ni NULL) y la lee de vuelta después de insertar. Un
    # Column(Integer, nullable=True) simple rompía el INSERT porque
    # SQLAlchemy sí manda NULL explícito para esos, y Postgres lo rechaza en
    # una columna GENERATED ALWAYS.
    sesion_label = Column(Integer, Identity(always=True), unique=True)
    filename = Column(Text, nullable=False)
    processing_date = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    records_read = Column(Integer, nullable=False, default=0)
    records_valid = Column(Integer, nullable=False, default=0)
    records_rejected = Column(Integer, nullable=False, default=0)
    warnings = Column(JSONB, nullable=False, default=list)
    errors = Column(JSONB, nullable=False, default=list)
    processing_time_seconds = Column(Numeric(10, 3))
    status = Column(String, nullable=False, default="pending")
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    records = relationship(
        "HandoverRecord", back_populates="execution", cascade="all, delete-orphan"
    )
    rejected_records = relationship(
        "HandoverRecordRejected", back_populates="execution", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','processing','completed','failed')", name="chk_status"
        ),
    )


class HandoverRecord(Base):
    """Dataset final limpio, consumido por los módulos de visualización y KPIs."""

    __tablename__ = "handover_record"

    id_registro = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id = Column(
        UUID(as_uuid=True),
        ForeignKey("etl_execution.execution_id", ondelete="CASCADE"),
        nullable=False,
    )

    # Guardado en UTC. Origen: xlsx combina Fecha+Hora; csv parsea sys_time.
    # Ambos en hora local America/Guayaquil (UTC-5), convertidos por el ETL.
    timestamp_medicion = Column(DateTime(timezone=True), nullable=False)

    cell_id = Column(Integer, nullable=False)

    # NULL solo posible en origen csv (centinela 2147483647 en lac_tac/arfcn).
    tac = Column(Integer, nullable=True)
    earfcn = Column(Integer, nullable=True)

    tecnologia = Column(SmallInteger, nullable=False)  # 0=sin señal, 1=LTE/4G, 2=3G/UMTS

    latitud = Column(Numeric(10, 6), nullable=False)
    longitud = Column(Numeric(10, 6), nullable=False)

    # NULL solo posible en origen csv (Network Cell Info no reporta RSRP).
    rsrp_dbm = Column(SmallInteger, nullable=True)

    # Columnas exclusivas del origen csv (Network Cell Info). NULL para xlsx,
    # y NULL también cuando el equipo reporta el centinela 2147483647 (o -1
    # para accuracy).
    node_id = Column(Integer, nullable=True)
    psc_pci = Column(Integer, nullable=True)
    rssi = Column(SmallInteger, nullable=True)
    rsrq = Column(SmallInteger, nullable=True)
    rssnr = Column(SmallInteger, nullable=True)
    accuracy = Column(SmallInteger, nullable=True)

    archivo_origen = Column(Text, nullable=False)
    hoja_origen = Column(Text, nullable=True)  # NULL en csv, que no tiene hojas
    origen_formato = Column(Text, nullable=False)  # 'xlsx' o 'csv'

    # Distancia Haversine / tiempo contra el registro anterior de la misma
    # sesión (misma hoja_origen). NULL si es el primero de su sesión, si el
    # registro actual o el anterior fueron rechazados por GPS sin fix, o si
    # la diferencia de tiempo es 0. Valores > 200 km/h se conservan con un
    # warning en vez de rechazarse (podría ser ruido de GPS).
    velocidad_kmh = Column(Numeric(6, 2), nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    execution = relationship("EtlExecution", back_populates="records")

    __table_args__ = (
        CheckConstraint("cell_id > 0", name="chk_cell_id_valido"),
        CheckConstraint("tecnologia IN (0,1,2)", name="chk_tecnologia_valida"),
        CheckConstraint("latitud BETWEEN -5 AND 2", name="chk_latitud_rango"),
        CheckConstraint("longitud BETWEEN -92 AND -75", name="chk_longitud_rango"),
        CheckConstraint("rsrp_dbm BETWEEN -140 AND -1", name="chk_rsrp_rango"),
        CheckConstraint(
            "NOT (latitud = 0 AND longitud = 0) AND NOT (latitud = -1 AND longitud = -1)",
            name="chk_gps_con_fix",
        ),
        CheckConstraint("origen_formato IN ('xlsx','csv')", name="chk_origen_formato_valido"),
    )


class HandoverRecordRejected(Base):
    """Registros descartados durante Validate/Clean, con motivo y datos crudos."""

    __tablename__ = "handover_record_rejected"

    id_rechazo = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id = Column(
        UUID(as_uuid=True),
        ForeignKey("etl_execution.execution_id", ondelete="CASCADE"),
        nullable=False,
    )
    hoja_origen = Column(Text)
    fila_excel = Column(Integer)
    motivo_rechazo = Column(Text, nullable=False)
    datos_crudos = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    execution = relationship("EtlExecution", back_populates="rejected_records")
