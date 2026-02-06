#!/usr/bin/env python3
"""
Script para corrigir o original_filename dos documentos especiais
"""
import sqlite3
import os

def fix_special_documents():
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Buscar todos os documentos especiais
    c.execute('SELECT id, filename, original_filename, mime_type FROM special_documents')
    docs = c.fetchall()
    
    print(f"Encontrados {len(docs)} documentos especiais")
    
    for doc in docs:
        doc_id, filename, original_filename, mime_type = doc
        
        # Verificar se o original_filename já tem extensão
        _, ext = os.path.splitext(original_filename)
        
        if not ext:
            # Pegar a extensão do filename
            _, real_ext = os.path.splitext(filename)
            
            if real_ext:
                new_original = original_filename + real_ext
                c.execute('UPDATE special_documents SET original_filename = ? WHERE id = ?', 
                         (new_original, doc_id))
                print(f"  ID {doc_id}: '{original_filename}' -> '{new_original}'")
            else:
                print(f"  ID {doc_id}: Não foi possível determinar extensão de '{filename}'")
        else:
            print(f"  ID {doc_id}: OK - '{original_filename}'")
    
    conn.commit()
    
    # Verificar resultado
    print("\n--- Verificação final ---")
    c.execute('SELECT id, filename, original_filename FROM special_documents')
    for row in c.fetchall():
        print(f"  ID {row[0]}: {row[2]}")
    
    conn.close()
    print("\n✅ Concluído!")

if __name__ == "__main__":
    fix_special_documents()
