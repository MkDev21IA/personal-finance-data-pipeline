import sys
import sqlite3

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

def list_existing_categories(cursor):
    """Returns a sorted list of unique categories already present in the database."""
    cursor.execute("SELECT DISTINCT categoria FROM transacoes WHERE categoria IS NOT NULL ORDER BY categoria")
    return [row[0] for row in cursor.fetchall()]

# Compatibility alias
listar_categorias_existentes = list_existing_categories

def override_category(id_hash: str, new_category: str, db_path: str = "meu_dinheiro.db") -> bool:
    """Manually updates the category of a single transaction identified by its hash."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT data_transacao, descricao, valor, categoria FROM transacoes WHERE id_hash = ?", (id_hash,))
    transaction = cursor.fetchone()

    if not transaction:
        print("[X] Transaction not found!")
        conn.close()
        return False

    date_str, desc, amount, current_category = transaction
    cursor.execute("UPDATE transacoes SET categoria = ? WHERE id_hash = ?", (new_category, id_hash))
    conn.commit()
    conn.close()

    print(f"[+] '{desc}' ({date_str}, R$ {amount:.2f}): '{current_category}' -> '{new_category}'")
    return True

# Compatibility alias
corrigir_categoria = override_category

if __name__ == "__main__":
    print("===================================================")
    print("         CATEGORY OVERRIDE TOOL")
    print("===================================================\n")
    print("Tip: Retrieve transaction id_hash directly from Metabase.\n")

    conn = sqlite3.connect("meu_dinheiro.db")
    existing_categories = list_existing_categories(conn.cursor())
    conn.close()

    while True:
        chosen_hash = input("Paste transaction ID_HASH (or 'Q' to quit): ").strip()

        if chosen_hash.upper() in ('Q', 'QUIT', 'S'):
            print("\n[*] Exiting category override tool...")
            break

        if not chosen_hash:
            print("[!] ID_HASH cannot be empty. Please try again.\n")
            continue

        if existing_categories:
            print(f"  (Existing categories: {', '.join(existing_categories)})")
        new_category = clean_input(input("New category: "))

        if not new_category:
            print("[!] Category cannot be empty. Please try again.\n")
            continue

        if override_category(chosen_hash, new_category) and new_category not in existing_categories:
            existing_categories.append(new_category)

        print("-" * 50)
        print()
