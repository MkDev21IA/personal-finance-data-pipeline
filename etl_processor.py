import pandas as pd
import hashlib
import sqlite3
import os
import sys
import glob
import shutil
import re
import numpy as np
import pdfplumber
from dotenv import load_dotenv

load_dotenv()

# Directories where statements and invoices are manually exported (configurable via .env)
C6_STATEMENTS_PATH = os.getenv("C6_STATEMENTS_PATH", "../C6_Statements")
INTER_INVOICES_PATH = os.getenv("INTER_INVOICES_PATH", "../Inter_Invoices")

# Compatibility aliases
PASTA_EXTRATOS_C6 = C6_STATEMENTS_PATH
PASTA_FATURAS_INTER = INTER_INVOICES_PATH

def setup_database_with_rules(db_path: str = "meu_dinheiro.db"):
    """Initializes the database schema and default rules engine."""
    print("[*] Verifying database schema and rules engine...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Official transactions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transacoes (
        id_hash TEXT PRIMARY KEY,
        data_transacao DATE,
        descricao TEXT,
        valor NUMERIC,
        saldo_conta NUMERIC,
        categoria TEXT,
        tipo_conta TEXT,
        banco_origem TEXT
    )
    """)

    # Migration: add banco_origem column to existing databases if missing
    existing_columns = [row[1] for row in cursor.execute("PRAGMA table_info(transacoes)").fetchall()]
    if 'banco_origem' not in existing_columns:
        cursor.execute("ALTER TABLE transacoes ADD COLUMN banco_origem TEXT DEFAULT 'INTER'")

    # Categorization rules table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS regras_categorizacao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        palavra_chave TEXT NOT NULL UNIQUE,
        categoria_destino TEXT NOT NULL,
        tipo_fluxo TEXT NOT NULL CHECK(tipo_fluxo IN ('ENTRADA', 'SAIDA'))
    )
    """)
    
    # Seed rules
    seed_rules = [
        # OUTFLOWS (negative amounts)
        ('IFOOD', 'Alimentação', 'SAIDA'),
        ('UBER', 'Transporte Aplicativo', 'SAIDA'),
        ('99APP', 'Transporte Aplicativo', 'SAIDA'),
        ('FATURA', 'Transferência Interna', 'SAIDA'),
        # INFLOWS (positive amounts)
        ('RESGATE', 'Resgate de Investimentos', 'ENTRADA'),
        ('PROV', 'Rendimentos', 'ENTRADA'),
        ('RENDIMENTO', 'Rendimentos', 'ENTRADA'),
        ('CASHBACK', 'Chackbacks', 'ENTRADA')
    ]
    
    cursor.executemany("""
    INSERT OR IGNORE INTO regras_categorizacao (palavra_chave, categoria_destino, tipo_fluxo)
    VALUES (?, ?, ?)
    """, seed_rules)
    
    conn.commit()
    conn.close()

def import_c6_statements(source_dir: str = C6_STATEMENTS_PATH, target_dir: str = "./downloads"):
    """Copies manually exported C6 CSV files to the local downloads folder.
    Returns (original, copy) pairs that are deleted only after verified SQLite commit."""
    if not os.path.isdir(source_dir):
        print(f"[!] C6 statement folder not found at: {source_dir}")
        return []

    file_pairs = []
    for file_path in glob.glob(os.path.join(source_dir, "*.csv")):
        destination = os.path.join(target_dir, os.path.basename(file_path))
        shutil.copy2(file_path, destination)
        file_pairs.append((file_path, destination))

    if file_pairs:
        print(f"[*] {len(file_pairs)} C6 file(s) found and imported from '{source_dir}'.")
    else:
        print(f"[*] No new CSV files in '{source_dir}'.")

    return file_pairs

