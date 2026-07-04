"""
operations_db.py
JRS Central Operations Intelligence System

Almacen estructurado de eventos operativos (la FUENTE DE LA VERDAD).
- SQLite en el volumen persistente de Railway (/data/operations.db).
- Cada correo o crew update que Joe procesa deja aqui un registro
  consultable por proyecto y por fecha.
- Disenado para el patron HIBRIDO acordado:
    * Esta tabla es la fuente de la verdad (consultas exactas y deterministas).
    * ChromaDB (collection_jrs_history) recibe una copia para busqueda semantica.
    * event_uid es un ID determinista que se REUTILIZA como ID en ChromaDB,
      asi que upsert reemplaza en vez de duplicar (misma leccion aprendida
      que ya aplicas en la carga de conocimiento).
    * chroma_synced marca si la copia semantica ya se escribio; si el write a
      ChromaDB falla, SQLite conserva el dato y un reintento puede sincronizar
      despues. SQLite manda; ChromaDB es un indice derivado.

ALCANCE: este archivo es el PASO 1 (esquema + capa de acceso).
Todavia NO integra el agent loop (Paso 2: write-back) ni la herramienta de
recuperacion de Joe (Paso 3). Se puede correr y probar de forma aislada.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional


# ---------------------------------------------------------------------------
# Resolucion de ruta: volumen de Railway en produccion, archivo local en dev
# ---------------------------------------------------------------------------
def _resolve_db_path() -> str:
    explicit = os.getenv("OPERATIONS_DB_PATH")
    if explicit:
        return explicit
    # En Railway el volumen persistente vive en /data
    if Path("/data").is_dir():
        return "/data/operations.db"
    # Desarrollo local (Windows / venv): archivo junto a este modulo
    return str(Path(__file__).resolve().parent / "operations.db")


OPERATIONS_DB_PATH = _resolve_db_path()


# ---------------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS operational_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_uid       TEXT    NOT NULL UNIQUE,    -- ID determinista (= ID en ChromaDB)

    -- Clasificacion / origen
    event_type      TEXT    NOT NULL,           -- crew_update | client_email | vendor | inspection | report | other
    source          TEXT    NOT NULL DEFAULT 'gmail',
    source_id       TEXT,                        -- p.ej. Gmail message id

    -- Llaves de negocio (dimensiones filtrables)
    project_name    TEXT,                        -- "TJ Maxx - Hattiesburg, MS"
    client          TEXT,                        -- "TJ Maxx"
    client_norm     TEXT,                        -- "tj maxx" (filtrar sin importar mayusculas)
    store_number    TEXT,
    city            TEXT,
    state           TEXT,                        -- 2 letras: MS, TX...

    -- Estado y tiempo
    status          TEXT    DEFAULT 'unknown',   -- in_progress | completed | on_hold | unknown
    event_date      TEXT,                        -- YYYY-MM-DD: DIA de las actividades (NULL si el correo no lo dice)
    received_at     TEXT    NOT NULL,            -- ISO datetime en que Joe lo proceso

    -- Contenido
    summary         TEXT,                        -- resumen corto que genera Joe
    activities      TEXT,                        -- JSON array de actividades finales / del dia
    team_members    TEXT,                        -- JSON array de miembros del equipo
    crew_leader     TEXT,
    severity        TEXT,                        -- CRITICAL | HIGH | MEDIUM | LOW | NULL
    raw_text        TEXT,                        -- cuerpo original (fuente para re-leer; nunca inventar)

    -- Flexibilidad y sincronizacion con ChromaDB
    metadata_json   TEXT    DEFAULT '{}',        -- extras: PO, lat/long (mapa de burbujas futuro), etc.
    chroma_synced   INTEGER NOT NULL DEFAULT 0,  -- 0 = falta copiar a ChromaDB, 1 = ya copiado

    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

-- Indices para los patrones de consulta de Joe / Richard
CREATE INDEX IF NOT EXISTS idx_events_project   ON operational_events (project_name);
CREATE INDEX IF NOT EXISTS idx_events_date      ON operational_events (event_date);
CREATE INDEX IF NOT EXISTS idx_events_proj_date ON operational_events (project_name, event_date);
CREATE INDEX IF NOT EXISTS idx_events_client    ON operational_events (client_norm);
CREATE INDEX IF NOT EXISTS idx_events_type      ON operational_events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_status    ON operational_events (status);
CREATE INDEX IF NOT EXISTS idx_events_state     ON operational_events (state);
CREATE INDEX IF NOT EXISTS idx_events_unsynced  ON operational_events (chroma_synced);
"""


