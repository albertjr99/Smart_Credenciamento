"""
=============================================================================
BASE DE CONHECIMENTO DO AGENTE DE IA - ANÁLISE DE DOCUMENTOS
Sistema Profissional de Credenciamento RPPS
=============================================================================

Este módulo contém TODO o conhecimento especializado do agente de IA
para análise e validação de documentos de credenciamento.

DOCUMENTOS COBERTOS:
1. Apresentação Institucional (PDF/PPTX)
2. Checklist de Credenciamento (Excel)
3. Informações Preenchimento CadPrev (Excel)
4. Formulário Termo de Credenciamento (Excel)
5. Declaração Unificada (PDF) - REQUER ASSINATURA VÁLIDA
6. Relatório Agência de Risco/Rating (PDF)
7. Certidões (CVM, BACEN, etc.)

REGRAS CRÍTICAS:
- Documentos com assinatura digital inválida: reportar no feedback
- Declaração Unificada: assinatura inválida = INVALIDA credenciamento
- Termo de Declaração: assinatura inválida = INVALIDA credenciamento
"""

from datetime import datetime, timedelta
from dateutil import parser as date_parser
import re
import json

# =============================================================================
# DEFINIÇÕES DE CORES PARA ANÁLISE DE EXCEL
# =============================================================================

EXCEL_COLORS = {
    # Cores para Checklist
    'green_check': ['92D050', '00B050', '00FF00', 'A9D08E'],  # Verde - OK/Aprovado
    'red_x': ['FF0000', 'C00000', 'FF6666'],  # Vermelho - Reprovado
    
    # Cores para CadPrev
    'cadprev_question_blue': ['00B0F0', '0070C0', '4472C4', '5B9BD5'],  # Azul - Perguntas
    'cadprev_answer_yellow': ['FFFF00', 'FFC000', 'FFEB9C', 'FFE699'],  # Amarelo - Respostas
    
    # Cores para Termo de Credenciamento
    'termo_institution_orange': ['FF6600', 'F4B084', 'ED7D31', 'FABF8F', 'FFC000'],  # Laranja/Pêssego - Instituição deve preencher
    'termo_rpps_white': ['FFFFFF', 'F2F2F2'],  # Branco/Cinza claro - RPPS preenche
}

# =============================================================================
# SÍMBOLOS DE VALIDAÇÃO
# =============================================================================

CHECK_SYMBOLS = ['✓', '✔', '☑', 'V', 'v', True, 'Sim', 'SIM', 'OK', 'ok', 'Ok']
X_SYMBOLS = ['✗', '✘', '☒', 'X', 'x', False, 'Não', 'NÃO', 'NAO', 'nao']

# =============================================================================
# DOCUMENTO 1: APRESENTAÇÃO INSTITUCIONAL
# =============================================================================

APRESENTACAO_INSTITUCIONAL = {
    'name': 'Apresentação Institucional',
    'formats': ['.pdf', '.pptx', '.ppt'],
    'description': 'Documento que apresenta a empresa/instituição financeira',
    
    'required_content': [
        'Informações sobre a empresa',
        'História/trajetória',
        'Serviços oferecidos',
        'Estrutura organizacional',
        'Diferenciais competitivos'
    ],
    
    'indicators': [
        'sobre nós', 'nossa história', 'quem somos', 'missão', 'visão', 'valores',
        'serviços', 'produtos', 'soluções', 'experiência', 'equipe', 'clientes',
        'portfólio', 'atuação', 'apresentação', 'institucional', 'empresa'
    ],
    
    'wrong_document_indicators': {
        'termo de credenciamento': ['termo de análise', 'termo de credenciamento', 'anexo i'],
        'checklist': ['checklist', 'requisito', 'atribuição', 'situação'],
        'certidão': ['certidão', 'certifica', 'certificado'],
        'declaração': ['declara que', 'declaração', 'pelo presente instrumento'],
        'formulário': ['formulário', 'preencher', 'campo obrigatório'],
        'relatório financeiro': ['balanço', 'patrimônio líquido', 'demonstrativo', 'ativo', 'passivo']
    },
    
    'validation_rules': {
        'date_max_age_days': 365,  # Data não pode ser maior que 1 ano
        'min_content_chars': 500,   # Conteúdo mínimo
        'min_indicators': 3,        # Mínimo de indicadores encontrados
        'must_mention_institution': True
    },
    
    'ai_prompt': """Analise esta Apresentação Institucional com RIGOR PROFISSIONAL:

INSTITUIÇÃO ESPERADA: "{institution_name}"

VERIFICAÇÕES CRÍTICAS OBRIGATÓRIAS:
1. Este documento é REALMENTE uma apresentação institucional? 
   - Deve conter: visão geral da empresa, histórico, serviços, diferenciais, equipe
   - NÃO pode ser: termo, checklist, certidão, declaração, relatório financeiro

2. O documento menciona explicitamente a instituição "{institution_name}"?

3. Qualidade e completude do conteúdo para credenciamento RPPS

4. A data do documento (se houver) é de menos de 1 ano?

RETORNE EM JSON:
{{
    "is_valid": true/false,
    "score": 0-100,
    "document_type_correct": true/false,
    "institution_mentioned": true/false,
    "content_quality": "alta/média/baixa",
    "date_found": "DD/MM/YYYY" ou null,
    "date_valid": true/false/null,
    "issues": ["lista de problemas"],
    "warnings": ["lista de avisos"],
    "summary": "resumo da análise"
}}"""
}

