"""
Migración de datos históricos de GLIMS desde Local a Azure.
Filtros:
- glims_samples: date_received <= '2025-12-31'
- glims_*_results: sample_id NOT LIKE 'S26-%'
"""

import os
import json
import logging
import argparse
from datetime import datetime, timezone
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

load_dotenv()

TABLES_RESULTS = [
    "glims_cn_results",
    "glims_hm_results",
    "glims_tp_results",
    "glims_mb_results",
    "glims_rs_results",
    "glims_wa_results",
    "glims_mc_results",
    "glims_pn_results",
    "glims_ffm_results",
    "glims_lw_results",
    "glims_ho_results"
]

def get_local_engine():
    """Conexión a la base de datos local (Origen)."""
    host = os.getenv("LOCAL_POSTGRES_HOST")
    port = os.getenv("LOCAL_POSTGRES_PORT")
    db = os.getenv("LOCAL_POSTGRES_DB")
    user = os.getenv("LOCAL_POSTGRES_USER")
    pw = os.getenv("LOCAL_POSTGRES_PASSWORD")
    return create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}")

def get_azure_engine():
    """Conexión a la base de datos de Azure (Destino)."""
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    db = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    pw = os.getenv("POSTGRES_PASSWORD")
    
    # Validación de seguridad: no permitir Azure == Local por error
    local_host = os.getenv("LOCAL_POSTGRES_HOST")
    if host == local_host and os.getenv("POSTGRES_DB") == os.getenv("LOCAL_POSTGRES_DB"):
        LOGGER.warning("POSTGRES_* apunta a la misma BD que LOCAL_POSTGRES_*. ¿Estás en modo local?")
        
    return create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}")

def migrate_table(src_engine, dst_engine, table_name, query, dry_run=True, batch_size=100):
    LOGGER.info(f"--- Migrando tabla: {table_name} ---")
    
    # 1. Leer de Local
    with src_engine.connect() as src_conn:
        result = src_conn.execute(text(query))
        rows = []
        LOGGER.info(f"Convirtiendo registros de {table_name} a formato dict...")
        for i, row in enumerate(result):
            if i % 1000 == 0 and i > 0:
                LOGGER.info(f"Convertidos {i} registros...")
            r = dict(row._mapping)
            # Normalizar datetimes (Azure a veces tiene problemas con TZs mixtas)
            # Y convertir dicts a JSON strings para psycopg2
            for k, v in r.items():
                if isinstance(v, datetime) and v.tzinfo is not None:
                    r[k] = v.astimezone(timezone.utc).replace(tzinfo=None)
                elif isinstance(v, dict):
                    r[k] = json.dumps(v)
            rows.append(r)
    
    LOGGER.info(f"Conversión completa. Total: {len(rows)} registros.")
    
    if not rows:
        LOGGER.info(f"No hay registros que cumplan los filtros para {table_name}.")
        return 0

    LOGGER.info(f"Encontrados {len(rows)} registros para migrar.")
    
    if dry_run:
        LOGGER.info(f"[DRY-RUN] Se insertarían/actualizarían {len(rows)} registros en {table_name}.")
        return len(rows)

    # 2. Insertar en Azure
    cols = list(rows[0].keys())
    
    # Determinar estrategia de ON CONFLICT
    pk_map = {
        "glims_samples": "sample_id",
        "glims_dispensaries": "id"
    }
    pk = pk_map.get(table_name, "sample_id")
    
    update_parts = [f"{c} = EXCLUDED.{c}" for c in cols if c not in (pk, "updated_at")]
    sql = f"""
        INSERT INTO {table_name} ({", ".join(cols)})
        VALUES ({", ".join(f":{c}" for c in cols)})
        ON CONFLICT ({pk}) DO UPDATE SET
            {", ".join(update_parts)},
            updated_at = now()
    """
    
    # Para resultados, la estrategia es DO NOTHING
    if table_name not in ["glims_samples", "glims_dispensaries"]:
        sql = f"""
            INSERT INTO {table_name} ({", ".join(cols)})
            VALUES ({", ".join(f":{c}" for c in cols)})
            ON CONFLICT ({pk}) DO NOTHING
        """

    total_inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        try:
            LOGGER.info(f"Ejecutando inserción de batch ({len(batch)} registros) en {table_name}...")
            # En SQLAlchemy 2.0, usamos commit() explícito si no usamos .begin()
            with dst_engine.begin() as conn:
                conn.execute(text(sql), batch)
            total_inserted += len(batch)
            LOGGER.info(f"Éxito: {total_inserted}/{len(rows)}...")
        except SQLAlchemyError as e:
            LOGGER.warning(f"Error en batch de {table_name}: {e}. Reintentando fila por fila...")
            for row in batch:
                try:
                    with dst_engine.begin() as conn:
                        conn.execute(text(sql), [row])
                    total_inserted += 1
                except SQLAlchemyError as row_e:
                    LOGGER.error(f"Falla crítica en fila {row.get('sample_id') or row.get('id')}: {row_e}")
                    continue
    
    return total_inserted

def main(dry_run=True):
    src_engine = get_local_engine()
    dst_engine = get_azure_engine()
    
    summary = {"tables": {}, "total_records": 0}
    
    # --- 0. Migrar Dispensaries (Dependencia para FK) ---
    query_disp = "SELECT * FROM glims_dispensaries"
    try:
        count = migrate_table(src_engine, dst_engine, "glims_dispensaries", query_disp, dry_run)
        summary["tables"]["glims_dispensaries"] = count
        summary["total_records"] += count
    except Exception as e:
        LOGGER.error(f"Fallo migrando glims_dispensaries: {e}")
        summary["tables"]["glims_dispensaries"] = f"Error: {e}"

    # --- 1. Migrar Samples ---
    query_samples = """
        SELECT * FROM glims_samples 
        WHERE date_received <= '2025-12-31'
    """
    try:
        count = migrate_table(src_engine, dst_engine, "glims_samples", query_samples, dry_run)
        summary["tables"]["glims_samples"] = count
        summary["total_records"] += count
    except Exception as e:
        LOGGER.error(f"Fallo total en glims_samples: {e}")
        summary["tables"]["glims_samples"] = f"Error: {e}"
    
    # --- 2. Migrar Resultados ---
    for table in TABLES_RESULTS:
        query_results = f"""
            SELECT * FROM {table} 
            WHERE sample_id NOT LIKE 'S26-%'
        """
        try:
            count = migrate_table(src_engine, dst_engine, table, query_results, dry_run)
            summary["tables"][table] = count
            summary["total_records"] += count
        except Exception as e:
            LOGGER.error(f"Error migrando {table}: {e}")
            summary["tables"][table] = f"Error: {str(e)}"

    LOGGER.info("Resumen de Migración:")
    print(json.dumps(summary, indent=2))
    
    with open("scripts/azure_migration_report.json", "w") as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=False, help="Solo simula la migración")
    args = parser.parse_args()
    
    try:
        main(dry_run=args.dry_run)
    except Exception as e:
        LOGGER.exception(f"Error fatal: {e}")
