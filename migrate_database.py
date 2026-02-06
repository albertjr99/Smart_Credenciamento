"""
Script de Migração do Banco de Dados
Adiciona novas tabelas e funcionalidades para o sistema completo
"""

import sqlite3
from datetime import datetime

def upgrade_database():
    """Atualiza banco de dados com novas funcionalidades"""
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    print("🔄 Iniciando migração do banco de dados...")
    
    # 1. Adicionar coluna para análise RPPS nos documentos (se não existir)
    try:
        c.execute('''ALTER TABLE documents ADD COLUMN rpps_analysis TEXT''')
        print("✅ Coluna rpps_analysis adicionada")
    except:
        print("⚠️  Coluna rpps_analysis já existe")
    
    # 2. Tabela de devoluções/retornos de processos
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS process_returns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            process_id INTEGER NOT NULL,
            returned_by INTEGER NOT NULL,
            returned_to INTEGER NOT NULL,
            reason TEXT NOT NULL,
            observations TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            FOREIGN KEY (process_id) REFERENCES processes(id),
            FOREIGN KEY (returned_by) REFERENCES users(id),
            FOREIGN KEY (returned_to) REFERENCES users(id)
        )''')
        print("✅ Tabela process_returns criada")
    except Exception as e:
        print(f"⚠️  Erro ao criar process_returns: {e}")
    
    # 3. Tabela de histórico de ações
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS action_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            process_id INTEGER,
            document_id INTEGER,
            user_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            action_details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (process_id) REFERENCES processes(id),
            FOREIGN KEY (document_id) REFERENCES documents(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )''')
        print("✅ Tabela action_history criada")
    except Exception as e:
        print(f"⚠️  Erro ao criar action_history: {e}")
    
    # 4. Tabela de logs de e-mails
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS email_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            process_id INTEGER,
            recipient_email TEXT NOT NULL,
            recipient_name TEXT,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'sent',
            error_message TEXT,
            FOREIGN KEY (process_id) REFERENCES processes(id)
        )''')
        print("✅ Tabela email_logs criada")
    except Exception as e:
        print(f"⚠️  Erro ao criar email_logs: {e}")
    
    # 5. Tabela de organizações (instituições + RPPS)
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            cnpj TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            type TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )''')
        print("✅ Tabela organizations criada")
    except Exception as e:
        print(f"⚠️  Erro ao criar organizations: {e}")
    
    # 6. Adicionar role 'admin' se não existir na tabela users
    try:
        c.execute("ALTER TABLE users ADD COLUMN organization_id INTEGER REFERENCES organizations(id)")
        print("✅ Coluna organization_id adicionada a users")
    except:
        print("⚠️  Coluna organization_id já existe em users")
    
    # 7. Adicionar status de devolução aos processos
    try:
        c.execute("ALTER TABLE processes ADD COLUMN return_count INTEGER DEFAULT 0")
        print("✅ Coluna return_count adicionada a processes")
    except:
        print("⚠️  Coluna return_count já existe em processes")
    
    try:
        c.execute("ALTER TABLE processes ADD COLUMN last_returned_at TIMESTAMP")
        print("✅ Coluna last_returned_at adicionada a processes")
    except:
        print("⚠️  Coluna last_returned_at já existe em processes")
    
    conn.commit()
    conn.close()
    
    print("\n✅ Migração do banco de dados concluída!")
    print("🎉 Sistema pronto para novas funcionalidades\n")

if __name__ == '__main__':
    upgrade_database()
