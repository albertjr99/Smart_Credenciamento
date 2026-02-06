"""
Migration: Adicionar campos de perfil do usuário
Novos campos: endereco, telefone, email_institucional, foto_perfil
"""
import sqlite3
import os

def migrate():
    db_path = os.path.join(os.path.dirname(__file__), 'credenciamento.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Verificar colunas existentes
    c.execute("PRAGMA table_info(users)")
    existing_columns = [col[1] for col in c.fetchall()]
    
    # Adicionar novas colunas se não existirem
    new_columns = [
        ('endereco', 'TEXT'),
        ('telefone', 'TEXT'),
        ('email_institucional', 'TEXT'),
        ('foto_perfil', 'TEXT'),
        ('cidade', 'TEXT'),
        ('estado', 'TEXT'),
        ('cep', 'TEXT'),
        ('razao_social', 'TEXT'),
    ]
    
    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            try:
                c.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}')
                print(f'✅ Coluna "{col_name}" adicionada com sucesso!')
            except sqlite3.OperationalError as e:
                print(f'⚠️ Coluna "{col_name}": {e}')
        else:
            print(f'ℹ️ Coluna "{col_name}" já existe.')
    
    conn.commit()
    conn.close()
    print('\n✅ Migração de perfil de usuário concluída!')

if __name__ == '__main__':
    migrate()
