import sys
import sqlite3
import pandas as pd

# Ensures terminal uses UTF-8 and replaces invalid characters
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def clean_input(text: str) -> str:
    """Ensures input string is valid UTF-8 and free of invalid surrogates."""
    if not isinstance(text, str):
        return text
    try:
        text.encode('utf-8')
        return text.strip()
    except UnicodeEncodeError:
        try:
            return text.encode('utf-8', 'surrogateescape').decode('latin-1').strip()
        except Exception:
            return text.encode('utf-8', 'replace').decode('utf-8').strip()

# Compatibility alias
limpar_input = clean_input

def train_rules_engine(db_path: str = "meu_dinheiro.db"):
    """Interactive CLI for categorizing orphan transactions and creating permanent keyword rules."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Query uncategorized transactions ordered by date
    query = """
    SELECT id_hash, data_transacao, descricao, valor, tipo_conta 
    FROM transacoes 
    WHERE categoria = 'Não Categorizado'
    ORDER BY data_transacao DESC
    """
    df_orphans = pd.read_sql(query, conn)
    
    if df_orphans.empty:
        print("[+] Excellent! Zero orphan transactions. Rules engine is 100% trained.")
        conn.close()
        return

    cursor.execute("SELECT DISTINCT categoria FROM transacoes WHERE categoria NOT IN ('Não Categorizado', 'Avulso') ORDER BY categoria")
    existing_categories = [row[0] for row in cursor.fetchall()]

    print(f"\n[*] Found {len(df_orphans)} orphan transactions.")
    print("Actions: [R]ule (universal) | [M]anual (single) | [I]gnore (Misc) | [P] Skip | [Q]uit")
    if existing_categories:
        print(f"Existing categories: {', '.join(existing_categories)}")
    print("-" * 65)
    
    for _, row in df_orphans.iterrows():
        cursor.execute("SELECT categoria FROM transacoes WHERE id_hash = ?", (row['id_hash'],))
        current_status = cursor.fetchone()[0]
        if current_status != 'Não Categorizado':
            continue
        print(f"\n[{row['tipo_conta']}] Date: {row['data_transacao']} | Amount: R$ {row['valor']:.2f}")
        print(f"Desc: {row['descricao']}")
        
        action = input("Choose [R/M/I/P] or [Q] to Quit: ").strip().upper()
        
        # 0. QUIT
        if action in ('Q', 'QUIT', 'EXIT', 'S'):
            print("[*] Saving changes and exiting...")
            break

        # 1. SKIP
        if action in ('P', 'SKIP', ''):
            continue
            
        # 2. IGNORE (Mark as Misc / Avulso)
        elif action == 'I':
            cursor.execute("UPDATE transacoes SET categoria = 'Avulso' WHERE id_hash = ?", (row['id_hash'],))
            conn.commit()
            print(" -> Marked as 'Avulso'.")
            
        # 3. MANUAL (Single transaction classification without future rule)
        elif action == 'M':
            if existing_categories:
                print(f"  (Existing categories: {', '.join(existing_categories)})")
            cat = clean_input(input("  Enter category (ONLY for this transaction): "))
            cursor.execute("UPDATE transacoes SET categoria = ? WHERE id_hash = ?", (cat, row['id_hash']))
            conn.commit()
            if cat not in existing_categories:
                existing_categories.append(cat)
            print(f" -> Classified as '{cat}'.")
            
        # 4. RULE (Creates universal rule and applies to all matching past and future transactions)
        elif action == 'R':
            keyword = clean_input(input("  Keyword (e.g. UBER, IFOOD): ")).upper()
            if existing_categories:
                print(f"  (Existing categories: {', '.join(existing_categories)})")
            cat = clean_input(input("  Target category: "))
            flow_type = 'ENTRADA' if row['valor'] > 0 else 'SAIDA'
            
            # Insert rule into engine
            cursor.execute("""
            INSERT OR IGNORE INTO regras_categorizacao (palavra_chave, categoria_destino, tipo_fluxo)
            VALUES (?, ?, ?)
            """, (keyword, cat, flow_type))
            
            # Apply rule to all past matching transactions
            operator = ">" if flow_type == "ENTRADA" else "<"
            cursor.execute(f"""
                UPDATE transacoes 
                SET categoria = ? 
                WHERE categoria = 'Não Categorizado' 
                AND valor {operator} 0 
                AND descricao LIKE ?
            """, (cat, f"%{keyword}%"))
            
            conn.commit()
            if cat not in existing_categories:
                existing_categories.append(cat)
            print(f" -> Rule '{keyword}' created and applied to database!")
            
        else:
            print(" -> Unrecognized option. Skipping...")
            
    conn.close()
    print("\n[*] Rule training session completed!")

# Compatibility alias
treinar_motor = train_rules_engine

if __name__ == "__main__":
    train_rules_engine()