# =============================================================================
# DOCUMENTO 2: CHECKLIST DE CREDENCIAMENTO (Excel)
# =============================================================================

CHECKLIST_CREDENCIAMENTO = {
    'name': 'Checklist de Credenciamento',
    'formats': ['.xlsm', '.xlsx', '.xls'],
    'description': 'Planilha com checklist de requisitos para credenciamento',
    
    'validation_rules': {
        'all_checks_must_be_green': True,   # Todos os checks devem ser verdes (✓)
        'no_red_x_allowed': True,           # Nenhum X vermelho permitido
        'all_fields_must_be_filled': True,  # Todos os campos devem estar preenchidos
        'observations_must_be_coherent': True,  # Observações devem ser coerentes
        'min_checked_items': 5              # Mínimo de itens marcados
    },
    
    'structure': {
        'header_contains': ['nome', 'cnpj', 'instituição', 'credenciamento'],
        'check_columns': [4, 5, 6],  # Colunas típicas com checkmarks
        'observation_keywords': ['observa', 'diferencial', 'competitivo', 'nota']
    },
    
    'ai_prompt': """Analise este Checklist de Credenciamento:

INSTITUIÇÃO: "{institution_name}"
CNPJ: "{institution_cnpj}"

VERIFICAÇÕES OBRIGATÓRIAS:
1. TODOS os itens estão marcados com check verde (✓)?
   - Qualquer X vermelho = REJEIÇÃO

2. TODOS os campos estão preenchidos corretamente?

3. As observações gerais/diferenciais competitivos:
   - Estão preenchidas?
   - São coerentes e relevantes?
   - Têm conteúdo substancial (não genérico)?

4. O nome e CNPJ da instituição estão corretos?

RETORNE EM JSON:
{{
    "is_valid": true/false,
    "score": 0-100,
    "all_checks_green": true/false,
    "red_x_count": 0,
    "empty_fields_count": 0,
    "observations_quality": "boa/razoável/ruim/vazia",
    "issues": ["lista de problemas"],
    "warnings": ["lista de avisos"]
}}"""
}

# =============================================================================
# DOCUMENTO 3: INFORMAÇÕES PREENCHIMENTO CADPREV (Excel)
# =============================================================================

CADPREV_PREENCHIMENTO = {
    'name': 'Informações Preenchimento CadPrev',
    'formats': ['.xlsm', '.xlsx', '.xls'],
    'description': 'Planilha com perguntas (azul) e respostas (amarelo) para CadPrev',
    
    'color_rules': {
        'questions_color': 'blue',    # Células azuis = perguntas
        'answers_color': 'yellow'     # Células amarelas = respostas que devem ser preenchidas
    },
    
    'validation_rules': {
        'all_yellow_cells_must_be_filled': True,  # Todas as células amarelas devem ter resposta
        'min_characters_per_answer': 5,           # Mínimo de caracteres por resposta
        'check_coherence': True                   # Verificar coerência das respostas
    },
    
    'ai_prompt': """Analise este documento de Preenchimento CadPrev:

ESTRUTURA DO DOCUMENTO:
- Células AZUIS = Perguntas/Campos
- Células AMARELAS = Respostas (devem estar preenchidas)

VERIFICAÇÕES OBRIGATÓRIAS:
1. TODAS as células amarelas estão preenchidas?
   - Campos vazios = problema

2. As respostas são coerentes e relevantes?
   - Respostas genéricas ou sem sentido = problema

3. A completude informacional é adequada?

4. Há informações sobre volume gerido, experiência, etc?

RETORNE EM JSON:
{{
    "is_valid": true/false,
    "score": 0-100,
    "yellow_cells_filled": true/false,
    "empty_answer_count": 0,
    "short_answers_count": 0,
    "coherence_level": "alta/média/baixa",
    "issues": ["lista de problemas"],
    "warnings": ["lista de avisos"]
}}"""
}

