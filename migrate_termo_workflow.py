"""
Migração: Adicionar campos de workflow para Termo de Credenciamento
"""
import sqlite3

def migrate():
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    try:
        # Adicionar colunas para workflow do termo de credenciamento
        columns_to_add = [
            ('workflow_status', 'TEXT DEFAULT "initial"'),  # initial, prepared_for_if, signed_by_if, final_signed
            ('workflow_version', 'INTEGER DEFAULT 1'),      # Controle de versão
            ('original_filename', 'TEXT'),                   # Nome original do arquivo
            ('prepared_by', 'TEXT'),                         # Quem preparou o PDF
            ('prepared_at', 'TEXT'),                         # Quando foi preparado
            ('signed_by_if_at', 'TEXT'),                     # Quando IF assinou
            ('final_signed_at', 'TEXT'),                     # Quando RPPS assinou final
        ]
        
        for column_name, column_type in columns_to_add:
            try:
                c.execute(f'ALTER TABLE documents ADD COLUMN {column_name} {column_type}')
                print(f'✅ Coluna {column_name} adicionada!')
            except sqlite3.OperationalError as e:
                if 'duplicate column name' in str(e).lower():
                    print(f'⚠️  Coluna {column_name} já existe')
                else:
                    print(f'❌ Erro ao adicionar {column_name}: {e}')
        
        conn.commit()
        print('\n✅ Migração concluída com sucesso!')
        
    except Exception as e:
        print(f'❌ Erro na migração: {e}')
        conn.rollback()
    
    finally:
        conn.close()

if __name__ == '__main__':
    print('🔄 Iniciando migração de workflow do Termo de Credenciamento...\n')
    migrate()
