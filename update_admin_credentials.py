"""
Atualizar credenciais do administrador
"""

import sqlite3
from werkzeug.security import generate_password_hash

def update_admin_credentials():
    conn = sqlite3.connect('credenciamento.db')
    cursor = conn.cursor()
    
    print("🔧 Atualizando credenciais do administrador...")
    
    # Verificar se admin existe
    cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    admin = cursor.fetchone()
    
    if admin:
        admin_id = admin[0]
        # Atualizar credenciais
        hashed_password = generate_password_hash('Fieleaquelequeprometeu')
        cursor.execute('''
            UPDATE users 
            SET email = ?, password = ?, name = ?
            WHERE id = ?
        ''', ('suporte.aicsj@gmail.com', hashed_password, 'Administrador do Sistema', admin_id))
        
        print("   ✅ Credenciais atualizadas!")
        print("   📧 Email: suporte.aicsj@gmail.com")
        print("   🔐 Senha: Fieleaquelequeprometeu")
    else:
        # Criar admin se não existir
        hashed_password = generate_password_hash('Fieleaquelequeprometeu')
        cursor.execute('''
            INSERT INTO users (name, email, password, cpf_cnpj, role, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        ''', ('Administrador do Sistema', 'suporte.aicsj@gmail.com', hashed_password, '00000000000', 'admin'))
        
        print("   ✅ Administrador criado!")
        print("   📧 Email: suporte.aicsj@gmail.com")
        print("   🔐 Senha: Fieleaquelequeprometeu")
    
    # Atualizar email de configuração
    cursor.execute('''
        UPDATE system_settings 
        SET setting_value = ? 
        WHERE setting_key = 'admin_email'
    ''', ('suporte.aicsj@gmail.com',))
    
    conn.commit()
    conn.close()
    
    print("\n✅ Atualização concluída com sucesso!")

if __name__ == '__main__':
    update_admin_credentials()
