import sys
import sqlite3
from datetime import datetime
from dateutil.relativedelta import relativedelta
import hashlib

# Ensures terminal uses UTF-8 and replaces invalid characters
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def split_transaction_installments(original_id_hash: str, num_installments: int, db_path: str = "meu_dinheiro.db"):
    """Splits an existing one-off transaction into future monthly installments."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Fetch original transaction
    cursor.execute("SELECT data_transacao, descricao, valor, tipo_conta, categoria FROM transacoes WHERE id_hash = ?", (original_id_hash,))
    transaction = cursor.fetchone()
    
    if not transaction:
        print("[X] Transaction not found!")
        conn.close()
        return

    data_str, desc, total_amount, tipo_conta, categoria = transaction
    
    # 2. Compute installment value
    installment_amount = total_amount / num_installments
    base_date = datetime.strptime(data_str, "%Y-%m-%d")
    
    print(f"[*] Splitting '{desc}' (R$ {total_amount:.2f}) into {num_installments} installments of R$ {installment_amount:.2f}...")

    # 3. Update original transaction as installment 1
    desc_installment_1 = f"{desc} (1/{num_installments})"
    cursor.execute("""
        UPDATE transacoes 
        SET valor = ?, descricao = ? 
        WHERE id_hash = ?
    """, (installment_amount, desc_installment_1, original_id_hash))

    # 4. Generate future installment records
    for i in range(2, num_installments + 1):
        new_date = base_date + relativedelta(months=(i - 1))
        new_date_str = new_date.strftime("%Y-%m-%d")
        new_desc = f"{desc} ({i}/{num_installments})"
        
        new_hash = hashlib.sha256(f"{new_date_str}{new_desc}{installment_amount}{tipo_conta}".encode()).hexdigest()
        
        cursor.execute("""
            INSERT OR IGNORE INTO transacoes (id_hash, data_transacao, descricao, valor, tipo_conta, categoria, saldo_conta)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (new_hash, new_date_str, new_desc, installment_amount, tipo_conta, categoria))

    conn.commit()
    conn.close()
    print("[+] Installments successfully recorded in database!")

# Compatibility alias
parcelar_transacao_manual = split_transaction_installments

if __name__ == "__main__":
    print("===================================================")
    print("         INSTALLMENT TRANSACTION MANAGER")
    print("===================================================\n")
    print("Tip: Retrieve transaction id_hash directly from Metabase.\n")
    
    while True:
        chosen_hash = input("Paste transaction ID_HASH (or 'Q' to quit): ").strip()
        
        if chosen_hash.upper() in ('Q', 'QUIT', 'S'):
            print("\n[*] Exiting installment manager...")
            break
        
        if not chosen_hash:
            print("[!] ID_HASH cannot be empty. Please try again.\n")
            continue
            
        try:
            num = int(input("Enter total number of installments (e.g. 5): ").strip())
            if num <= 1:
                print("[!] Number of installments must be greater than 1.\n")
                continue
                
            split_transaction_installments(chosen_hash, num)
            print("-" * 50)
            
        except ValueError:
            print("[X] Invalid input. Please enter an integer.\n")
        except Exception as e:
            print(f"\n[X] Error processing installments: {e}\n")
        
        print()