def import_inter_invoices(source_dir: str = INTER_INVOICES_PATH, target_dir: str = "./downloads"):
    """Copies Banco Inter PDF invoice files to the local downloads folder.
    Returns (original, copy) pairs that are deleted only after verified SQLite commit."""
    if not os.path.isdir(source_dir):
        print(f"[!] Inter invoice folder not found at: {source_dir}")
        return []

    file_pairs = []
    for file_path in glob.glob(os.path.join(source_dir, "*.pdf")):
        destination = os.path.join(target_dir, os.path.basename(file_path))
        shutil.copy2(file_path, destination)
        file_pairs.append((file_path, destination))

    if file_pairs:
        print(f"[*] {len(file_pairs)} Inter PDF invoice(s) found and imported from '{source_dir}'.")
    else:
        print(f"[*] No new PDF invoices in '{source_dir}'.")

    return file_pairs

def _parse_csv(file_path: str):
    """Detects CSV source format (Inter or C6, checking account or card) and returns a standardized DataFrame.
    Returns None if the file does not match any supported schema."""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        first_line = f.readline().strip()

    if "C6 BANK" in first_line.upper():
        # C6 Bank checking account statement: 8 decorative header lines before table
        df = pd.read_csv(file_path, sep=',', skiprows=8, encoding='utf-8')
        df = df.rename(columns={
            'Data Lançamento': 'data_transacao',
            'Descrição': 'descricao',
            'Saldo do Dia(R$)': 'saldo_conta'
        })
        inflows = pd.to_numeric(df['Entrada(R$)'].astype(str).str.replace(',', '', regex=False), errors='coerce').fillna(0)
        outflows = pd.to_numeric(df['Saída(R$)'].astype(str).str.replace(',', '', regex=False), errors='coerce').fillna(0)
        df['valor'] = inflows - outflows
        df['saldo_conta'] = pd.to_numeric(df['saldo_conta'].astype(str).str.replace(',', '', regex=False), errors='coerce')
        df['tipo_conta'] = 'CONTA'
        df['banco_origem'] = 'C6'
        df = df[['data_transacao', 'descricao', 'valor', 'saldo_conta', 'tipo_conta', 'banco_origem']]

    elif "Data de Compra" in first_line:
        # C6 Bank credit card invoice
        df = pd.read_csv(file_path, sep=';', encoding='utf-8')
        df = df.rename(columns={'Data de Compra': 'data_transacao', 'Descrição': 'descricao'})
        df['valor'] = pd.to_numeric(df['Valor (em R$)'].astype(str).str.replace(',', '', regex=False), errors='coerce') * -1
        df['saldo_conta'] = np.nan
        df['tipo_conta'] = 'CARTAO'
        df['banco_origem'] = 'C6'
        df = df[['data_transacao', 'descricao', 'valor', 'saldo_conta', 'tipo_conta', 'banco_origem']]

    elif "Extrato" in first_line or "Conta" in first_line:
        # Banco Inter checking account statement
        df = pd.read_csv(file_path, sep=';', skiprows=6, header=None, names=['data_transacao', 'descricao', 'valor', 'saldo_conta'], encoding='utf-8')
        df['tipo_conta'] = 'CONTA'
        df['banco_origem'] = 'INTER'
        df['valor'] = df['valor'].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).astype(float)

    elif '"Data"' in first_line or 'Data' in first_line:
        # Banco Inter credit card invoice CSV
        df = pd.read_csv(file_path, sep=',', encoding='utf-8')
        df = df.rename(columns={'Data': 'data_transacao', 'Lançamento': 'descricao', 'Valor': 'valor'})
        df['saldo_conta'] = np.nan
        df['tipo_conta'] = 'CARTAO'
        df['banco_origem'] = 'INTER'
        df['valor'] = df['valor'].astype(str).str.replace('R$', '', regex=False).str.replace('\xa0', '', regex=False).str.replace(' ', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).astype(float) * -1
        df = df[['data_transacao', 'descricao', 'valor', 'saldo_conta', 'tipo_conta', 'banco_origem']]
    else:
        return None

    df['data_transacao'] = pd.to_datetime(df['data_transacao'], format='%d/%m/%Y', errors='coerce').dt.strftime('%Y-%m-%d')
    df = df.dropna(subset=['data_transacao', 'valor'])
    df['id_hash'] = df.apply(lambda row: hashlib.md5(f"{row['data_transacao']}{row['descricao']}{row['valor']}".encode('utf-8')).hexdigest(), axis=1)
    return df

