"""
Teste simples de conexão com Gemini API
"""
import os
from dotenv import load_dotenv

# Carregar .env
load_dotenv()

api_key = os.getenv('GEMINI_API_KEY')
print(f"📌 API Key configurada: {'Sim' if api_key else 'Não'}")
if api_key:
    print(f"📌 Primeiros 10 caracteres: {api_key[:10]}...")
    print(f"📌 Últimos 5 caracteres: ...{api_key[-5:]}")
    print(f"📌 Tamanho total: {len(api_key)} caracteres")

print("\n🧪 Testando conexão com Gemini...")

try:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    print("✅ Modelo configurado com sucesso!")
    print("📡 Enviando teste simples...")
    
    response = model.generate_content("Responda apenas com a palavra 'OK' se você conseguir me ler.")
    
    print(f"✅ SUCESSO! Resposta: {response.text}")
    
except Exception as e:
    print(f"❌ ERRO: {str(e)}")
    import traceback
    traceback.print_exc()
