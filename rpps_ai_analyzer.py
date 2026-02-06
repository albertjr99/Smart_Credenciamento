"""
Análise de IA Robusta e Conteudista para RPPS
Sistema profissional de auxílio à decisão para analistas do RPPS
"""

from ai_config import get_ai_analysis, get_ai_status
import json

def generate_rpps_analysis(document_analysis, document_type, document_name, institution_name):
    """
    Gera análise ROBUSTA e CONTEUDISTA para o RPPS
    Auxilia o analista a tomar decisão fundamentada
    
    Args:
        document_analysis: Análise inicial do documento (da instituição financeira)
        document_type: Tipo do documento
        document_name: Nome do documento
        institution_name: Nome da instituição financeira
    
    Returns:
        Dict com análise completa, recomendação e justificativas
    """
    
    # Verificar se IA está disponível
    ai_status = get_ai_status()
    
    if not ai_status['available']:
        return {
            'available': False,
            'recommendation': 'manual_review',
            'message': 'IA não disponível. Análise manual recomendada.'
        }
    
    # Extrair informações da análise original
    ai_content = document_analysis.get('ai_content_analysis', {})
    is_valid = ai_content.get('is_valid', False)
    issues = ai_content.get('issues', [])
    warnings = ai_content.get('warnings', [])
    score = ai_content.get('score', 0)
    details = ai_content.get('details', {})
    
    # Construir contexto completo para a IA
    context = f"""
ANÁLISE PRÉVIA DO DOCUMENTO:
- Tipo: {document_type}
- Nome: {document_name}
- Instituição: {institution_name}
- Validação Inicial: {'APROVADO' if is_valid else 'REPROVADO'}
- Pontuação: {score}/100
- Problemas Identificados: {json.dumps(issues, ensure_ascii=False)}
- Avisos: {json.dumps(warnings, ensure_ascii=False)}
- Detalhes Técnicos: {json.dumps(details, ensure_ascii=False)}
"""
    
    # Prompt especializado para análise RPPS
    prompt = f"""Você é um ANALISTA SÊNIOR especializado em credenciamento de instituições financeiras para RPPS (Regime Próprio de Previdência Social).

Sua missão é fornecer uma ANÁLISE ROBUSTA, DENSA E CONTEUDISTA que auxilie o analista do RPPS a tomar a melhor decisão sobre a aprovação ou rejeição deste documento.

DOCUMENTO EM ANÁLISE:
- Tipo: {document_type}
- Instituição: {institution_name}
- Status da Validação Inicial: {"APROVADO" if is_valid else "REPROVADO"}

INFORMAÇÕES DA ANÁLISE PRÉVIA:
{context}

SUA ANÁLISE DEVE CONTER:

1. RESUMO EXECUTIVO (2-3 parágrafos):
   - Visão geral do documento e sua adequação ao processo de credenciamento
   - Principais pontos fortes e fracos identificados
   - Contexto e relevância para o RPPS

2. ANÁLISE DETALHADA E CONTEUDISTA:
   - Examine ESPECIFICAMENTE o conteúdo do documento
   - Aponte TRECHOS, SEÇÕES ou INFORMAÇÕES relevantes que encontrou
   - Avalie a QUALIDADE, COMPLETUDE e RELEVÂNCIA das informações
   - Identifique GAPS informativos ou inconsistências
   - Compare com MELHORES PRÁTICAS do mercado de previdência

3. PONTOS CRÍTICOS DE ATENÇÃO:
   - Liste ESPECIFICAMENTE cada ponto que o analista deve verificar manualmente
   - Justifique POR QUE cada ponto é importante
   - Sugira COMO validar cada ponto

4. RECOMENDAÇÃO FUNDAMENTADA:
   - Recomende claramente: APROVAR, REJEITAR ou SOLICITAR REVISÃO
   - Fundamente sua recomendação em CRITÉRIOS TÉCNICOS e REGULATÓRIOS
   - Explique as CONSEQUÊNCIAS de cada decisão
   - Se recomendar rejeição: liste os motivos ESPECÍFICOS e OBJETIVOS
   - Se recomendar aprovação: destaque os pontos fortes que justificam

5. CHECKLIST PARA O ANALISTA:
   - Crie checklist de verificações manuais que o analista deve fazer
   - Inclua referências normativas ou regulatórias relevantes
   - Sugira documentos complementares que podem ser solicitados

6. RISCOS E MITIGAÇÕES:
   - Identifique riscos associados à aprovação deste documento
   - Sugira medidas de mitigação ou condições para aprovação
   - Avalie impacto para o RPPS

FORMATO DE RESPOSTA OBRIGATÓRIO (JSON):
{{
    "executive_summary": "Resumo executivo denso de 2-3 parágrafos",
    "recommendation": "approve|reject|request_revision",
    "confidence_level": 0-100,
    "detailed_analysis": {{
        "content_quality": "Análise detalhada da qualidade do conteúdo com exemplos específicos",
        "completeness": "Avaliação da completude com gaps identificados",
        "compliance": "Conformidade regulatória e normativa",
        "specific_findings": ["Lista de achados específicos no documento com detalhes"]
    }},
    "critical_points": [
        {{
            "point": "Descrição do ponto crítico",
            "why_important": "Justificativa da importância",
            "how_to_validate": "Como o analista deve validar"
        }}
    ],
    "recommendation_rationale": {{
        "technical_criteria": ["Critérios técnicos que fundamentam a decisão"],
        "regulatory_compliance": ["Aspectos regulatórios considerados"],
        "risk_assessment": "Avaliação de risco desta decisão",
        "consequences": "Consequências esperadas da decisão recomendada"
    }},
    "analyst_checklist": [
        {{
            "task": "Tarefa de verificação",
            "reference": "Referência normativa/regulatória se aplicável",
            "priority": "high|medium|low"
        }}
    ],
    "risks_and_mitigation": [
        {{
            "risk": "Descrição do risco",
            "severity": "high|medium|low",
            "mitigation": "Medida de mitigação sugerida"
        }}
    ],
    "complementary_documents": ["Lista de documentos complementares que podem ser solicitados"],
    "final_remarks": "Considerações finais e observações importantes"
}}

Seja PROFUNDO, TÉCNICO e ÚTIL. Sua análise será crucial para a decisão do RPPS."""
    
    try:
        # Chamar IA para análise robusta
        result = get_ai_analysis(prompt, context, f"RPPS_Analysis_{document_type}")
        
        if result['success']:
            analysis_result = result['analysis']
            
            # Estruturar resposta
            return {
                'available': True,
                'analysis': analysis_result,
                'provider': result.get('provider', 'Desconhecido'),
                'confidence': analysis_result.get('confidence_level', 0),
                'recommendation': analysis_result.get('recommendation', 'request_revision'),
                'summary': analysis_result.get('executive_summary', ''),
                'generated_at': json.dumps({'provider': result.get('provider')}),
                'ai_powered': True
            }
        else:
            return {
                'available': False,
                'recommendation': 'manual_review',
                'message': f'Erro na análise: {result.get("error", "Desconhecido")}'
            }
            
    except Exception as e:
        print(f"Erro ao gerar análise RPPS: {e}")
        return {
            'available': False,
            'recommendation': 'manual_review',
            'message': f'Erro: {str(e)}'
        }


