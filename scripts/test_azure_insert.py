import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def test_insert():
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    db = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    pw = os.getenv("POSTGRES_PASSWORD")
    
    engine = create_engine(f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}")
    
    try:
        with engine.begin() as conn:
            print("Conectado a Azure. Intentando insertar/actualizar una dispensaria...")
            # Usar una dispensaria de prueba o una existente
            sql = text("INSERT INTO glims_dispensaries (id, name, updated_at) VALUES (999999, 'TEST_MIGRATION', now()) ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = now()")
            conn.execute(sql)
            print("¡Éxito en la inserción!")
    except Exception as e:
        print(f"Error fatal: {e}")

if __name__ == "__main__":
    test_insert()
