"""
Script para configurar a API OpenAI de forma simples
Execute: py configure_openai.py
"""

import os

print("=" * 60)
print("🔧 CONFIGURAÇÃO DA API OPENAI PARA ANÁLISE AVANÇADA")
print("=" * 60)
print()

# Verificar se já está configurada
current_key = os.getenv('OPENAI_API_KEY')
if current_key:
    print("✅ API OpenAI já está configurada!")
    print(f"   Chave atual: {current_key[:10]}...{current_key[-4:]}")
    print()
    response = input("Deseja atualizar a chave? (s/n): ")
    if response.lower() != 's':
        print("\n👍 Mantendo configuração atual.")
        exit()

print("\n📝 Para obter sua chave da API OpenAI:")
print("   1. Acesse: https://platform.openai.com/api-keys")
print("   2. Faça login ou crie uma conta")
print("   3. Clique em 'Create new secret key'")
print("   4. Copie a chave gerada")
print()

api_key = input("Cole sua chave da API OpenAI aqui: ").strip()

if not api_key or len(api_key) < 20:
    print("\n❌ Chave inválida. A chave deve começar com 'sk-' e ter mais de 20 caracteres.")
    exit()

# Testar a chave
print("\n🔄 Testando a chave...")
try:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    
    # Fazer uma requisição simples de teste
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "teste"}],
        max_tokens=5
    )
    
    print("✅ Chave válida e funcionando!")
    
except Exception as e:
    print(f"❌ Erro ao testar a chave: {str(e)}")
    print("\nVerifique se:")
    print("  - A chave está correta")
    print("  - Você tem créditos disponíveis na OpenAI")
    print("  - Sua conta OpenAI está ativa")
    exit()

# Salvar em arquivo .env
print("\n💾 Salvando configuração...")
with open('.env', 'w', encoding='utf-8') as f:
    f.write(f"OPENAI_API_KEY={api_key}\n")

print("✅ Configuração salva em .env")
print()
print("=" * 60)
print("🎉 CONFIGURAÇÃO CONCLUÍDA COM SUCESSO!")
print("=" * 60)
print()
print("📋 Próximos passos:")
print("   1. Reinicie o servidor Flask (Ctrl+C e execute 'py app.py' novamente)")
print("   2. A análise avançada com GPT-4 estará ativa")
print("   3. Você verá '🧠 Análise realizada com IA Avançada (GPT-4)' nos documentos")
print()
print("💰 Custos estimados:")
print("   - ~R$ 0,30 por documento analisado")
print("   - ~R$ 15,00 para 50 documentos/mês")
print()
