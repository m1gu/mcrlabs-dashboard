"""
Valida el CSV fuente antes de ejecutar la migración.
Verifica columnas requeridas y genera reporte de cobertura.
"""
import pandas as pd
import json
import os

def validate():
    csv_path = 'qbench-backup.csv'
    if not os.path.exists(csv_path):
        print(f"Error: No se encuentra el archivo {csv_path}")
        return
        
    df = pd.read_csv(csv_path, low_memory=False)
    
    required = ['Full ID', 'Type']
    missing = [c for c in required if c not in df.columns]
    
    if missing:
        print(f"Error: Columnas faltantes en el CSV: {missing}")
        return
    
    report = {
        "status": "OK",
        "total_rows_csv": len(df),
        "type_distribution": df['Type'].value_counts(dropna=False).to_dict(),
        "full_id_nulls": int(df['Full ID'].isna().sum()),
        "full_id_coverage_pct": float((df['Full ID'].notna().sum() / len(df)) * 100)
    }
    
    output_path = 'scripts/csv_validation_report.json'
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
        
    print(f"Reporte de validación generado en {output_path}")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    validate()
