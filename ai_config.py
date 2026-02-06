"""
Configuração Avançada de IA para Análise de Documentos
Suporta múltiplos provedores: OpenAI, Anthropic Claude, Google Gemini
Sistema profissional e robusto para produção
"""

import os
import json
from typing import Optional, Dict, Any, List

class AIProvider:
    """Classe base para provedores de IA"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = None
        
    def analyze(self, prompt: str, context: str, system_prompt: str) -> Dict[str, Any]:
        raise NotImplementedError


class OpenAIProvider(AIProvider):
    """Provedor OpenAI GPT-4"""
    
    def __init__(self, api_key: str):
        super().__init__(api_key)
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key)
            self.available = True
        except Exception as e:
            print(f"OpenAI não disponível: {e}")
            self.available = False
    
    def analyze(self, prompt: str, context: str, system_prompt: str) -> Dict[str, Any]:
        if not self.available:
            return {'success': False, 'error': 'OpenAI não disponível'}
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",  # Modelo mais avançado
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{prompt}\n\nCONTEÚDO DO DOCUMENTO:\n{context[:8000]}"}
                ],
                temperature=0.1,  # Mais determinístico
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            return {
                'success': True,
                'analysis': result,
                'provider': 'OpenAI GPT-4 Turbo',
                'tokens_used': response.usage.total_tokens,
                'cost_estimate': response.usage.total_tokens * 0.00003  # Estimativa em USD
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


class AnthropicProvider(AIProvider):
    """Provedor Anthropic Claude"""
    
    def __init__(self, api_key: str):
        super().__init__(api_key)
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
            self.available = True
        except Exception as e:
            print(f"Anthropic Claude não disponível: {e}")
            self.available = False
    
    def analyze(self, prompt: str, context: str, system_prompt: str) -> Dict[str, Any]:
        if not self.available:
            return {'success': False, 'error': 'Anthropic Claude não disponível'}
        
        try:
            message = self.client.messages.create(
                model="claude-3-opus-20240229",  # Modelo mais avançado
                max_tokens=2000,
                temperature=0.1,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": f"{prompt}\n\nCONTEÚDO DO DOCUMENTO:\n{context[:8000]}"}
                ]
            )
            
            # Claude retorna texto, precisamos pedir JSON estruturado
            content = message.content[0].text
            
            # Tentar parsear como JSON
            try:
                result = json.loads(content)
            except:
                # Se não for JSON válido, criar estrutura
                result = {
                    'is_valid': False,
                    'score': 50,
                    'issues': ['Resposta da IA não estruturada corretamente'],
                    'warnings': [],
                    'summary': content[:500]
                }
            
            return {
                'success': True,
                'analysis': result,
                'provider': 'Anthropic Claude 3 Opus',
                'tokens_used': message.usage.input_tokens + message.usage.output_tokens,
                'cost_estimate': (message.usage.input_tokens * 0.000015 + message.usage.output_tokens * 0.000075)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


class GeminiProvider(AIProvider):
    """Provedor Google Gemini - Usando novo SDK google-genai"""
    
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.api_key = api_key
        try:
            from google import genai
            self.client = genai.Client(api_key=api_key)
            self.available = True
        except Exception as e:
            print(f"Google Gemini não disponível: {e}")
            self.available = False
    
    def analyze(self, prompt: str, context: str, system_prompt: str) -> Dict[str, Any]:
        if not self.available:
            return {'success': False, 'error': 'Google Gemini não disponível'}
        
        import time
        
        # Lista de modelos para tentar (nomes corretos para o novo SDK google-genai)
        # Formato: models/nome-do-modelo
        models_to_try = ['models/gemini-2.0-flash', 'models/gemini-1.5-flash', 'models/gemini-1.5-pro']
        max_retries = 2
        
        for model_name in models_to_try:
            for attempt in range(max_retries):
                try:
                    print(f"🤖 [GEMINI] Tentativa {attempt + 1}/{max_retries} com modelo {model_name}...")
                    full_prompt = f"{system_prompt}\n\n{prompt}\n\nCONTEÚDO DO DOCUMENTO:\n{context[:8000]}"
                    
                    # Usar o novo SDK google-genai
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=full_prompt
                    )
                    
                    response_text = response.text
                    print(f"📡 [GEMINI] Resposta recebida: {len(response_text)} caracteres")
                    print(f"📄 [GEMINI] Primeiros 200 caracteres: {response_text[:200]}")
            
                    # Tentar parsear como JSON
                    try:
                        # Limpar resposta se tiver markdown
                        cleaned_text = response_text.strip()
                        if '```json' in cleaned_text:
                            cleaned_text = cleaned_text.split('```json')[1].split('```')[0].strip()
                        elif '```' in cleaned_text:
                            cleaned_text = cleaned_text.split('```')[1].split('```')[0].strip()
                        
                        result = json.loads(cleaned_text)
                        print(f"✅ [GEMINI] JSON parseado com sucesso!")
                    except Exception as parse_error:
                        print(f"❌ [GEMINI] Erro ao parsear JSON: {str(parse_error)}")
                        print(f"📝 [GEMINI] Texto completo da resposta:\n{response_text}")
                        result = {
                            'is_valid': False,
                            'score': 50,
                            'issues': ['Resposta da IA não estruturada corretamente'],
                            'warnings': [],
                            'summary': response_text[:500]
                        }
                    
                    return {
                        'success': True,
                        'analysis': result,
                        'provider': f'Google Gemini ({model_name})',
                        'tokens_used': 'N/A',
                        'cost_estimate': 0.0001
                    }
                    
                except Exception as e:
                    error_str = str(e)
                    print(f"⚠️ [GEMINI] Erro com {model_name} (tentativa {attempt + 1}): {error_str[:200]}")
                    
                    # Se for erro de quota (429), esperar e tentar novamente
                    if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str:
                        wait_time = (attempt + 1) * 5  # 5s, 10s, 15s
                        print(f"⏳ [GEMINI] Quota excedida. Aguardando {wait_time}s antes de tentar novamente...")
                        time.sleep(wait_time)
                    else:
                        # Outro erro, tentar próximo modelo
                        break
        
        # Se todos falharam
        print(f"❌ [GEMINI] Todos os modelos e tentativas falharam")
        return {'success': False, 'error': 'Todos os modelos Gemini falharam - quota excedida ou erro de API'}


class AIAnalysisEngine:
    """Motor de Análise de IA - Sistema Robusto Multi-Provedor"""
    
    def __init__(self):
        self.providers = {}
        self.active_provider = None
        self._load_configuration()
    
    def _load_configuration(self):
        """Carrega configuração de múltiplas fontes"""
        
        # Carregar de .env se existir
        if os.path.exists('.env'):
            print("📄 Carregando arquivo .env...")
            with open('.env', 'r') as f:
                for line in f:
                    if '=' in line and not line.startswith('#'):
                        key, value = line.strip().split('=', 1)
                        os.environ[key] = value
                        print(f"   ✓ {key} configurado")
        else:
            print("⚠️  Arquivo .env não encontrado!")
        
        # Configurar provedores disponíveis
        openai_key = os.getenv('OPENAI_API_KEY')
        if openai_key:
            print("🔧 Configurando OpenAI...")
            self.providers['openai'] = OpenAIProvider(openai_key)
            if self.providers['openai'].available:
                self.active_provider = 'openai'
                print("   ✅ OpenAI ativo!")
        
        anthropic_key = os.getenv('ANTHROPIC_API_KEY')
        if anthropic_key:
            print("🔧 Configurando Anthropic...")
            self.providers['anthropic'] = AnthropicProvider(anthropic_key)
            if not self.active_provider and self.providers['anthropic'].available:
                self.active_provider = 'anthropic'
                print("   ✅ Anthropic ativo!")
        
        gemini_key = os.getenv('GEMINI_API_KEY')
        if gemini_key:
            print("🔧 Configurando Google Gemini...")
            self.providers['gemini'] = GeminiProvider(gemini_key)
            if not self.active_provider and self.providers['gemini'].available:
                self.active_provider = 'gemini'
                print("   ✅ Gemini ativo!")
        
        # Preferência configurável
        preferred = os.getenv('AI_PROVIDER', '').lower()
        if preferred in self.providers and self.providers[preferred].available:
            self.active_provider = preferred
            print(f"🎯 Provedor preferido configurado: {preferred}")
        
        if self.active_provider:
            print(f"\n✅ IA CONFIGURADA: Usando {self.active_provider.upper()}")
        else:
            print("\n❌ NENHUMA IA CONFIGURADA! Sistema usará análise básica.")
    
    def is_available(self) -> bool:
        """Verifica se há IA disponível"""
        return self.active_provider is not None and self.active_provider in self.providers
    
    def get_provider_info(self) -> Dict[str, Any]:
        """Retorna informações do provedor ativo"""
        if not self.is_available():
            return {
                'available': False,
                'provider': None,
                'all_providers': list(self.providers.keys())
            }
        
        return {
            'available': True,
            'provider': self.active_provider,
            'all_providers': list(self.providers.keys())
        }
    
    def analyze_document(self, prompt: str, context: str, document_type: str) -> Dict[str, Any]:
        """
        Analisa documento com IA de forma robusta
        Implementa retry e fallback entre provedores
        """
        
        if not self.is_available():
            return {
                'success': False,
                'error': 'Nenhum provedor de IA configurado',
                'fallback': True
            }
        
        # System prompt profissional e detalhado
        system_prompt = """Você é um analista especializado em credenciamento de instituições financeiras para RPPS (Regime Próprio de Previdência Social).