# =============================================================================
# DOCUMENTO 4: FORMULÁRIO TERMO DE CREDENCIAMENTO (Excel)
# =============================================================================

TERMO_CREDENCIAMENTO = {
    'name': 'Formulário Termo de Credenciamento',
    'formats': ['.xlsm', '.xlsx', '.xls'],
    'description': 'Formulário do termo de credenciamento com campos coloridos',
    
    'color_rules': {
        'institution_fields': 'orange',  # Laranja/Pêssego = Instituição DEVE preencher
        'rpps_fields': 'white'           # Branco = RPPS preenche (não verificar)
    },
    
    'rpps_fields_to_ignore': [
        'local e data',
        'responsável pelo credenciamento',
        'número do processo',
        'número do termo',
        'ente federativo',
        'termo de análise',
        'parecer do comitê',
        'assinatura do rpps'
    ],
    
    'validation_rules': {
        'all_orange_cells_must_be_filled': True,   # Campos laranja obrigatórios
        'white_cells_report_only': True,           # Campos brancos: apenas reportar se vazios
        'check_content_depth': True                # Verificar se respostas são superficiais
    },
    
    'ai_prompt': """Analise este Formulário de Termo de Credenciamento:

ESTRUTURA DO DOCUMENTO:
- Células LARANJA/PÊSSEGO = Campos que a INSTITUIÇÃO deve preencher (OBRIGATÓRIOS)
- Células BRANCAS = Campos para o RPPS preencher (apenas reportar se vazios)

CAMPOS DO RPPS (NÃO exigir preenchimento):
- Local e data
- Responsável pelo credenciamento
- Número do processo/termo
- Ente federativo
- Termo de análise

VERIFICAÇÕES OBRIGATÓRIAS:
1. TODOS os campos laranja estão preenchidos pela instituição?
   - Campos laranja vazios = REJEIÇÃO

2. As respostas têm profundidade adequada?
   - Respostas muito curtas ou superficiais = aviso

3. Campos brancos vazios: apenas informar que o RPPS deverá preencher

RETORNE EM JSON:
{{
    "is_valid": true/false,
    "score": 0-100,
    "orange_fields_filled": true/false,
    "empty_orange_count": 0,
    "empty_white_count": 0,
    "content_depth": "adequada/superficial/insuficiente",
    "issues": ["lista de problemas"],
    "warnings": ["lista de avisos"],
    "rpps_pending_fields": ["campos que o RPPS deve preencher"]
}}"""
}

# =============================================================================
# DOCUMENTO 5: DECLARAÇÃO UNIFICADA (PDF)
# =============================================================================

DECLARACAO_UNIFICADA = {
    'name': 'Declaração Unificada',
    'formats': ['.pdf'],
    'description': 'Declaração unificada com múltiplas declarações da instituição',
    
    'CRITICAL_RULE': 'ASSINATURA DIGITAL VÁLIDA É OBRIGATÓRIA - INVALIDA CREDENCIAMENTO SE NÃO TIVER',
    
    'required_text': ['declaração unificada', 'declaracao unificada'],
    
    'validation_rules': {
        'must_contain_declaration_text': True,
        'date_max_age_days': 365,
        'signature_required': True,           # OBRIGATÓRIO
        'signature_must_be_valid': True       # CRÍTICO - invalida credenciamento
    },
    
    'signature_validation': {
        'validate_at_tcees': True,
        'invalid_signature_action': 'INVALIDATE_CREDENTIALING',  # AÇÃO CRÍTICA
        'report_in_feedback': True
    },
    
    'ai_prompt': """Analise esta Declaração Unificada:

VERIFICAÇÕES OBRIGATÓRIAS:
1. O documento contém o texto "DECLARAÇÃO UNIFICADA"?
   - Se não contiver = não é o documento correto

2. A data do documento é de menos de 1 ano?
   - Data antiga = REJEIÇÃO

3. ASSINATURA DIGITAL:
   - CRÍTICO: Este documento REQUER assinatura digital VÁLIDA
   - Assinatura inválida = INVALIDA TODO O CREDENCIAMENTO
   - A validação de assinatura é feita separadamente no TCEES

RETORNE EM JSON:
{{
    "is_valid": true/false,
    "score": 0-100,
    "contains_declaration_text": true/false,
    "date_found": "DD/MM/YYYY" ou null,
    "date_valid": true/false,
    "signature_note": "Assinatura será validada no TCEES",
    "issues": ["lista de problemas"],
    "warnings": ["lista de avisos"]
}}"""
}