# ---------------------------------------------------------------------------
# Conexion (PRAGMAs seguros para agente + dashboard sobre el mismo volumen)
# ---------------------------------------------------------------------------
@contextmanager
def _connect(db_path: str = OPERATIONS_DB_PATH) -> Iterator[sqlite3.Connection]:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")    # lecturas del dashboard sin bloquear escritura del agente
        conn.execute("PRAGMA busy_timeout=30000;")  # espera en vez de fallar con 'database is locked'
        conn.execute("PRAGMA foreign_keys=ON;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_operations_db(db_path: str = OPERATIONS_DB_PATH) -> None:
    """Crea la base y las tablas si no existen. Idempotente."""
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)


# ---------------------------------------------------------------------------
# Contrato del registro
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_event_uid(source: str, source_id: str, discriminator: str = "") -> str:
    """
    ID determinista y estable. Reprocesar el mismo correo produce el mismo UID,
    asi que upsert reemplaza en vez de duplicar (en SQLite y en ChromaDB).
    """
    base = f"{source}:{source_id}:{discriminator}".strip(":")
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    return f"evt-{digest}"


@dataclass
class OperationalEvent:
    """Contrato del registro. El Paso 2 (write-back) llenara esto desde el agent loop."""
    event_type: str
    source_id: str
    source: str = "gmail"
    project_name: Optional[str] = None
    client: Optional[str] = None
    store_number: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    status: str = "unknown"
    event_date: Optional[str] = None
    summary: Optional[str] = None
    activities: list = field(default_factory=list)
    team_members: list = field(default_factory=list)
    crew_leader: Optional[str] = None
    severity: Optional[str] = None
    raw_text: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def event_uid(self) -> str:
        return make_event_uid(self.source, self.source_id)

    @property
    def client_norm(self) -> Optional[str]:
        return self.client.strip().lower() if self.client else None