Sua análise deve ser RIGOROSA, PROFISSIONAL e PRECISA.

RESPONSABILIDADES CRÍTICAS:
1. Verificar se o documento é REALMENTE do tipo esperado
2. Confirmar que o documento menciona a instituição financeira correta
3. Avaliar completude informacional (informações não podem ser rasas, genéricas ou superficiais)
4. Verificar coerência e relevância das informações
5. Identificar inconsistências, erros ou tentativas de envio de documentos inadequados

CRITÉRIOS DE REJEIÇÃO AUTOMÁTICA:
- Documento não é do tipo esperado (ex: enviaram "Termo de Credenciamento" mas disseram ser "Apresentação Institucional")
- Documento não menciona a instituição financeira correta
- Conteúdo genérico, copiado ou não relacionado ao credenciamento
- Informações insuficientes, rasas ou irrelevantes
- Documento trata de outro assunto/empresa
- Dados contraditórios ou inconsistentes

FORMATO DE RESPOSTA OBRIGATÓRIO (JSON):
{
    "is_valid": true/false,
    "confidence_score": 0.0-1.0,
    "score": 0-100,
    "document_type_correct": true/false,
    "institution_mentioned": true/false,
    "content_quality": "excellent/good/fair/poor",
    "completeness": 0-100,
    "coherence": 0-100,
    "issues": ["lista de problemas CRÍTICOS encontrados"],
    "warnings": ["lista de avisos e pontos de atenção"],
    "recommendations": ["recomendações para melhoria"],
    "extracted_data": {
        "institution_name": "nome encontrado",
        "dates_found": ["datas"],
        "key_information": ["informações chave"]
    },
    "summary": "resumo executivo da análise em 2-3 sentenças",
    "detailed_analysis": "análise detalhada e fundamentada"
}