def _parse_inter_pdf(file_path: str):
    """Extracts invoice line items from Banco Inter PDF statement into a standardized DataFrame.
    Returns None if the document does not contain 'Despesas da fatura' or valid transactions."""
    month_map = {
        "jan": "01", "fev": "02", "mar": "03", "abr": "04", "mai": "05", "jun": "06",
        "jul": "07", "ago": "08", "set": "09", "out": "10", "nov": "11", "dez": "12"
    }
    line_pattern = re.compile(r"^(\d{2}\s+de\s+[a-z]{3}\.?\s+\d{4})\s+(.+?)\s*([+-]?\s*R\$\s*[\d\.,]+)$", re.IGNORECASE)
    date_pattern = re.compile(r"(\d{2})\s+de\s+([a-z]{3})\.?\s+(\d{4})", re.IGNORECASE)

    records = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "Despesas da fatura" not in text:
                continue
            for line in text.split("\n"):
                match_line = line_pattern.match(line.strip())
                if not match_line:
                    continue
                raw_date, raw_desc, raw_val = match_line.groups()

                # Ignore previous invoice payments to prevent double counting with checking account debit
                if any(t in raw_desc.upper() for t in ["PAGTO DEBITO", "PAGAMENTO DE FATURA", "PAGTO ELETRON", "PAGAMENTO EM CONTA"]):
                    continue

                match_date = date_pattern.search(raw_date)
                if not match_date:
                    continue
                day, month_name, year = match_date.groups()
                month_num = month_map.get(month_name.lower()[:3])
                if not month_num:
                    continue
                iso_date = f"{year}-{month_num}-{day}"

                # Clean description (remove trailing dash from empty beneficiary and extra spaces)
                clean_desc = re.sub(r"\s+-\s*$", "", raw_desc).strip()
                clean_desc = re.sub(r"\s+", " ", clean_desc)

                # Normalize monetary amount
                is_credit = "+" in raw_val
                val_clean = raw_val.replace("R$", "").replace("+", "").replace("-", "").replace(".", "").replace(",", ".").strip()
                val_num = float(val_clean)
                final_val = val_num if is_credit else -val_num

                records.append({
                    "data_transacao": iso_date,
                    "descricao": clean_desc,
                    "valor": final_val,
                    "saldo_conta": np.nan,
                    "tipo_conta": "CARTAO",
                    "banco_origem": "INTER"
                })

    if not records:
        return None

    df = pd.DataFrame(records)
    df["id_hash"] = df.apply(
        lambda r: hashlib.md5(f"{r['data_transacao']}{r['descricao']}{r['valor']}".encode("utf-8")).hexdigest(),
        axis=1
    )
    return df

def process_all_files(directory: str = "./downloads"):
    """Scans downloads folder processing CSV and PDF files.
    Each file is isolated in its own try/except for resilient processing."""
    csv_files = glob.glob(os.path.join(directory, "*.csv"))
    pdf_files = glob.glob(os.path.join(directory, "*.pdf"))
    if not csv_files and not pdf_files:
        return None
    dataframes = []

    for file_path in csv_files:
        try:
            df = _parse_csv(file_path)
        except Exception as e:
            print(f"[!] Warning: failed to parse CSV '{file_path}', skipping. Error: {e}")
            continue

        if df is not None:
            dataframes.append(df)

    for file_path in pdf_files:
        try:
            df = _parse_inter_pdf(file_path)
        except Exception as e:
            print(f"[!] Warning: failed to parse PDF '{file_path}', skipping. Error: {e}")
            continue

        if df is not None:
            dataframes.append(df)

    return pd.concat(dataframes, ignore_index=True) if dataframes else None