# ---------------------------------------------------------------------------
# Escritura (upsert) y lectura
# ---------------------------------------------------------------------------
def upsert_event(event: OperationalEvent, db_path: str = OPERATIONS_DB_PATH) -> str:
    """
    Inserta o actualiza un evento por su UID determinista.
    Al re-escribir marca chroma_synced=0 para que la copia semantica se
    regenere. received_at se fija en el primer insert y NO se toca despues.
    Devuelve el event_uid.
    """
    uid = event.event_uid()
    now = _now_iso()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO operational_events (
                event_uid, event_type, source, source_id,
                project_name, client, client_norm, store_number, city, state,
                status, event_date, received_at,
                summary, activities, team_members, crew_leader, severity, raw_text,
                metadata_json, chroma_synced, created_at, updated_at
            ) VALUES (
                :event_uid, :event_type, :source, :source_id,
                :project_name, :client, :client_norm, :store_number, :city, :state,
                :status, :event_date, :now,
                :summary, :activities, :team_members, :crew_leader, :severity, :raw_text,
                :metadata_json, 0, :now, :now
            )
            ON CONFLICT(event_uid) DO UPDATE SET
                event_type    = excluded.event_type,
                project_name  = excluded.project_name,
                client        = excluded.client,
                client_norm   = excluded.client_norm,
                store_number  = excluded.store_number,
                city          = excluded.city,
                state         = excluded.state,
                status        = excluded.status,
                event_date    = excluded.event_date,
                summary       = excluded.summary,
                activities    = excluded.activities,
                team_members  = excluded.team_members,
                crew_leader   = excluded.crew_leader,
                severity      = excluded.severity,
                raw_text      = excluded.raw_text,
                metadata_json = excluded.metadata_json,
                chroma_synced = 0,
                updated_at    = excluded.updated_at
            """,
            {
                "event_uid": uid,
                "event_type": event.event_type,
                "source": event.source,
                "source_id": event.source_id,
                "project_name": event.project_name,
                "client": event.client,
                "client_norm": event.client_norm,
                "store_number": event.store_number,
                "city": event.city,
                "state": event.state,
                "status": event.status,
                "event_date": event.event_date,
                "summary": event.summary,
                "activities": json.dumps(event.activities, ensure_ascii=False),
                "team_members": json.dumps(event.team_members, ensure_ascii=False),
                "crew_leader": event.crew_leader,
                "severity": event.severity,
                "raw_text": event.raw_text,
                "metadata_json": json.dumps(event.metadata, ensure_ascii=False),
                "now": now,
            },
        )
    return uid


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for k in ("activities", "team_members"):
        try:
            d[k] = json.loads(d[k]) if d[k] else []
        except (json.JSONDecodeError, TypeError):
            d[k] = []
    try:
        d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        d["metadata"] = {}
    return d


def get_events(
    project_name: Optional[str] = None,
    event_date: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client: Optional[str] = None,
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db_path: str = OPERATIONS_DB_PATH,
) -> list[dict]:
    """
    Consulta determinista. Es la base de la herramienta de recuperacion de Joe
    (Paso 3). Filtra por proyecto, fecha exacta o rango, cliente, tipo y estatus.
    """
    clauses: list[str] = []
    params: dict = {}
    if project_name:
        clauses.append("project_name = :project_name")
        params["project_name"] = project_name
    if event_date:
        clauses.append("event_date = :event_date")
        params["event_date"] = event_date
    if date_from:
        clauses.append("event_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        clauses.append("event_date <= :date_to")
        params["date_to"] = date_to
    if client:
        clauses.append("client_norm = :client_norm")
        params["client_norm"] = client.strip().lower()
    if event_type:
        clauses.append("event_type = :event_type")
        params["event_type"] = event_type
    if status:
        clauses.append("status = :status")
        params["status"] = status

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = (
        f"SELECT * FROM operational_events {where} "
        f"ORDER BY event_date DESC, received_at DESC LIMIT :limit"
    )
    params["limit"] = limit
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_pending_chroma_sync(limit: int = 100, db_path: str = OPERATIONS_DB_PATH) -> list[dict]:
    """Paso 2: eventos que aun no se copiaron a ChromaDB (chroma_synced = 0)."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM operational_events WHERE chroma_synced = 0 "
            "ORDER BY id ASC LIMIT :limit",
            {"limit": limit},
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def mark_synced(event_uids: list[str], db_path: str = OPERATIONS_DB_PATH) -> None:
    """Paso 2: tras copiar a ChromaDB, marca los eventos como sincronizados."""
    if not event_uids:
        return
    with _connect(db_path) as conn:
        conn.executemany(
            "UPDATE operational_events SET chroma_synced = 1, updated_at = ? WHERE event_uid = ?",
            [(_now_iso(), uid) for uid in event_uids],
        )


# ---------------------------------------------------------------------------
# Prueba local (validar antes de integrar con el agente)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_operations_db()
    print(f"Base lista en: {OPERATIONS_DB_PATH}")

    sample = OperationalEvent(
        event_type="crew_update",
        source_id="demo-msg-001",
        project_name="TJ Maxx - Hattiesburg, MS",
        client="TJ Maxx",
        store_number="1420",
        city="Hattiesburg",
        state="MS",
        status="completed",
        event_date="2026-07-03",
        summary="Cierre de proyecto: punch list aprobada.",
        activities=["Instalacion final de senaletica", "Limpieza y entrega", "Fotos de cierre"],
        team_members=["J. Ramirez (lead)", "M. Colon", "A. Diaz"],
        crew_leader="J. Ramirez",
        severity=None,
        raw_text="Jefe, terminamos TJ Maxx Hattiesburg. Punch list aprobada, tienda entregada.",
    )

    uid = upsert_event(sample)
    print(f"Evento guardado. UID: {uid}")

    # Idempotencia: re-escribir el mismo source_id NO debe duplicar
    upsert_event(sample)

    results = get_events(project_name="TJ Maxx - Hattiesburg, MS", event_date="2026-07-03")
    print(f"Filas para ese proyecto/fecha: {len(results)}")
    for row in results:
        print(json.dumps(row, ensure_ascii=False, indent=2))

    pending = get_pending_chroma_sync()
    print(f"Pendientes de copiar a ChromaDB: {len(pending)}")