def create_rpps_decision_support(document_path, document_analysis, document_type, document_name, institution_name):
    """
    Cria sistema completo de suporte à decisão para o RPPS
    Inclui análise robusta + recomendação + justificativas
    """
    
    # Gerar análise robusta
    rpps_analysis = generate_rpps_analysis(
        document_analysis,
        document_type,
        document_name,
        institution_name
    )
    
    # Se análise não disponível, fornecer fallback básico
    if not rpps_analysis.get('available', False):
        ai_content = document_analysis.get('ai_content_analysis', {})
        return {
            'rpps_analysis_available': False,
            'basic_recommendation': 'manual_review',
            'basic_info': {
                'document_valid': ai_content.get('is_valid', False),
                'score': ai_content.get('score', 0),
                'issues_count': len(ai_content.get('issues', [])),
                'warnings_count': len(ai_content.get('warnings', []))
            },
            'message': rpps_analysis.get('message', 'Análise automática não disponível')
        }
    
    # Retornar análise completa
    return {
        'rpps_analysis_available': True,
        'analysis': rpps_analysis.get('analysis', {}),
        'recommendation': rpps_analysis.get('recommendation', 'manual_review'),
        'confidence': rpps_analysis.get('confidence', 0),
        'summary': rpps_analysis.get('summary', ''),
        'provider': rpps_analysis.get('provider', 'Desconhecido'),
        'ai_powered': True
    }
