import sqlite3
from werkzeug.security import generate_password_hash

# Conectar ao banco
conn = sqlite3.connect('credenciamento.db')
c = conn.cursor()

# Verificar se já existe admin
c.execute("SELECT * FROM users WHERE role = 'admin'")
admin = c.fetchone()

if admin:
    print(f"✓ Admin já existe: {admin[1]}")
else:
    # Criar admin
    admin_email = "admin@sistema.com"
    admin_password = generate_password_hash("admin123")
    admin_name = "Administrador do Sistema"
    admin_cpf = "00000000000"
    
    c.execute('''
        INSERT INTO users (email, password, name, cpf_cnpj, role)
        VALUES (?, ?, ?, ?, ?)
    ''', (admin_email, admin_password, admin_name, admin_cpf, 'admin'))
    
    conn.commit()
    print("✅ Admin criado com sucesso!")
    print(f"   Email: {admin_email}")
    print(f"   Senha: admin123")

conn.close()
