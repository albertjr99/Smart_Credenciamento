import sqlite3

conn = sqlite3.connect('credenciamento.db')
c = conn.cursor()

# Verificar documentos termo_credenciamento existentes
c.execute('SELECT id, process_id, type, name FROM documents WHERE type = ?', ('termo_credenciamento',))
docs = c.fetchall()
print(f'=== Termos de Credenciamento na tabela DOCUMENTS: {len(docs)} ===')
for doc in docs:
    print(f'  - ID: {doc[0]}, Process: {doc[1]}, Type: {doc[2]}, Name: {doc[3]}')

# Verificar registros em special_documents
c.execute('SELECT * FROM special_documents')
special = c.fetchall()
print(f'\n=== Registros em SPECIAL_DOCUMENTS: {len(special)} ===')
for s in special:
    print(f'  {s}')

# Se há termos na tabela documents mas não em special_documents, migrar
if docs and not special:
    print('\n🔄 MIGRANDO termos existentes para special_documents...')
    for doc in docs:
        process_id = doc[1]
        c.execute('SELECT filename, name, mime_type, uploaded_by FROM documents WHERE id = ?', (doc[0],))
        full_doc = c.fetchone()
        
        c.execute('''INSERT INTO special_documents 
                     (process_id, document_type, version, status, filename, original_filename, 
                      mime_type, uploaded_by, uploaded_by_role, notes)
                     VALUES (?, ?, 1, 'excel_if', ?, ?, ?, ?, 'financial_institution', 'Migrado automaticamente')''',
                  (process_id, 'termo_credenciamento', full_doc[0], full_doc[1], full_doc[2], full_doc[3]))
    conn.commit()
    print('✅ Migração concluída!')

conn.close()
