"""
Migração para adicionar funcionalidades administrativas
- Tabela de assinaturas
- Configurações de valores
- Logs de atividades
"""

import sqlite3
from datetime import datetime

def migrate_admin_features():
    conn = sqlite3.connect('credenciamento.db')
    cursor = conn.cursor()
    
    print("🔧 Iniciando migração para painel administrativo...")
    
    # Tabela de assinaturas
    print("📦 Criando tabela de assinaturas...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organization_id INTEGER NOT NULL,
        plan_type TEXT NOT NULL,
        annual_value REAL NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        payment_method TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (organization_id) REFERENCES organizations(id)
    )
    ''')
    
    # Tabela de pagamentos
    print("💰 Criando tabela de pagamentos...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subscription_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        payment_date TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        payment_method TEXT,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
    )
    ''')
    
    # Tabela de configurações do sistema
    print("⚙️ Criando tabela de configurações...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS system_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        setting_key TEXT UNIQUE NOT NULL,
        setting_value TEXT NOT NULL,
        description TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Tabela de logs de auditoria
    print("📋 Criando tabela de auditoria...")
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT NOT NULL,
        entity_type TEXT,
        entity_id INTEGER,
        details TEXT,
        ip_address TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    ''')
    
    # Adicionar valores padrão nas configurações
    print("📝 Inserindo configurações padrão...")
    default_settings = [
        ('default_rpps_annual_fee', '5000.00', 'Valor anual padrão para assinatura RPPS'),
        ('default_financial_annual_fee', '8000.00', 'Valor anual padrão para assinatura Instituição Financeira'),
        ('system_currency', 'BRL', 'Moeda do sistema'),
        ('company_name', 'Sistema de Credenciamento RPPS', 'Nome da empresa'),
        ('admin_email', 'admin@credenciamento.com', 'Email do administrador'),
        ('enable_notifications', 'true', 'Ativar notificações por email')
    ]
    
    for key, value, description in default_settings:
        cursor.execute('''
            INSERT OR IGNORE INTO system_settings (setting_key, setting_value, description)
            VALUES (?, ?, ?)
        ''', (key, value, description))
    
    # Verificar se existe usuário admin
    print("👤 Verificando usuário administrador...")
    cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    admin_exists = cursor.fetchone()
    
    if not admin_exists:
        print("➕ Criando usuário administrador padrão...")
        cursor.execute('''
            INSERT INTO users (name, email, password, cpf_cnpj, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('Administrador', 'admin@sistema.com', 'admin123', '00000000000', 'admin', datetime.now().isoformat()))
        print("   ✅ Usuário admin criado!")
        print("   📧 Email: admin@sistema.com")
        print("   🔐 Senha: admin123")
    else:
        print("   ✅ Usuário admin já existe")
    
    # Adicionar coluna de tipo em organizations se não existir
    print("🏢 Verificando estrutura de organizations...")
    cursor.execute("PRAGMA table_info(organizations)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'organization_type' not in columns:
        print("   ➕ Adicionando coluna organization_type...")
        cursor.execute('ALTER TABLE organizations ADD COLUMN organization_type TEXT DEFAULT "rpps"')
    
    if 'status' not in columns:
        print("   ➕ Adicionando coluna status...")
        cursor.execute('ALTER TABLE organizations ADD COLUMN status TEXT DEFAULT "active"')
    
    if 'cnpj' not in columns:
        print("   ➕ Adicionando coluna cnpj...")
        cursor.execute('ALTER TABLE organizations ADD COLUMN cnpj TEXT')
    
    if 'phone' not in columns:
        print("   ➕ Adicionando coluna phone...")
        cursor.execute('ALTER TABLE organizations ADD COLUMN phone TEXT')
    
    conn.commit()
    conn.close()
    
    print("\n✅ Migração concluída com sucesso!")
    print("🎯 Painel administrativo está pronto para uso!")

if __name__ == '__main__':
    migrate_admin_features()