# =============================================================================
# DOCUMENTO 6: RELATÓRIO AGÊNCIA DE RISCO / RATING (PDF)
# =============================================================================

RELATORIO_RATING = {
    'name': 'Relatório Agência de Risco (Rating)',
    'formats': ['.pdf'],
    'description': 'Relatório de classificação de risco emitido por agência autorizada',
    
    'rating_indicators': [
        'rating', 'classificação', 'risco', 'avaliação de crédito', 'score',
        'nota', 'agência', 'análise de risco', 'credit rating', 'grau de investimento'
    ],
    
    'known_agencies': [
        'Moody\'s', 'Standard & Poor\'s', 'S&P', 'Fitch', 'Austin Rating',
        'SR Rating', 'Liberum', 'RiskBank', 'LF Rating'
    ],
    
    'rating_patterns': [
        r'AAA|AA\+|AA|AA-|A\+|A|A-',
        r'BBB\+|BBB|BBB-|BB\+|BB|BB-',
        r'B\+|B|B-|CCC|CC|C|D',
        r'brAAA|brAA|brA|brBBB|brBB|brB',  # Ratings brasileiros
        r'[Nn]ota[:\s]+\d+',
        r'[Ss]core[:\s]+\d+',
        r'[Cc]lassifica[çc][aã]o[:\s]+\w+'
    ],
    
    'validation_rules': {
        'must_have_rating_terms': True,
        'must_have_score_or_classification': True,
        'should_mention_institution': True,
        'should_identify_agency': True,
        'min_rating_terms': 2
    },
    
    'ai_prompt': """Analise este Relatório de Agência de Risco (Rating):

INSTITUIÇÃO AVALIADA: "{institution_name}"

VERIFICAÇÕES OBRIGATÓRIAS:
1. O documento é realmente um relatório de rating/risco?
   - Deve conter termos como: rating, classificação, risco, score, nota

2. Qual a CLASSIFICAÇÃO/NOTA/SCORE atribuída?
   - Ex: AAA, AA+, brAA, Nota 8, Score 85, etc.

3. Qual a AGÊNCIA que emitiu o relatório?
   - Agências conhecidas: Moody's, S&P, Fitch, Austin Rating, SR Rating, etc.

4. O relatório é sobre a instituição correta?

RETORNE EM JSON:
{{
    "is_valid": true/false,
    "score": 0-100,
    "is_rating_report": true/false,
    "rating_found": "AAA" ou null,
    "agency_name": "nome da agência" ou null,
    "institution_mentioned": true/false,
    "issues": ["lista de problemas"],
    "warnings": ["lista de avisos"]
}}"""
}

# =============================================================================
# DOCUMENTO 7: CERTIDÕES (CVM, BACEN, etc.)
# =============================================================================

