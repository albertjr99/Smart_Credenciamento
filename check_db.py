import sqlite3

conn = sqlite3.connect('credenciamento.db')
c = conn.cursor()

# Listar todas as tabelas
tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()

print("Tabelas no banco:")
for t in tables:
    print(f"  - {t[0]}")
    
# Verificar estrutura da tabela users
print("\nEstrutura da tabela users:")
info = c.execute("PRAGMA table_info(users)").fetchall()
for col in info:
    print(f"  {col}")

conn.close()