Seja CRÍTICO e OBJETIVO. Este sistema é comercial e precisa ser confiável."""

        # Tentar com provedor ativo
        provider = self.providers[self.active_provider]
        result = provider.analyze(prompt, context, system_prompt)
        
        if result['success']:
            result['engine_info'] = {
                'provider': self.active_provider,
                'fallback_used': False
            }
            return result
        
        # Fallback: tentar outros provedores
        for provider_name, provider_obj in self.providers.items():
            if provider_name != self.active_provider:
                print(f"Tentando fallback para {provider_name}...")
                result = provider_obj.analyze(prompt, context, system_prompt)
                if result['success']:
                    result['engine_info'] = {
                        'provider': provider_name,
                        'fallback_used': True,
                        'original_provider': self.active_provider
                    }
                    return result
        
        # Se todos falharam
        return {
            'success': False,
            'error': 'Todos os provedores de IA falharam',
            'fallback': True
        }


# Instância global do motor de IA
ai_engine = AIAnalysisEngine()


def get_ai_analysis(prompt: str, context: str, document_type: str) -> Dict[str, Any]:
    """
    Função principal para obter análise de IA
    Interface simplificada para o resto do sistema
    """
    return ai_engine.analyze_document(prompt, context, document_type)


def get_ai_status() -> Dict[str, Any]:
    """Retorna status da configuração de IA"""
    return ai_engine.get_provider_info()
