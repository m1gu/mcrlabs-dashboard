import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from datetime import datetime

load_dotenv()

def verify_db_exclusion():
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    db = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    pw = os.getenv("POSTGRES_PASSWORD")
    
    engine = create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}")
    
    # Same logic as in the backend
    exclude_pattern = r"(-HO[12](-\d+)?)$|(-(1|2|3|N))$"
    min_days = 3
    
    sql = """
        SELECT COUNT(*)
        FROM glims_samples s
        WHERE s.date_received IS NOT NULL
          AND s.sample_id !~ :exclude_pattern
          AND s.date_received >= '2025-01-01'
          AND s.status NOT IN ('Unknown', 'DISCONTINUED', 'NOT STARTED', 'NOT REPORTABLE', 'CLIENT CANCELLED')
          AND s.report_date IS NULL
          AND s.status NOT IN ('Reported', 'Cancelled', 'Destroyed')
          AND EXTRACT(EPOCH FROM (timezone('America/New_York', now()) - s.date_received::timestamp))/3600.0 >= (:min_days * 24)
    """
    
    sql_old = """
        SELECT COUNT(*)
        FROM glims_samples s
        WHERE s.date_received IS NOT NULL
          AND s.sample_id !~ :exclude_pattern
          AND s.date_received < '2025-01-01'
          AND s.status = 'Unknown'
          AND s.report_date IS NULL
          AND s.status NOT IN ('Reported', 'Cancelled', 'Destroyed')
          AND EXTRACT(EPOCH FROM (timezone('America/New_York', now()) - s.date_received::timestamp))/3600.0 >= (:min_days * 24)
    """

    with engine.connect() as conn:
        count_active = conn.execute(text(sql), {"exclude_pattern": exclude_pattern, "min_days": min_days}).scalar()
        count_historical = conn.execute(text(sql_old), {"exclude_pattern": exclude_pattern, "min_days": min_days}).scalar()
        
        print("\n=== VERIFICACIÓN DE EXCLUSIÓN EN DB ===")
        print(f"Samples Overdue (Recientes >= 2025): {count_active}")
        print(f"Samples Históricos (Qbench < 2025, Unknown) que SERÍAN filtrados: {count_historical}")
        
        if count_historical > 0:
            print("SUCCESS: Se identificaron muestras históricas que el nuevo filtro excluirá.")
        else:
            print("NOTE: No se encontraron muestras históricas pendientes, pero el filtro es preventivo.")

if __name__ == "__main__":
    verify_db_exclusion()
