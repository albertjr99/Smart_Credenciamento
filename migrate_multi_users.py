"""
Script para migrar o banco de dados para suportar múltiplos usuários por entidade
Adiciona tabela de usuários e campo de autorização de processos
"""
import sqlite3
import secrets
from datetime import datetime

def migrate_database():
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    print("=== Iniciando Migração Multi-Usuários ===\n")
    
    # 1. Atualizar tabela de usuários existente
    print("1. Atualizando tabela de usuários...")
    
    # A tabela users já existe com: id, email, password, name, cpf_cnpj, role, created_at
    # Vamos adicionar os campos necessários
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN entity_id INTEGER')
        print("   ✓ Campo entity_id adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo entity_id já existe")
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1')
        print("   ✓ Campo is_active adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo is_active já existe")
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN reset_token TEXT')
        print("   ✓ Campo reset_token adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo reset_token já existe")
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN reset_token_expires TEXT')
        print("   ✓ Campo reset_token_expires adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo reset_token_expires já existe")
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN last_login TEXT')
        print("   ✓ Campo last_login adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo last_login já existe")
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN user_number INTEGER')  # 1 a 5 para cada entidade
        print("   ✓ Campo user_number adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo user_number já existe")
    
    # 2. Adicionar campo de autorização em processes
    print("\n2. Adicionando campos de autorização em processes...")
    try:
        c.execute('ALTER TABLE processes ADD COLUMN is_authorized INTEGER DEFAULT 0')
        print("   ✓ Campo is_authorized adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo is_authorized já existe")
    
    try:
        c.execute('ALTER TABLE processes ADD COLUMN authorized_by INTEGER')
        print("   ✓ Campo authorized_by adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo authorized_by já existe")
    
    try:
        c.execute('ALTER TABLE processes ADD COLUMN authorized_at TEXT')
        print("   ✓ Campo authorized_at adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo authorized_at já existe")
    
    # 3. Adicionar campos para análise de IA
    print("\n3. Adicionando campos para análise de IA...")
    try:
        c.execute('ALTER TABLE processes ADD COLUMN ai_pre_analysis TEXT')  # JSON com análise prévia da IF
        print("   ✓ Campo ai_pre_analysis adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo ai_pre_analysis já existe")
    
    try:
        c.execute('ALTER TABLE processes ADD COLUMN ai_full_analysis TEXT')  # JSON com análise completa do RPPS
        print("   ✓ Campo ai_full_analysis adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo ai_full_analysis já existe")
    
    try:
        c.execute('ALTER TABLE processes ADD COLUMN ai_analysis_date TEXT')
        print("   ✓ Campo ai_analysis_date adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo ai_analysis_date já existe")
    
    # 4. Adicionar campos de validação de assinatura em documents
    print("\n4. Adicionando campos de validação de assinatura em documents...")
    try:
        c.execute('ALTER TABLE documents ADD COLUMN has_signature INTEGER DEFAULT 0')
        print("   ✓ Campo has_signature adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo has_signature já existe")
    
    try:
        c.execute('ALTER TABLE documents ADD COLUMN signature_valid INTEGER')
        print("   ✓ Campo signature_valid adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo signature_valid já existe")
    
    try:
        c.execute('ALTER TABLE documents ADD COLUMN signature_info TEXT')  # JSON com informações do certificado
        print("   ✓ Campo signature_info adicionado")
    except sqlite3.OperationalError:
        print("   ⚠ Campo signature_info já existe")
    
    # 5. Atualizar usuários existentes com entity_id
    print("\n5. Atualizando usuários existentes...")
    c.execute('SELECT id, role FROM users WHERE entity_id IS NULL')
    existing_users = c.fetchall()
    
    updated = 0
    for user in existing_users:
        user_id, role = user
        
        # Para usuários existentes, vamos assumir que eles são o primeiro usuário da sua entidade
        # Na prática, você precisará mapear corretamente cada usuário à sua entidade
        c.execute('''
            UPDATE users 
            SET entity_id = id, user_number = 1, is_active = 1
            WHERE id = ?
        ''', (user_id,))
        
        updated += 1
        print(f"   ✓ Usuário ID {user_id} atualizado")
    
    print(f"\n   Total atualizado: {updated} usuários")
    
    # 6. Criar índices
    print("\n6. Criando índices...")
    try:
        c.execute('CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_users_entity ON users(entity_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_users_reset_token ON users(reset_token)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_processes_authorized ON processes(is_authorized)')
        print("   ✓ Índices criados")
    except Exception as e:
        print(f"   ⚠ Erro ao criar índices: {e}")
    
    conn.commit()
    conn.close()
    
    print("\n=== Migração Concluída com Sucesso! ===")
    print("\nPróximos passos:")
    print("1. Atualizar app.py para usar a nova tabela users")
    print("2. Implementar sistema de tokens de redefinição de senha")
    print("3. Criar interface administrativa para gerenciar usuários")
    print("4. Implementar modal de autorização no portal RPPS")

if __name__ == '__main__':
    migrate_database()
