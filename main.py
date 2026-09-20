import subprocess
import sys
import os

if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def run_script_with_input(script_name: str, user_input: str = None) -> bool:
    """Executes a python script, piping user input into stdin if provided."""
    try:
        if user_input:
            result = subprocess.run(
                [sys.executable, script_name],
                input=user_input,
                text=True,
                check=True
            )
        else:
            result = subprocess.run(
                [sys.executable, script_name],
                check=True
            )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"[X] Error executing {script_name}: {e}")
        return False

# Compatibility alias
rodar_script_com_input = run_script_with_input

def run_pipeline():
    """Main orchestrator for the multi-bank personal finance pipeline."""
    print("=" * 60)
    print("      STARTING FINANCIAL AUTOMATION PIPELINE")
    print("=" * 60)
    
    # 1. Extraction period selection menu
    print("\nChoose extraction period:")
    print("[ A ] 7 days")
    print("[ B ] 15 days")
    print("[ C ] 30 days")
    print("[ D ] 90 days")
    
    option = input("\nEnter option letter: ").strip().upper()
    
    # Maps selected letter to the exact string required by Banco Inter web portal
    period_map = {
        'A': '7 dias',
        'B': '15 dias',
        'C': '30 dias',
        'D': '90 dias'
    }
    
    period = period_map.get(option, '7 dias')
    print(f"\n[*] Validated period: {period}")
    
    # 2. PHASE 1: Banco Inter Web Crawler
    print("\n" + "=" * 60)
    print("      [PHASE 1/2] BANCO INTER PROCESSING")
    print("=" * 60)
    print("\n[*] Launching Banco Inter Web Crawler (Checking Account Statement)...")
    if not run_script_with_input("inter_crawler.py", user_input=f"{period}\n"):
        print("[!] Warning: Inter Crawler failed. Pipeline will continue with available PDF invoices and C6 data.")

    # 3. PHASE 2: Ingestion and ETL Processing
    print("\n" + "=" * 60)
    print("      [PHASE 2/2] INGESTION (INTER PDF + C6 CSV) & ETL PIPELINE")
    print("=" * 60)
    if not run_script_with_input("etl_processor.py"):
        print("[X] Pipeline aborted: neither Inter nor C6 produced valid data to process.")
        sys.exit(1)

    # 4. Interactive Rule Training for Orphan Transactions
    print("\n" + "=" * 60)
    print("      ORPHAN TRANSACTION CATEGORIZATION")
    print("=" * 60)
    train_choice = input("\nDo you want to run the rule training engine now? (Y/N): ").strip().upper()
    
    if train_choice in ('Y', 'S'):
        run_script_with_input("train_rules.py")
    else:
        print("[*] Training skipped. Database is ready for Metabase queries.")
        
    print("\n" + "=" * 60)
    print("            PIPELINE COMPLETED SUCCESSFULLY!")
    print("=" * 60)

# Compatibility alias
pipeline_principal = run_pipeline

if __name__ == "__main__":
    run_pipeline()