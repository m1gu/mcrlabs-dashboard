import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def migrate():
    load_dotenv()
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ["POSTGRES_DB"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    engine = create_engine(url)

    sql = """
    CREATE TABLE IF NOT EXISTS glims_rs_results_raw (
        id SERIAL PRIMARY KEY,
        
        -- Identificadores
        sample_id TEXT NOT NULL,           -- Valor original de columna A (sin limpiar)
        sample_id_clean TEXT,              -- ID limpio para agrupación
        
        -- Fechas y análisis
        prep_date DATE,
        start_date DATE,
        lab_analyst TEXT,
        instrument TEXT,
        sample_weight_mg NUMERIC(12, 4),
        dilution NUMERIC(12, 4),
        
        -- Resultados de solventes (todos como TEXT para soportar ND/BQL)
        acetone TEXT,
        acetonitrile TEXT,
        benzene TEXT,
        butane TEXT,
        chloroform TEXT,
        dichloroethane_1_2 TEXT,           -- "1,2-Dichloroethane"
        ethanol TEXT,
        ethyl_acetate TEXT,
        ethyl_ether TEXT,
        ethylene_oxide TEXT,
        heptane TEXT,
        hexane TEXT,
        isopropyl_alcohol TEXT,
        methanol TEXT,
        methylene_chloride TEXT,
        pentane TEXT,
        propane TEXT,
        toluene TEXT,
        total_xylenes TEXT,
        trichloroethylene TEXT,
        
        -- Metadata
        client TEXT,
        data_analyst TEXT,
        rerun_category TEXT,
        note TEXT,
        batch_id TEXT,
        
        -- Timestamps
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- Índices para búsqueda eficiente
    CREATE INDEX IF NOT EXISTS idx_rs_raw_sample_id_clean ON glims_rs_results_raw(sample_id_clean);
    CREATE INDEX IF NOT EXISTS idx_rs_raw_client ON glims_rs_results_raw(lower(client));
    CREATE INDEX IF NOT EXISTS idx_rs_raw_start_date ON glims_rs_results_raw(start_date);
    """
    
    with engine.begin() as conn:
        conn.execute(text(sql))
        print("Table glims_rs_results_raw and indices created successfully.")

if __name__ == "__main__":
    migrate()
