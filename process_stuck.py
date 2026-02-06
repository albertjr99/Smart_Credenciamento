import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('credenciamento.db')
c = conn.cursor()

# Buscar documentos em analyzing
c.execute("SELECT id, filename FROM documents WHERE status = 'analyzing'")
docs = c.fetchall()

if not docs:
    print("Nenhum documento em analyzing")
else:
    for doc_id, filename in docs:
        print(f"Processando documento #{doc_id}: {filename}")
        # Mudar status para rejected forçadamente
        c.execute("UPDATE documents SET status = 'rejected' WHERE id = ?", (doc_id,))
    
    conn.commit()
    print(f"Processados {len(docs)} documentos")

conn.close()

# Agora rodar força análise
import os
os.system('py force_analyze.py')