CERTIDOES = {
    'name': 'Certidões',
    'formats': ['.pdf'],
    'description': 'Certidões de órgãos reguladores e documentos comprobatórios',
    
    'types': {
        'formulario_referencia_cvm': {
            'name': 'Formulário de Referência CVM',
            'keywords': ['cvm', 'comissão de valores mobiliários', 'formulário de referência', 
                        'administrador de carteiras', 'registro'],
            'description': 'Formulário de registro na CVM'
        },
        'autorizacao_bacen': {
            'name': 'Certidão Autorização Funcionar BACEN',
            'keywords': ['bacen', 'banco central', 'autorização', 'funcionar', 
                        'instituição financeira', 'bcb'],
            'description': 'Autorização do Banco Central para funcionamento'
        },
        'bacen_socio_representante': {
            'name': 'Certidão BACEN Sócio/Representante',
            'keywords': ['bacen', 'banco central', 'sócio', 'representante', 
                        'administrador', 'responsável'],
            'description': 'Certidão do BACEN sobre sócios ou representantes'
        },
        'anbima': {
            'name': 'Certidão ANBIMA',
            'keywords': ['anbima', 'associação brasileira', 'mercado de capitais', 
                        'código de auto-regulação'],
            'description': 'Certidão de associação à ANBIMA'
        },
        'lista_exaustiva': {
            'name': 'Lista Exaustiva Resolução CMN',
            'keywords': ['lista exaustiva', 'resolução cmn', 'art. 15', 'artigo 15',
                        'ativos financeiros'],
            'description': 'Lista exaustiva conforme Resolução CMN'
        }
    },
    
    'validation_rules': {
        'must_match_expected_type': True,
        'keywords_min_match': 2,
        'must_look_like_certificate': True
    },
    
    'certificate_indicators': ['certidão', 'certificado', 'certifica', 'atesta', 
                               'declara', 'comprova', 'autorização'],
    
    'ai_prompt': """Analise esta Certidão:

TIPO ESPERADO: "{expected_type}"

VERIFICAÇÕES OBRIGATÓRIAS:
1. O documento é do tipo esperado?
   - Verificar se as palavras-chave do tipo aparecem no documento

2. O documento tem formato de certidão oficial?
   - Deve conter termos como: certidão, certificado, certifica, atesta

3. O conteúdo é coerente com o tipo de certidão esperado?

RETORNE EM JSON:
{{
    "is_valid": true/false,
    "score": 0-100,
    "matches_expected_type": true/false,
    "keywords_found": ["lista de palavras encontradas"],
    "looks_like_certificate": true/false,
    "issues": ["lista de problemas"],
    "warnings": ["lista de avisos"]
}}"""
}

# =============================================================================
# REGRAS GLOBAIS DE ASSINATURA DIGITAL
# =============================================================================

SIGNATURE_RULES = {
    'general_rule': 'Se documento tem assinatura, validar no TCEES e reportar no feedback',
    
    'critical_documents': {
        'declaracao_unificada': {
            'signature_required': True,
            'invalid_signature_action': 'INVALIDATE_CREDENTIALING',
            'message': 'Assinatura digital inválida INVALIDA o credenciamento'
        },
        'termo_declaracao': {
            'signature_required': True,
            'invalid_signature_action': 'INVALIDATE_CREDENTIALING',
            'message': 'Assinatura digital inválida INVALIDA o credenciamento'
        }
    },
    
    'non_critical_documents': {
        'action': 'REPORT_IN_FEEDBACK',
        'message': 'Assinatura inválida deve ser reportada, mas não invalida credenciamento'
    },
    
    'validation_service': {
        'name': 'TCEES',
        'url': 'https://conformidadepdf.tcees.tc.br/',
        'description': 'Tribunal de Contas do Estado do Espírito Santo'
    }
}

# =============================================================================
# MAPEAMENTO DE TIPOS PARA ANÁLISE
# =============================================================================

DOCUMENT_TYPES_MAP = {
    # Apresentação Institucional
    'apresentacao_institucional': APRESENTACAO_INSTITUCIONAL,
    'apresentação institucional': APRESENTACAO_INSTITUCIONAL,
    'apresentacao institucional': APRESENTACAO_INSTITUCIONAL,
    
    # Checklist
    'checklist_credenciamento': CHECKLIST_CREDENCIAMENTO,
    'checklist de credenciamento': CHECKLIST_CREDENCIAMENTO,
    'checklist': CHECKLIST_CREDENCIAMENTO,
    
    # CadPrev
    'cadprev': CADPREV_PREENCHIMENTO,
    'informacoes_cadprev': CADPREV_PREENCHIMENTO,
    'informações cadprev': CADPREV_PREENCHIMENTO,
    'preenchimento cadprev': CADPREV_PREENCHIMENTO,
    
    # Termo de Credenciamento
    'termo_credenciamento': TERMO_CREDENCIAMENTO,
    'formulário termo de credenciamento': TERMO_CREDENCIAMENTO,
    'termo de credenciamento': TERMO_CREDENCIAMENTO,
    
    # Declaração Unificada
    'declaracao_unificada': DECLARACAO_UNIFICADA,
    'declaração unificada': DECLARACAO_UNIFICADA,
    'declaracao unificada': DECLARACAO_UNIFICADA,
    
    # Relatório de Rating
    'relatorio_rating': RELATORIO_RATING,
    'relatório de rating': RELATORIO_RATING,
    'rating': RELATORIO_RATING,
    'agencia de risco': RELATORIO_RATING,
    'relatório agência de risco': RELATORIO_RATING,
    
    # Certidões
    'certidao': CERTIDOES,
    'certidão': CERTIDOES,
    'cvm': CERTIDOES,
    'bacen': CERTIDOES,
    'anbima': CERTIDOES,
}

# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def get_document_knowledge(document_type):
    """
    Retorna a base de conhecimento para um tipo de documento
    """
    doc_type_lower = document_type.lower().strip()
    
    # Busca direta
    if doc_type_lower in DOCUMENT_TYPES_MAP:
        return DOCUMENT_TYPES_MAP[doc_type_lower]
    
    # Busca por palavras-chave
    for key, value in DOCUMENT_TYPES_MAP.items():
        if key in doc_type_lower or doc_type_lower in key:
            return value
    
    return None


def is_signature_critical(document_type):
    """
    Verifica se a assinatura é crítica para este tipo de documento
    """
    doc_lower = document_type.lower()
    
    for critical_doc in SIGNATURE_RULES['critical_documents']:
        if critical_doc in doc_lower:
            return True
    
    return False


def get_signature_action(document_type, signature_valid):
    """
    Retorna a ação a ser tomada baseada na validação de assinatura
    """
    doc_lower = document_type.lower()
    
    if not signature_valid:
        for critical_doc, rules in SIGNATURE_RULES['critical_documents'].items():
            if critical_doc in doc_lower:
                return {
                    'action': rules['invalid_signature_action'],
                    'message': rules['message'],
                    'critical': True
                }
        
        return {
            'action': SIGNATURE_RULES['non_critical_documents']['action'],
            'message': SIGNATURE_RULES['non_critical_documents']['message'],
            'critical': False
        }
    
    return {
        'action': 'SIGNATURE_VALID',
        'message': 'Assinatura digital válida',
        'critical': False
    }


def get_ai_prompt_for_document(document_type, **kwargs):
    """
    Retorna o prompt de IA configurado para o tipo de documento
    """
    knowledge = get_document_knowledge(document_type)
    
    if not knowledge:
        return None
    
    prompt = knowledge.get('ai_prompt', '')
    
    # Substituir variáveis no prompt
    for key, value in kwargs.items():
        placeholder = '{' + key + '}'
        prompt = prompt.replace(placeholder, str(value) if value else '')
    
    return prompt


def get_validation_rules(document_type):
    """
    Retorna as regras de validação para o tipo de documento
    """
    knowledge = get_document_knowledge(document_type)
    
    if not knowledge:
        return {}
    
    return knowledge.get('validation_rules', {})


def check_excel_cell_color(cell_color_rgb, color_type):
    """
    Verifica se a cor de uma célula corresponde ao tipo esperado
    
    Args:
        cell_color_rgb: Cor RGB da célula
        color_type: Tipo de cor a verificar ('green_check', 'red_x', 'cadprev_answer_yellow', etc.)
    
    Returns:
        bool: True se a cor corresponder
    """
    if not cell_color_rgb or color_type not in EXCEL_COLORS:
        return False
    
    color_str = str(cell_color_rgb).upper()
    
    for valid_color in EXCEL_COLORS[color_type]:
        if valid_color.upper() in color_str:
            return True
    
    return False


def is_check_symbol(value):
    """Verifica se o valor é um símbolo de check/aprovação"""
    return value in CHECK_SYMBOLS


def is_x_symbol(value):
    """Verifica se o valor é um símbolo de X/reprovação"""
    return value in X_SYMBOLS and value not in CHECK_SYMBOLS


# =============================================================================
# EXPORTAÇÃO DO MÓDULO
# =============================================================================

__all__ = [
    'APRESENTACAO_INSTITUCIONAL',
    'CHECKLIST_CREDENCIAMENTO',
    'CADPREV_PREENCHIMENTO',
    'TERMO_CREDENCIAMENTO',
    'DECLARACAO_UNIFICADA',
    'RELATORIO_RATING',
    'CERTIDOES',
    'SIGNATURE_RULES',
    'DOCUMENT_TYPES_MAP',
    'EXCEL_COLORS',
    'CHECK_SYMBOLS',
    'X_SYMBOLS',
    'get_document_knowledge',
    'is_signature_critical',
    'get_signature_action',
    'get_ai_prompt_for_document',
    'get_validation_rules',
    'check_excel_cell_color',
    'is_check_symbol',
    'is_x_symbol'
]