def apply_categorization_rules(df, db_path: str = "meu_dinheiro.db"):
    """Applies keyword rules to classify transactions by cash flow type."""
    print("[*] Applying categorization rules engine...")
    conn = sqlite3.connect(db_path)
    
    # Load rules from SQLite into DataFrame
    df_rules = pd.read_sql("SELECT palavra_chave, categoria_destino, tipo_fluxo FROM regras_categorizacao", conn)
    conn.close()
    
    df['categoria'] = 'Não Categorizado'
    
    # Separate rules by flow direction to prevent cross-matching
    outflow_rules = df_rules[df_rules['tipo_fluxo'] == 'SAIDA']
    inflow_rules = df_rules[df_rules['tipo_fluxo'] == 'ENTRADA']
    
    # Apply outflow rules (amount < 0)
    for _, rule in outflow_rules.iterrows():
        mask_outflow = (df['valor'] < 0) & (df['descricao'].str.contains(rule['palavra_chave'], case=False, na=False))
        df.loc[mask_outflow, 'categoria'] = rule['categoria_destino']
        
    # Apply inflow rules (amount > 0)
    for _, rule in inflow_rules.iterrows():
        mask_inflow = (df['valor'] > 0) & (df['descricao'].str.contains(rule['palavra_chave'], case=False, na=False))
        df.loc[mask_inflow, 'categoria'] = rule['categoria_destino']
        
    print("[+] Categorization complete. Data sample:")
    print(df[['descricao', 'valor', 'categoria']].head())
    return df

def load_data_sqlite(df, db_path: str = "meu_dinheiro.db"):
    """Persists transactions into SQLite warehouse using idempotent upsert."""
    print("[*] Connecting to SQLite database...")
    conn = sqlite3.connect(db_path)
    
    # 1. Ensure official table exists with hash as primary key
    conn.execute("""
    CREATE TABLE IF NOT EXISTS transacoes (
        id_hash TEXT PRIMARY KEY,
        data_transacao DATE,
        descricao TEXT,
        valor NUMERIC,
        saldo_conta NUMERIC,
        categoria TEXT,
        tipo_conta TEXT,
        banco_origem TEXT
    )
    """)

    # 2. Stage clean data into temporary staging table
    df.to_sql('staging_transacoes', conn, if_exists='replace', index=False)

    # 3. Idempotent Upsert: Insert only previously unseen transaction hashes
    query_insert = """
    INSERT OR IGNORE INTO transacoes (id_hash, data_transacao, descricao, valor, saldo_conta, categoria, tipo_conta, banco_origem)
    SELECT id_hash, data_transacao, descricao, valor, saldo_conta, categoria, tipo_conta, banco_origem
    FROM staging_transacoes;
    """
    
    cursor = conn.cursor()
    cursor.execute(query_insert)
    inserted_rows = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print(f"[+] Load complete! {inserted_rows} new unique transactions added.")

# Backward compatibility aliases
setup_database_com_regras = setup_database_with_rules
importar_extratos_c6 = import_c6_statements
importar_faturas_inter = import_inter_invoices
_parsear_csv = _parse_csv
_parsear_pdf_inter = _parse_inter_pdf
processar_todos_arquivos = process_all_files
processar_todos_csvs = process_all_files
aplicar_regras_categorizacao = apply_categorization_rules
carregar_dados_sqlite = load_data_sqlite

if __name__ == "__main__":
    # Prepare database schema and seed rules
    setup_database_with_rules()

    # Import Banco Inter PDF invoices from configured directory
    inter_source_pairs = import_inter_invoices()

    # Import C6 Bank manual CSV statements/invoices from configured directory
    c6_source_pairs = import_c6_statements()

    # Process all files (CSVs and PDFs) available in downloads folder
    raw_df = process_all_files("./downloads")

    if raw_df is None:
        print("[X] Error: No valid files found to process (neither Inter nor C6).")
        sys.exit(1)

    try:
        # Categorize
        categorized_df = apply_categorization_rules(raw_df)
        load_data_sqlite(categorized_df)

        # Remove source originals and temporary copies only AFTER successful database load
        all_pairs = inter_source_pairs + c6_source_pairs
        for original, copy in all_pairs:
            if os.path.exists(original):
                os.remove(original)
            if os.path.exists(copy):
                os.remove(copy)

        if inter_source_pairs:
            print(f"[*] {len(inter_source_pairs)} Inter invoice(s) removed from source folder after load.")
        if c6_source_pairs:
            print(f"[*] {len(c6_source_pairs)} C6 file(s) removed from source folder after load.")

    except Exception as e:
        print(f"[X] Critical error during database load: {e}")
        sys.exit(1)