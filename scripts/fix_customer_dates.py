import os
from datetime import date
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def fix_dates():
    # Load environment variables
    load_dotenv()
    
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB")
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")

    if not all([db, user, password]):
        print("Error: Missing database environment variables (POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD).")
        return

    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    engine = create_engine(url, future=True)
    
    # Specific mappings provided by user (MM-DD-YYYY -> YYYY-MM-DD)
    specific_updates = [
        (359, "2025-11-18"),
        (360, "2025-11-20"),
        (361, "2025-11-21"),
        (362, "2025-12-03"),
        (363, "2025-12-01"),
        (365, "2025-12-03"),
        (366, "2025-12-08"),
        (367, "2025-12-10"),
        (368, "2025-12-12"),
        (369, "2025-12-18"),
        (370, "2025-12-23"),
        (371, "2025-12-26"),
        (372, "2025-12-31"),
        (373, "2026-01-02"),
    ]

    try:
        with engine.begin() as conn:
            # 1. Update all clients <= 359 to 2025-11-18
            print("Updating legacy clients (ID <= 359)...")
            res = conn.execute(
                text("UPDATE glims_new_customers SET date_created = :d WHERE client_id <= 359"),
                {"d": "2025-11-18"}
            )
            print(f"Updated {res.rowcount} legacy records.")

            # 2. Update specific individual IDs
            print("Updating specific individual client IDs...")
            for cid, dt in specific_updates:
                if cid <= 359: continue # Already handled or covered by <= 359
                conn.execute(
                    text("UPDATE glims_new_customers SET date_created = :d WHERE client_id = :cid"),
                    {"d": dt, "cid": cid}
                )
            print("Finished individual updates.")

        print("\nSuccess: Customer dates have been updated.")
        
        # Verify result
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT client_id, date_created FROM glims_new_customers ORDER BY client_id DESC LIMIT 15")).all()
            print("\nVerification (Last 15 records):")
            for row in rows:
                print(f"ID: {row.client_id} -> Date: {row.date_created}")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    fix_dates()
