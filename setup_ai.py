"""
Configurador Profissional de IA para Sistema de Credenciamento
Suporta: OpenAI GPT-4, Anthropic Claude, Google Gemini
"""

import os
import sys

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    print("=" * 70)
    print("🚀 SISTEMA PROFISSIONAL DE CREDENCIAMENTO RPPS")
    print("   Configurador de Inteligência Artificial Avançada")
    print("=" * 70)
    print()

def test_openai(api_key):
    """Testa configuração OpenAI GPT-4"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[{"role": "user", "content": "Teste"}],
            max_tokens=5
        )
        
        return True, "OpenAI GPT-4 Turbo configurado com sucesso!"
    except Exception as e:
        return False, f"Erro: {str(e)}"

def test_anthropic(api_key):
    """Testa configuração Anthropic Claude"""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        
        message = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=10,
            messages=[{"role": "user", "content": "Teste"}]
        )
        
        return True, "Anthropic Claude 3 Opus configurado com sucesso!"
    except Exception as e:
        return False, f"Erro: {str(e)}"

def test_gemini(api_key):
    """Testa configuração Google Gemini"""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content("Teste")
        
        return True, "Google Gemini 1.5 Flash configurado com sucesso!"
    except Exception as e:
        return False, f"Erro: {str(e)}"

def configure_provider(provider_name, test_func):
    """Configura um provedor específico"""
    print(f"\n📝 Configurando {provider_name}")
    print("-" * 70)
    
    api_key = input(f"Cole sua API Key do {provider_name} (ou ENTER para pular): ").strip()
    
    if not api_key:
        print(f"⏭️  Pulando {provider_name}")
        return None
    
    print(f"\n🔄 Testando {provider_name}...")
    success, message = test_func(api_key)
    
    if success:
        print(f"✅ {message}")
        return api_key
    else:
        print(f"❌ {message}")
        retry = input("\nTentar novamente? (s/n): ").lower()
        if retry == 's':
            return configure_provider(provider_name, test_func)
        return None

def main():
    clear_screen()
    print_header()
    
    print("Este configurador permite usar IA de múltiplos provedores:")
    print("  1️⃣  OpenAI GPT-4 Turbo (Recomendado) - Mais preciso")
    print("  2️⃣  Anthropic Claude 3 Opus - Excelente alternativa")
    print("  3️⃣  Google Gemini Pro - Opção gratuita com limites")
    print()
    print("💡 Você pode configurar TODOS ou apenas um. O sistema usa")
    print("   o melhor disponível e faz fallback automático se um falhar.")
    print()
    
    input("Pressione ENTER para continuar...")
    
    config = {}
    
    # Configurar OpenAI
    clear_screen()
    print_header()
    print("🔵 OPENAI GPT-4 TURBO (Recomendado)")
    print("-" * 70)
    print("✅ Mais preciso e confiável")
    print("✅ Melhor para análise profissional")
    print("💰 ~$0.06 por documento (~R$ 0,30)")
    print("🔗 Obter chave: https://platform.openai.com/api-keys")
    print()
    
    openai_key = configure_provider("OpenAI GPT-4", test_openai)
    if openai_key:
        config['OPENAI_API_KEY'] = openai_key
    
    # Configurar Anthropic
    clear_screen()
    print_header()
    print("🟣 ANTHROPIC CLAUDE 3 OPUS")
    print("-" * 70)
    print("✅ Excelente qualidade de análise")
    print("✅ Alternativa robusta ao GPT-4")
    print("💰 ~$0.05 por documento (~R$ 0,25)")
    print("🔗 Obter chave: https://console.anthropic.com/settings/keys")
    print()
    
    anthropic_key = configure_provider("Anthropic Claude", test_anthropic)
    if anthropic_key:
        config['ANTHROPIC_API_KEY'] = anthropic_key
    
    # Configurar Gemini
    clear_screen()
    print_header()
    print("🟡 GOOGLE GEMINI PRO")
    print("-" * 70)
    print("✅ Opção gratuita (com limites)")
    print("⚠️  Menos preciso que GPT-4/Claude")
    print("💰 Gratuito até certo limite")
    print("🔗 Obter chave: https://makersuite.google.com/app/apikey")
    print()
    
    gemini_key = configure_provider("Google Gemini", test_gemini)
    if gemini_key:
        config['GEMINI_API_KEY'] = gemini_key
    
    # Salvar configuração
    clear_screen()
    print_header()
    
    if not config:
        print("❌ Nenhum provedor foi configurado!")
        print("\n⚠️  O sistema funcionará com análise básica (menos preciso).")
        print("\nExecute este script novamente quando quiser configurar IA.")
        sys.exit(1)
    
    print("💾 Salvando configuração...")
    
    # Salvar em .env
    with open('.env', 'w', encoding='utf-8') as f:
        for key, value in config.items():
            f.write(f"{key}={value}\n")
        
        # Definir provedor preferido
        if 'OPENAI_API_KEY' in config:
            f.write("AI_PROVIDER=openai\n")
        elif 'ANTHROPIC_API_KEY' in config:
            f.write("AI_PROVIDER=anthropic\n")
        elif 'GEMINI_API_KEY' in config:
            f.write("AI_PROVIDER=gemini\n")
    
    print("✅ Configuração salva em .env")
    print()
    print("=" * 70)
    print("🎉 CONFIGURAÇÃO CONCLUÍDA COM SUCESSO!")
    print("=" * 70)
    print()
    print("📊 Provedores configurados:")
    for key in config.keys():
        provider = key.replace('_API_KEY', '')
        print(f"   ✅ {provider}")
    print()
    print("📋 Próximos passos:")
    print("   1. Reinicie o servidor Flask")
    print("      • Pressione Ctrl+C no terminal do servidor")
    print("      • Execute: py app.py")
    print()
    print("   2. A IA avançada estará ativa!")
    print("      • Você verá análises muito mais precisas")
    print("      • Detecção automática de documentos errados")
    print("      • Feedback profissional e detalhado")
    print()
    print("   3. Teste enviando documentos:")
    print("      • Tente enviar documento errado de propósito")
    print("      • O sistema vai rejeitar e explicar o porquê")
    print()
    print("💡 Dica: Se um provedor falhar, o sistema automaticamente")
    print("   tenta usar outro provedor configurado (fallback inteligente)")
    print()
    input("Pressione ENTER para finalizar...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Configuração cancelada pelo usuário.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Erro inesperado: {e}")
        sys.exit(1)
