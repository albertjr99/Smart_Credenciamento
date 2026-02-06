import sqlite3
conn = sqlite3.connect('credenciamento.db')
c = conn.cursor()
c.execute("UPDATE documents SET status = 'analyzing' WHERE id = 1")
conn.commit()
print('✅ Documento resetado para analyzing')
conn.close()
