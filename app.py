from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import os
import sqlite3
import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import PyPDF2
import io
import base64
import threading
import zipfile
import tempfile

# Carregar variáveis de ambiente do arquivo .env se existir
if os.path.exists('.env'):
    with open('.env', 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

# Importar módulo de análise RIGOROSA com IA
from ai_analyzer_rigorous import analyze_document_rigorous

# Importar validador TCEES
from tcees_validator import validate_pdf_with_tcees, validate_multiple_pdfs

# Importar assinador digital
from digital_signer import digital_signer, PYHANKO_AVAILABLE

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_super_segura_aqui_12345'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Criar pasta de uploads se não existir
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Função para gerar ID customizado
def generate_custom_id(institution_name, credentialing_type):
    """
    Gera ID no formato: IT00001G
    - 2 primeiras letras da instituição (ex: Itaú = IT)
    - 5 dígitos sequenciais (00001, 00002, etc)
    - 1 letra do tipo (G=Gestor, D=Distribuidor, A=Administrador)
    """
    # Extrair 2 primeiras letras da instituição
    institution_code = ''.join(c.upper() for c in institution_name if c.isalpha())[:2]
    if len(institution_code) < 2:
        institution_code = institution_code.ljust(2, 'X')
    
    # Mapear tipo para letra
    type_map = {
        'savings_management': 'G',  # Gestor
        'investments': 'D',          # Distribuidor
        'custody': 'A'               # Administrador
    }
    type_letter = type_map.get(credentialing_type, 'X')
    
    # Buscar último número sequencial para esta instituição
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    c.execute('''SELECT custom_id FROM processes 
                 WHERE custom_id LIKE ? 
                 ORDER BY custom_id DESC LIMIT 1''', (f'{institution_code}%',))
    last_id = c.fetchone()
    conn.close()
    
    if last_id and last_id[0]:
        # Extrair número do último ID
        try:
            last_number = int(last_id[0][2:7])  # Posições 2-7 contêm o número
            next_number = last_number + 1
        except:
            next_number = 1
    else:
        next_number = 1
    
    # Formatar ID: IT00001G
    custom_id = f"{institution_code}{next_number:05d}{type_letter}"
    return custom_id

# Inicializar banco de dados
def init_db():
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Tabela de usuários
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  name TEXT NOT NULL,
                  cpf_cnpj TEXT NOT NULL,
                  role TEXT NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Tabela de processos de credenciamento
    c.execute('''CREATE TABLE IF NOT EXISTS processes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  custom_id TEXT UNIQUE,
                  financial_institution_id INTEGER NOT NULL,
                  financial_institution_name TEXT NOT NULL,
                  financial_institution_cnpj TEXT,
                  rpps_id INTEGER NOT NULL,
                  rpps_name TEXT NOT NULL,
                  credentialing_type TEXT NOT NULL,
                  status TEXT DEFAULT 'draft',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  submitted_at TIMESTAMP,
                  reviewed_at TIMESTAMP,
                  final_review_note TEXT,
                  final_decision TEXT,
                  final_decision_at TIMESTAMP,
                  final_decision_by INTEGER,
                  is_archived INTEGER DEFAULT 0,
                  FOREIGN KEY (financial_institution_id) REFERENCES users(id),
                  FOREIGN KEY (rpps_id) REFERENCES users(id))''')
    
    # Tabela de documentos
    c.execute('''CREATE TABLE IF NOT EXISTS documents
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  process_id INTEGER NOT NULL,
                  type TEXT NOT NULL,
                  name TEXT NOT NULL,
                  filename TEXT NOT NULL,
                  mime_type TEXT NOT NULL,
                  uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  uploaded_by INTEGER NOT NULL,
                  status TEXT DEFAULT 'pending',
                  analysis_data TEXT,
                  workflow_status TEXT DEFAULT 'initial',
                  workflow_version INTEGER DEFAULT 1,
                  FOREIGN KEY (process_id) REFERENCES processes(id),
                  FOREIGN KEY (uploaded_by) REFERENCES users(id))''')
    
    # Tabela de comunicações
    c.execute('''CREATE TABLE IF NOT EXISTS communications
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  process_id INTEGER NOT NULL,
                  sender_id INTEGER,
                  sender_role TEXT NOT NULL,
                  message TEXT NOT NULL,
                  message_type TEXT DEFAULT 'comment',
                  is_internal INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (process_id) REFERENCES processes(id),
                  FOREIGN KEY (sender_id) REFERENCES users(id))''')
    
    # Adicionar coluna is_fulfilled se não existir (para rastrear documentos solicitados atendidos)
    try:
        c.execute('ALTER TABLE communications ADD COLUMN is_fulfilled INTEGER DEFAULT 0')
    except:
        pass  # Coluna já existe
    
    # Tabela de histórico do processo
    c.execute('''CREATE TABLE IF NOT EXISTS process_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  process_id INTEGER NOT NULL,
                  user_id INTEGER,
                  user_name TEXT,
                  user_role TEXT,
                  action TEXT NOT NULL,
                  details TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (process_id) REFERENCES processes(id),
                  FOREIGN KEY (user_id) REFERENCES users(id))''')
    
    # Tabela de controle de uso de IA (proteção financeira)
    c.execute('''CREATE TABLE IF NOT EXISTS ai_usage_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  process_id INTEGER NOT NULL,
                  user_id INTEGER NOT NULL,
                  documents_analyzed INTEGER DEFAULT 0,
                  tokens_estimated INTEGER DEFAULT 0,
                  analysis_date DATE DEFAULT CURRENT_DATE,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (process_id) REFERENCES processes(id),
                  FOREIGN KEY (user_id) REFERENCES users(id))''')
    
    # Tabela de Documentos Especiais (Termo de Credenciamento - fluxo de assinaturas)
    c.execute('''CREATE TABLE IF NOT EXISTS special_documents
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  process_id INTEGER NOT NULL,
                  document_type TEXT NOT NULL,
                  version INTEGER DEFAULT 1,
                  status TEXT NOT NULL,
                  filename TEXT NOT NULL,
                  original_filename TEXT,
                  mime_type TEXT,
                  uploaded_by INTEGER,
                  uploaded_by_role TEXT,
                  notes TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (process_id) REFERENCES processes(id),
                  FOREIGN KEY (uploaded_by) REFERENCES users(id))''')
    
    # Status possíveis para special_documents:
    # - excel_if: Excel original enviado pela IF
    # - pdf_rpps_signed: PDF alterado e assinado pelo RPPS
    # - awaiting_if_signature: Aguardando assinatura da IF
    # - signed_by_if: Assinado pela IF e retornado
    # - official_final: Documento oficial final no dossiê
    
    # Inserir usuários de teste se não existirem
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        test_users = [
            ('rpps@teste.com', generate_password_hash('rpps123'), 'RPPS Teste', '12345678000190', 'rpps'),
            ('financeira@teste.com', generate_password_hash('financeira123'), 'Instituição Financeira Teste', '98765432000180', 'financial_institution'),
            ('suporte.aicsj@gmail.com', generate_password_hash('Fieleaquelequeprometeu'), 'Administrador do Sistema', '00000000000', 'admin')
        ]
        c.executemany('INSERT INTO users (email, password, name, cpf_cnpj, role) VALUES (?, ?, ?, ?, ?)', test_users)
    
    conn.commit()
    conn.close()

init_db()

# Decorador para rotas protegidas
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_role' not in session or session['user_role'] != role:
                return jsonify({'error': 'Acesso negado'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Função helper para registrar histórico do processo
def log_process_history(process_id, action, details=None, user_id=None, user_name=None, user_role=None):
    """Registra uma ação no histórico do processo"""
    try:
        conn = sqlite3.connect('credenciamento.db')
        c = conn.cursor()
        
        # Se não passou user info, pegar da sessão
        if user_id is None:
            user_id = session.get('user_id')
        if user_name is None:
            user_name = session.get('user_name', 'Sistema')
        if user_role is None:
            user_role = session.get('role', 'system')
        
        c.execute('''INSERT INTO process_history (process_id, user_id, user_name, user_role, action, details, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, datetime('now'))''',
                  (process_id, user_id, user_name, user_role, action, details))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erro ao registrar histórico: {e}")

# Função para validar assinatura no TCEES
def validate_signature_tcees(document_path):
    """
    Valida assinatura digital consultando o site do TCE-ES
    https://www.tcees.tc.br/validacao-assinatura
    Retorna checks detalhados de conformidade
    """
    try:
        # Ler o arquivo PDF
        with open(document_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            
            # Informações básicas do arquivo
            file_size = os.path.getsize(document_path)
            page_count = len(pdf_reader.pages)
            file_extension = os.path.splitext(document_path)[1].lower()
            has_password = pdf_reader.is_encrypted
            
            # Verificar se é PDF
            extensao_check = file_extension == '.pdf'
            
            # Verificar se tem senha
            sem_senha_check = not has_password
            
            # Verificar tamanho do arquivo (máximo 10MB como no TCE-ES)
            tamanho_arquivo_check = file_size <= (10 * 1024 * 1024)
            
            # Verificar tamanho das páginas e se é pesquisável
            is_searchable = False
            tamanho_pagina_check = True
            
            try:
                for page in pdf_reader.pages:
                    # Verificar se tem texto extraível (com proteção contra erros de imagem)
                    try:
                        text = page.extract_text()
                        if text and len(text.strip()) > 0:
                            is_searchable = True
                    except Exception as e:
                        # Ignorar erros de decodificação de imagens
                        if 'XFormObject' not in str(e):
                            print(f"⚠️ Aviso ao extrair texto da página: {str(e)[:80]}")
                    
                    # Verificar dimensões da página (A4 padrão: 210x297mm ou 595x842 pontos)
                    try:
                        if hasattr(page, 'mediabox'):
                            width = float(page.mediabox.width)
                            height = float(page.mediabox.height)
                            # Aceitar páginas entre A5 e A3
                            if width < 420 or width > 1191 or height < 595 or height > 1684:
                                tamanho_pagina_check = False
                    except:
                        pass
            except:
                is_searchable = False
            
            pesquisavel_check = is_searchable
            
            # 🔐 VALIDAÇÃO REAL COM TCEES
            # Usar o site oficial conformidadepdf.tcees.tc.br para validar
            print("\n🔐 Iniciando validação TCEES...")
            
            tcees_results = validate_pdf_with_tcees(document_path)
            
            # Usar os resultados do TCEES
            extensao_check = tcees_results.get('extensao_valida', extensao_check)
            sem_senha_check = tcees_results.get('sem_senha', sem_senha_check)
            tamanho_arquivo_check = tcees_results.get('tamanho_arquivo_ok', tamanho_arquivo_check)
            tamanho_pagina_check = tcees_results.get('tamanho_pagina_ok', tamanho_pagina_check)
            assinado_check = tcees_results.get('assinado', False)
            autenticidade_check = tcees_results.get('autenticidade', False)
            integridade_check = tcees_results.get('integridade', False)
            pesquisavel_check = tcees_results.get('pesquisavel', pesquisavel_check)
            
            validation_details = f"Validação TCEES: {tcees_results.get('resultado_final', 'ERRO')}"
            if tcees_results.get('observacoes'):
                validation_details += f" | Obs: {'; '.join(tcees_results['observacoes'][:2])}"
            
            has_signature = assinado_check
            signature_count = 1 if has_signature else 0
            
            print(f"✅ Validação TCEES concluída: {tcees_results.get('resultado_final', 'ERRO')}")
            
            # Calcular resultado final
            all_checks_passed = (
                extensao_check and 
                sem_senha_check and 
                tamanho_arquivo_check and 
                tamanho_pagina_check and 
                assinado_check and 
                autenticidade_check and 
                integridade_check and
                pesquisavel_check
            )
            
            resultado_final = 'approved' if all_checks_passed else 'rejected'
            
            # Montar mensagem de detalhes
            details_parts = []
            if not extensao_check:
                details_parts.append("❌ Extensão inválida (apenas PDF)")
            if not sem_senha_check:
                details_parts.append("❌ Documento protegido por senha")
            if not tamanho_arquivo_check:
                details_parts.append(f"❌ Arquivo muito grande ({file_size / 1024 / 1024:.1f}MB > 10MB)")
            if not tamanho_pagina_check:
                details_parts.append("❌ Tamanho de página fora do padrão")
            if not pesquisavel_check:
                details_parts.append("❌ Documento não é pesquisável")
            if not assinado_check:
                details_parts.append("❌ Documento não possui assinatura digital")
            if not autenticidade_check:
                details_parts.append("❌ Falha na verificação de autenticidade")
            if not integridade_check:
                details_parts.append("❌ Falha na verificação de integridade")
            
            if all_checks_passed:
                details_parts.append("✅ Documento aprovado em todas as verificações")
            
            details = " | ".join(details_parts) if details_parts else "Documento analisado"
            if validation_details:
                details += f" | {validation_details}"
            
            if signature_count > 0:
                details += f" | {signature_count} assinatura(s) detectada(s)"
            
            return {
                # Checks do TCE-ES (conforme imagem)
                'extensao_valida': extensao_check,
                'sem_senha': sem_senha_check,
                'tamanho_arquivo_ok': tamanho_arquivo_check,
                'tamanho_pagina_ok': tamanho_pagina_check,
                'assinado': assinado_check,
                'autenticidade': autenticidade_check,
                'integridade': integridade_check,
                'pesquisavel': pesquisavel_check,
                'resultado_final_conformidade': resultado_final,
                
                # Informações adicionais
                'numero_assinaturas': signature_count,
                'extension': file_extension,
                'file_size': f"{file_size / 1024:.2f} KB",
                'file_size_mb': f"{file_size / 1024 / 1024:.2f} MB",
                'page_count': page_count,
                'has_password': has_password,
                'details': details,
                
                # Compatibilidade com código anterior
                'is_valid': all_checks_passed,
                'has_identifiable_signature': has_signature,
                'is_intact': integridade_check,
                'is_searchable': pesquisavel_check,
                'is_signed': assinado_check,
                'has_authenticity': autenticidade_check,
                'has_integrity': integridade_check,
                'final_result': resultado_final
            }
    
    except Exception as e:
        print(f"Erro ao validar assinatura: {e}")
        return {
            'extensao_valida': False,
            'sem_senha': False,
            'tamanho_arquivo_ok': False,
            'tamanho_pagina_ok': False,
            'assinado': False,
            'autenticidade': False,
            'integridade': False,
            'pesquisavel': False,
            'resultado_final_conformidade': 'rejected',
            'numero_assinaturas': 0,
            'details': f"Erro ao processar documento: {str(e)}",
            'is_valid': False,
            'has_identifiable_signature': False,
            'is_intact': False,
            'is_searchable': False,
            'final_result': 'rejected'
        }

# Função para análise de conteúdo do documento
def analyze_document_content(document_type, document_name, file_path):
    """
    Analisa o conteúdo do documento
    """
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            
            # Extrair texto do PDF
            text_content = ""
            for page in pdf_reader.pages:
                text_content += page.extract_text()
            
            # Análise básica baseada no tipo de documento
            issues = []
            recommendations = []
            completeness = 80
            coherence = 85
            
            if not text_content.strip():
                issues.append("Documento parece estar vazio ou não possui texto extraível")
                completeness = 20
            
            if len(text_content) < 100:
                issues.append("Documento possui conteúdo muito reduzido")
                completeness = 40
            
            # Verificações específicas por tipo de documento
            if document_type == "termo_declaracao" and "declaração" not in text_content.lower():
                issues.append("Documento não parece ser uma declaração")
                coherence = 50
            
            if document_type == "certidao_cvm" and "cvm" not in text_content.lower():
                issues.append("Documento não parece ser uma certidão da CVM")
                coherence = 50
            
            if not issues:
                recommendations.append("Documento aparenta estar em conformidade")
            else:
                recommendations.append("Revisar os pontos destacados e corrigir se necessário")
            
            summary = f"Documento '{document_name}' analisado. "
            if issues:
                summary += f"Foram encontrados {len(issues)} problema(s). "
            else:
                summary += "Documento aprovado na análise preliminar."
            
            return {
                'is_valid': len(issues) == 0,
                'completeness': completeness,
                'coherence': coherence,
                'issues': issues,
                'recommendations': recommendations,
                'summary': summary
            }
    
    except Exception as e:
        return {
            'is_valid': False,
            'completeness': 0,
            'coherence': 0,
            'issues': [f"Erro ao analisar documento: {str(e)}"],
            'recommendations': ["Verifique se o arquivo está corrompido"],
            'summary': "Falha na análise do documento"
        }

# Rotas de autenticação
@app.route('/')
def index():
    if 'user_id' in session:
        if session['user_role'] == 'rpps':
            return redirect(url_for('rpps_home'))
        else:
            return redirect(url_for('financial_home'))
    return redirect(url_for('login'))

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static', 'images'),
                               'só o simbolo.png', mimetype='image/png')

@app.route('/api/process/<int:process_id>/documents')
@login_required
def get_process_documents(process_id):
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    c.execute('''SELECT id, process_id, type, name, filename, mime_type, uploaded_at, 
                        status, workflow_status, workflow_version 
                 FROM documents WHERE process_id = ? ORDER BY uploaded_at DESC''', (process_id,))
    docs = c.fetchall()
    conn.close()
    
    documents = []
    for doc in docs:
        documents.append({
            'id': doc[0],
            'process_id': doc[1],
            'document_type': doc[2],
            'name': doc[3],
            'filename': doc[4],
            'mime_type': doc[5],
            'uploaded_at': doc[6],
            'status': doc[7] if len(doc) > 7 else 'pending',
            'workflow_status': doc[8] if len(doc) > 8 else 'initial',
            'workflow_version': doc[9] if len(doc) > 9 else 1
        })
    
    return jsonify(documents)

@app.route('/api/process/<int:process_id>/download-zip')
@login_required
def download_documents_zip(process_id):
    """Baixar todos os documentos de um processo em um arquivo ZIP"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Verificar permissão do usuário
    user_id = session.get('user_id')
    user_role = session.get('role')
    
    if user_role == 'financial_institution':
        c.execute('SELECT id, financial_institution_name FROM processes WHERE id = ? AND financial_institution_id = ?', 
                  (process_id, user_id))
    elif user_role == 'rpps':
        c.execute('SELECT id, financial_institution_name FROM processes WHERE id = ? AND rpps_id = ?', 
                  (process_id, user_id))
    else:  # admin
        c.execute('SELECT id, financial_institution_name FROM processes WHERE id = ?', (process_id,))
    
    process = c.fetchone()
    if not process:
        conn.close()
        return jsonify({'error': 'Processo não encontrado ou sem permissão'}), 403
    
    institution_name = process[1] if process[1] else f'processo_{process_id}'
    
    # Buscar documentos
    c.execute('SELECT id, name, filename FROM documents WHERE process_id = ?', (process_id,))
    docs = c.fetchall()
    conn.close()
    
    if not docs:
        return jsonify({'error': 'Nenhum documento encontrado'}), 404
    
    # Criar arquivo ZIP temporário
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    
    try:
        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zf:
            for doc in docs:
                doc_id, doc_name, filename = doc
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                if os.path.exists(file_path):
                    # Usar nome do documento para arquivo no ZIP (evitar duplicatas)
                    ext = os.path.splitext(filename)[1]
                    zip_filename = f"{doc_name}{ext}" if doc_name else filename
                    # Evitar nomes duplicados
                    counter = 1
                    original_zip_filename = zip_filename
                    while zip_filename in zf.namelist():
                        base, ext = os.path.splitext(original_zip_filename)
                        zip_filename = f"{base}_{counter}{ext}"
                        counter += 1
                    zf.write(file_path, zip_filename)
        
        # Limpar nome da instituição para uso como nome de arquivo
        safe_name = "".join(c for c in institution_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name[:50]  # Limitar tamanho
        zip_filename = f"{safe_name}_documentos.zip"
        
        return send_file(
            temp_zip.name,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
    except Exception as e:
        print(f"Erro ao criar ZIP: {e}")
        return jsonify({'error': 'Erro ao criar arquivo ZIP'}), 500

@app.route('/api/process/<int:process_id>/communications')
@login_required
def get_process_communications(process_id):
    from datetime import datetime, timedelta
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    # Filtrar apenas mensagens de comunicação real (excluir análises automáticas)
    c.execute('''SELECT c.id, c.message, c.sender_role, c.message_type, u.name as sender_name, c.created_at
                 FROM communications c
                 LEFT JOIN users u ON c.sender_id = u.id
                 WHERE c.process_id = ? 
                 AND (c.message_type = 'comment' OR c.message_type = 'message')
                 AND c.message NOT LIKE '%**Análise%'
                 AND c.message NOT LIKE '%Análise com IA%'
                 AND c.message NOT LIKE '%**Score:**%'
                 ORDER BY c.id ASC''', (process_id,))
    comms = c.fetchall()
    conn.close()
    
    communications = []
    for comm in comms:
        # Ajustar para horário de Brasília (UTC-3)
        created_at = comm[5]
        if created_at:
            try:
                dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                dt_brasilia = dt - timedelta(hours=3)
                created_at_formatted = dt_brasilia.strftime('%Y-%m-%d %H:%M:%S')
            except:
                created_at_formatted = created_at
        else:
            created_at_formatted = '2026-01-23 12:00:00'
            
        communications.append({
            'id': comm[0],
            'message': comm[1],
            'sender_role': comm[2] if comm[2] else 'system',
            'message_type': comm[3] if comm[3] else 'comment',
            'sender_name': comm[4] if comm[4] else 'Sistema',
            'created_at': created_at_formatted,
            'sent_at': created_at_formatted
        })
    
    return jsonify(communications)

@app.route('/api/process/<int:process_id>/communications', methods=['POST'])
@login_required
def send_communication(process_id):
    data = request.json
    message = data.get('message')
    message_type = data.get('message_type', 'comment')
    
    if not message:
        return jsonify({'success': False, 'error': 'Mensagem vazia'}), 400
    
    # Obter role da sessão ou determinar baseado no user_id
    sender_role = session.get('role')
    if not sender_role:
        # Buscar role do usuário no banco
        conn_temp = sqlite3.connect('credenciamento.db')
        c_temp = conn_temp.cursor()
        c_temp.execute('SELECT role FROM users WHERE id = ?', (session.get('user_id'),))
        user = c_temp.fetchone()
        conn_temp.close()
        sender_role = user[0] if user else 'financial_institution'
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Inserir a comunicação
    c.execute('''INSERT INTO communications 
                 (process_id, sender_id, sender_role, message, message_type, is_internal)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (process_id, session.get('user_id'), sender_role, 
               message, message_type, 0))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/process/<int:process_id>/has-analysis')
@login_required
def check_has_analysis(process_id):
    """Verifica se o processo já possui análise de IA"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Verificar se existe log de uso de IA para este processo
    c.execute('SELECT COUNT(*) FROM ai_usage_log WHERE process_id = ?', (process_id,))
    count = c.fetchone()[0]
    conn.close()
    
    return jsonify({'has_analysis': count > 0})

@app.route('/api/process/<int:process_id>/return-info')
@login_required
def get_return_info(process_id):
    """Retorna informações de devolução do processo"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Buscar a última comunicação de devolução
    c.execute('''SELECT message, created_at FROM communications 
                 WHERE process_id = ? 
                 AND message_type = 'return_reason'
                 ORDER BY id DESC LIMIT 1''', (process_id,))
    
    return_comm = c.fetchone()
    conn.close()
    
    if not return_comm:
        return jsonify({'has_return_info': False})
    
    message = return_comm[0] or ''
    
    # Limpar prefixo se houver
    reason = message.replace('📋 Processo devolvido para correção:\n\n', '')
    
    # Verificar se há informação sobre documentos com problema
    problem_docs = []
    if '[Documentos com problema:' in reason:
        parts = reason.split('\n\n[Documentos com problema:')
        reason = parts[0] if parts else reason
    
    return jsonify({
        'has_return_info': True,
        'reason': reason,
        'problem_docs': problem_docs,
        'return_date': return_comm[1]
    })

@app.route('/api/process/<int:process_id>/analyze', methods=['POST'])
@login_required
@role_required('rpps')
def analyze_process_with_ai(process_id):
    """Inicia análise com IA de todos os documentos do processo"""
    try:
        from datetime import datetime, timedelta
        
        conn = sqlite3.connect('credenciamento.db')
        c = conn.cursor()
        
        user_id = session.get('user_id')
        
        # ========== PROTEÇÃO FINANCEIRA: CONTROLE DE USO DE IA ==========
        
        # 1. Verificar limite diário de análises por processo (máx 3 por dia)
        c.execute('''SELECT COUNT(*) FROM ai_usage_log 
                     WHERE process_id = ? AND analysis_date = DATE('now')''', (process_id,))
        daily_count = c.fetchone()[0]
        
        MAX_DAILY_ANALYSES = 3
        if daily_count >= MAX_DAILY_ANALYSES:
            conn.close()
            return jsonify({
                'success': False, 
                'error': f'Limite diário atingido. Este processo já foi analisado {daily_count} vez(es) hoje. Máximo permitido: {MAX_DAILY_ANALYSES} análises por dia.'
            }), 429
        
        # 2. Verificar cooldown entre análises (mínimo 30 minutos)
        c.execute('''SELECT created_at FROM ai_usage_log 
                     WHERE process_id = ? 
                     ORDER BY created_at DESC LIMIT 1''', (process_id,))
        last_analysis = c.fetchone()
        
        if last_analysis:
            last_time = datetime.strptime(last_analysis[0], '%Y-%m-%d %H:%M:%S')
            cooldown_minutes = 30
            time_diff = datetime.now() - last_time
            
            if time_diff < timedelta(minutes=cooldown_minutes):
                remaining = cooldown_minutes - int(time_diff.total_seconds() / 60)
                conn.close()
                return jsonify({
                    'success': False, 
                    'error': f'Aguarde {remaining} minuto(s) antes de solicitar nova análise. Cooldown: {cooldown_minutes} minutos entre análises.'
                }), 429
        
        # ========== FIM PROTEÇÃO FINANCEIRA ==========
        
        # Buscar processo e instituição
        c.execute('''SELECT financial_institution_name FROM processes WHERE id = ?''', (process_id,))
        process = c.fetchone()
        
        if not process:
            conn.close()
            return jsonify({'success': False, 'error': 'Processo não encontrado'}), 404
        
        institution_name = process[0]
        
        # Buscar todos os documentos do processo
        c.execute('SELECT id, filename, type, name FROM documents WHERE process_id = ?', (process_id,))
        documents = c.fetchall()
        
        if not documents:
            conn.close()
            return jsonify({'success': False, 'error': 'Nenhum documento encontrado'}), 400
        
        # Registrar uso de IA (ANTES de analisar)
        tokens_estimated = len(documents) * 3000  # ~3000 tokens por documento
        c.execute('''INSERT INTO ai_usage_log 
                     (process_id, user_id, documents_analyzed, tokens_estimated)
                     VALUES (?, ?, ?, ?)''',
                  (process_id, user_id, len(documents), tokens_estimated))
        
        print(f"\n{'='*60}")
        print(f"🔍 ANÁLISE COM IA INICIADA - Processo {process_id}")
        print(f"   Instituição: {institution_name}")
        print(f"   Documentos encontrados: {len(documents)}")
        print(f"   💰 Tokens estimados: {tokens_estimated}")
        print(f"   📊 Análise #{daily_count + 1} do dia para este processo")
        print(f"{'='*60}\n")
        
        # Atualizar status do processo para "em análise"
        c.execute('UPDATE processes SET status = ? WHERE id = ?', ('in_review', process_id))
        
        # Registrar no histórico
        log_process_history(process_id, 'Análise com IA iniciada', f'{len(documents)} documento(s) analisados')
        
        # Adicionar mensagem inicial
        c.execute('''INSERT INTO communications 
                     (process_id, sender_id, sender_role, message, message_type, is_internal)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (process_id, session.get('user_id'), 'rpps', 
                   f'🤖 Análise com IA iniciada para {len(documents)} documento(s)...', 'system', 0))
        
        conn.commit()
        
        # Analisar cada documento
        analysis_count = 0
        for doc_id, filename, doc_type, doc_name in documents:
            try:
                full_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                print(f"\n📄 Analisando documento: {doc_name}")
                print(f"   Tipo: {doc_type}")
                print(f"   Arquivo: {filename}")
                print(f"   Caminho: {full_path}")
                
                if not os.path.exists(full_path):
                    print(f"   ❌ Arquivo não encontrado!")
                    error_msg = f"❌ Documento '{doc_name}' não encontrado no servidor"
                    c.execute('''INSERT INTO communications 
                                 (process_id, sender_id, sender_role, message, message_type, is_internal)
                                 VALUES (?, ?, ?, ?, ?, ?)''',
                              (process_id, session.get('user_id'), 'rpps', error_msg, 'system', 0))
                    continue
                
                # Chamar análise RIGOROSA com IA
                print(f"   🤖 Chamando analyze_document_rigorous()...")
                result = analyze_document_rigorous(full_path, doc_type, doc_name, institution_name)
                print(f"   ✅ Análise concluída!")
                
                # Formatar resultado bonito
                if isinstance(result, dict):
                    is_valid = result.get('is_valid', False)
                    score = result.get('score', 0)
                    issues = result.get('issues', [])
                    warnings = result.get('warnings', [])
                    details = result.get('details', {})
                    
                    # Criar mensagem formatada
                    status_icon = "✅" if is_valid else "❌"
                    message_parts = [
                        f"\n{'='*50}",
                        f"{status_icon} **ANÁLISE: {doc_name}**",
                        f"{'='*50}",
                        f"\n📊 **Score:** {score}/100",
                        f"📋 **Tipo:** {doc_type}",
                        f"🔍 **Status:** {'APROVADO' if is_valid else 'REPROVADO'}",
                    ]
                    
                    # Detalhes da IA
                    if details.get('ai_powered'):
                        message_parts.append(f"\n🤖 **Análise com IA:** {details.get('provider', 'Gemini')}")
                        message_parts.append(f"   Confiança: {int(details.get('confidence', 0) * 100)}%")
                        if details.get('summary'):
                            message_parts.append(f"\n📝 **Resumo:** {details['summary']}")
                    
                    # Problemas encontrados
                    if issues:
                        message_parts.append(f"\n❌ **Problemas Encontrados:**")
                        for issue in issues:
                            message_parts.append(f"   • {issue}")
                    
                    # Avisos
                    if warnings:
                        message_parts.append(f"\n⚠️ **Avisos:**")
                        for warning in warnings:
                            message_parts.append(f"   • {warning}")
                    
                    # Se aprovado, mostrar pontos positivos
                    if is_valid and not issues:
                        message_parts.append(f"\n✅ **Pontos Positivos:**")
                        message_parts.append(f"   • Documento em conformidade")
                        message_parts.append(f"   • Tipo correto identificado")
                        message_parts.append(f"   • Conteúdo adequado para credenciamento")
                    
                    message_parts.append(f"\n{'='*50}\n")
                    
                    message = "\n".join(message_parts)
                else:
                    # Resultado em texto simples
                    message = f"\n📄 **{doc_name}**\n\n{result}"
                
                # Salvar resultado na comunicação
                c.execute('''INSERT INTO communications 
                             (process_id, sender_id, sender_role, message, message_type, is_internal)
                             VALUES (?, ?, ?, ?, ?, ?)''',
                          (process_id, session.get('user_id'), 'rpps', message, 'system', 0))
                
                conn.commit()
                analysis_count += 1
                print(f"   💾 Resultado salvo nas comunicações!")
                
            except Exception as e:
                print(f"   ❌ Erro ao analisar documento {doc_id}: {e}")
                import traceback
                traceback.print_exc()
                
                error_msg = f"❌ Erro ao analisar '{doc_name}': {str(e)}"
                c.execute('''INSERT INTO communications 
                             (process_id, sender_id, sender_role, message, message_type, is_internal)
                             VALUES (?, ?, ?, ?, ?, ?)''',
                          (process_id, session.get('user_id'), 'rpps', error_msg, 'system', 0))
                conn.commit()
        
        # Mensagem final
        final_message = f"\n🎉 **Análise concluída!** {analysis_count}/{len(documents)} documentos analisados com sucesso."
        c.execute('''INSERT INTO communications 
                     (process_id, sender_id, sender_role, message, message_type, is_internal)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (process_id, session.get('user_id'), 'rpps', final_message, 'system', 0))
        
        conn.commit()
        conn.close()
        
        print(f"\n{'='*60}")
        print(f"✅ ANÁLISE COMPLETA!")
        print(f"   Documentos analisados: {analysis_count}/{len(documents)}")
        print(f"{'='*60}\n")
        
        return jsonify({
            'success': True, 
            'message': f'Análise concluída! {analysis_count} documento(s) processado(s).',
            'analyzed': analysis_count,
            'total': len(documents)
        })
        
    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO na análise com IA: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/process/<int:process_id>/change-status', methods=['POST'])
@login_required
def change_process_status(process_id):
    data = request.json
    new_status = data.get('status')
    reason = data.get('reason', '')
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    c.execute('UPDATE processes SET status = ? WHERE id = ?', (new_status, process_id))
    
    # Se foi devolvido, salvar o motivo na tabela de communications
    if new_status == 'returned' and reason:
        user_id = session.get('user_id')
        user_role = session.get('role', 'rpps')
        
        # Formatar mensagem de devolução
        message = f"📋 Processo devolvido para correção:\n\n{reason}"
        
        c.execute('''INSERT INTO communications (process_id, sender_id, sender_role, message, message_type, created_at)
                     VALUES (?, ?, ?, ?, 'return_reason', datetime('now'))''',
                  (process_id, user_id, user_role, message))
    
    conn.commit()
    conn.close()
    
    # Registrar no histórico
    status_labels = {
        'draft': 'Rascunho',
        'submitted': 'Enviado para análise',
        'in_review': 'Em análise pelo RPPS',
        'returned': 'Devolvido para correção',
        'approved': 'Aprovado',
        'rejected': 'Rejeitado'
    }
    action = f"Status alterado para: {status_labels.get(new_status, new_status)}"
    details = reason if reason else None
    log_process_history(process_id, action, details)
    
    return jsonify({'success': True})

@app.route('/api/process/<int:process_id>/request-document', methods=['POST'])
@login_required
def request_document(process_id):
    """Solicitar documento adicional ao IF"""
    data = request.json
    document_type = data.get('document_type', 'Documento Adicional')
    description = data.get('description', '')
    
    if not description:
        return jsonify({'success': False, 'error': 'Descrição é obrigatória'}), 400
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    user_id = session.get('user_id')
    user_role = session.get('role', 'rpps')
    
    # Salvar solicitação como comunicação
    message = f"📄 Solicitação de Documento:\n\n{description}"
    
    c.execute('''INSERT INTO communications (process_id, sender_id, sender_role, message, message_type, created_at)
                 VALUES (?, ?, ?, ?, 'document_request', datetime('now'))''',
              (process_id, user_id, user_role, message))
    
    conn.commit()
    conn.close()
    
    # Registrar no histórico
    log_process_history(process_id, 'Documento adicional solicitado', description)
    
    return jsonify({'success': True})

@app.route('/api/process/<int:process_id>/document-requests')
@login_required
def get_document_requests(process_id):
    """Retorna solicitações de documentos pendentes"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Buscar todas as solicitações de documentos
    c.execute('''SELECT id, message, created_at FROM communications 
                 WHERE process_id = ? 
                 AND message_type = 'document_request'
                 ORDER BY id DESC''', (process_id,))
    
    requests_data = c.fetchall()
    conn.close()
    
    document_requests = []
    for req in requests_data:
        message = req[1] or ''
        # Limpar prefixo
        description = message.replace('📄 Solicitação de Documento:\n\n', '')
        document_requests.append({
            'id': req[0],
            'description': description,
            'created_at': req[2]
        })
    
    return jsonify({
        'requests': document_requests,
        'count': len(document_requests)
    })

@app.route('/api/process/<int:process_id>/pending-issues')
@login_required
def get_pending_issues(process_id):
    """Retorna pendências do processo (devolução e/ou documentos solicitados não atendidos)"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Verificar status do processo
    c.execute('SELECT status FROM processes WHERE id = ?', (process_id,))
    result = c.fetchone()
    status = result[0] if result else None
    
    # Verificar se há devolução pendente (status = returned)
    has_return_pending = status == 'returned'
    
    # Buscar solicitações de documentos não atendidas
    c.execute('''SELECT id, message, created_at FROM communications 
                 WHERE process_id = ? 
                 AND message_type = 'document_request'
                 AND (is_fulfilled IS NULL OR is_fulfilled = 0)
                 ORDER BY id ASC''', (process_id,))
    pending_requests = c.fetchall()
    
    conn.close()
    
    pending_docs = []
    for req in pending_requests:
        message = req[1] or ''
        description = message.replace('📄 Solicitação de Documento:\n\n', '')
        pending_docs.append({
            'id': req[0],
            'description': description,
            'created_at': req[2]
        })
    
    has_pending = has_return_pending or len(pending_docs) > 0
    
    return jsonify({
        'has_pending': has_pending,
        'return_pending': has_return_pending,
        'document_requests': pending_docs,
        'document_requests_count': len(pending_docs)
    })

@app.route('/api/process/<int:process_id>/resolve-issues', methods=['POST'])
@login_required
def resolve_issues(process_id):
    """Marca pendências como resolvidas e atualiza status se todas foram sanadas"""
    data = request.json
    resolve_return = data.get('resolve_return', False)
    resolved_doc_ids = data.get('resolved_doc_ids', [])
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Verificar estado atual
    c.execute('SELECT status FROM processes WHERE id = ?', (process_id,))
    result = c.fetchone()
    current_status = result[0] if result else None
    
    history_actions = []
    
    # Resolver devolução
    if resolve_return and current_status == 'returned':
        history_actions.append(('Documento enviado após correção', 'Correção do processo devolvido'))
    
    # Marcar documentos solicitados como atendidos
    if resolved_doc_ids:
        for doc_id in resolved_doc_ids:
            c.execute('UPDATE communications SET is_fulfilled = 1 WHERE id = ?', (doc_id,))
        
        # Buscar descrições dos documentos para o histórico
        placeholders = ','.join('?' * len(resolved_doc_ids))
        c.execute(f'SELECT message FROM communications WHERE id IN ({placeholders})', resolved_doc_ids)
        for row in c.fetchall():
            desc = row[0].replace('📄 Solicitação de Documento:\n\n', '') if row[0] else 'Documento adicional'
            history_actions.append(('Documento solicitado enviado', desc[:100]))
    
    # Verificar se TODAS as pendências foram resolvidas
    c.execute('''SELECT COUNT(*) FROM communications 
                 WHERE process_id = ? 
                 AND message_type = 'document_request'
                 AND (is_fulfilled IS NULL OR is_fulfilled = 0)''', (process_id,))
    remaining_docs = c.fetchone()[0]
    
    # Se resolveu a devolução, verifica se não há mais docs pendentes
    all_resolved = False
    if resolve_return and remaining_docs == 0:
        all_resolved = True
    elif not resolve_return and current_status != 'returned' and remaining_docs == 0:
        # Não tinha devolução pendente e resolveu todos os docs
        all_resolved = True
    elif resolve_return and remaining_docs > 0:
        # Resolveu devolução mas ainda há docs pendentes
        all_resolved = False
    
    # Se todas as pendências foram resolvidas, mudar status para submitted
    new_status = current_status
    if all_resolved:
        new_status = 'submitted'
        c.execute('UPDATE processes SET status = ?, submitted_at = CURRENT_TIMESTAMP WHERE id = ?', 
                  (new_status, process_id))
        history_actions.append(('Processo reenviado ao RPPS', 'Todas as pendências foram sanadas'))
    
    conn.commit()
    conn.close()
    
    # Registrar ações no histórico
    for action, details in history_actions:
        log_process_history(process_id, action, details)
    
    return jsonify({
        'success': True,
        'all_resolved': all_resolved,
        'new_status': new_status,
        'remaining_docs': remaining_docs
    })

@app.route('/api/process/<int:process_id>/history')
@login_required
def get_process_history(process_id):
    """Retorna histórico completo do processo"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Buscar dados completos do processo para incluir eventos inferidos
    c.execute('''SELECT created_at, financial_institution_name, rpps_name, status,
                        submitted_at, reviewed_at, final_decision_at, final_decision
                 FROM processes WHERE id = ?''', (process_id,))
    process_data = c.fetchone()
    
    # Buscar histórico registrado
    c.execute('''SELECT user_name, user_role, action, details, created_at 
                 FROM process_history 
                 WHERE process_id = ? 
                 ORDER BY created_at ASC''', (process_id,))
    history_data = c.fetchall()
    
    # Buscar comunicações de devolução que não estão no histórico
    c.execute('''SELECT sender_role, message, created_at FROM communications 
                 WHERE process_id = ? AND message_type = 'return_reason'
                 ORDER BY created_at ASC''', (process_id,))
    return_comms = c.fetchall()
    
    # Buscar solicitações de documentos
    c.execute('''SELECT sender_role, message, created_at FROM communications 
                 WHERE process_id = ? AND message_type = 'document_request'
                 ORDER BY created_at ASC''', (process_id,))
    doc_requests = c.fetchall()
    
    conn.close()
    
    history = []
    existing_actions = set()
    
    # Rastrear ações já registradas
    for item in history_data:
        existing_actions.add((item[2], item[4]))  # (action, created_at)
    
    # Adicionar criação do processo como primeiro item
    if process_data:
        history.append({
            'user_name': process_data[1] or 'Instituição Financeira',
            'user_role': 'financial_institution',
            'action': 'Processo criado',
            'details': f'Processo de credenciamento iniciado',
            'created_at': process_data[0],
            'icon': 'create'
        })
        
        # Se foi submetido mas não está no histórico, adicionar
        if process_data[4]:  # submitted_at
            submitted_found = any('enviado' in str(h[2]).lower() for h in history_data)
            if not submitted_found:
                history.append({
                    'user_name': process_data[1] or 'Instituição Financeira',
                    'user_role': 'financial_institution',
                    'action': 'Processo enviado ao RPPS',
                    'details': 'Documentos submetidos para análise',
                    'created_at': process_data[4],
                    'icon': 'send'
                })
    
    # Adicionar histórico registrado
    for item in history_data:
        history.append({
            'user_name': item[0] or 'Sistema',
            'user_role': item[1] or 'system',
            'action': item[2],
            'details': item[3],
            'created_at': item[4],
            'icon': get_history_icon(item[2])
        })
    
    # Adicionar devoluções da tabela de communications se não estão no histórico
    for comm in return_comms:
        devol_found = any('devolvido' in str(h.get('action', '')).lower() and h.get('created_at') == comm[2] for h in history)
        if not devol_found:
            history.append({
                'user_name': 'RPPS',
                'user_role': comm[0] or 'rpps',
                'action': 'Processo devolvido para correção',
                'details': comm[1].replace('📋 Processo devolvido para correção:\n\n', ''),
                'created_at': comm[2],
                'icon': 'return'
            })
    
    # Adicionar solicitações de documentos se não estão no histórico
    for req in doc_requests:
        req_found = any('solicit' in str(h.get('action', '')).lower() and h.get('created_at') == req[2] for h in history)
        if not req_found:
            history.append({
                'user_name': 'RPPS',
                'user_role': req[0] or 'rpps',
                'action': 'Documento adicional solicitado',
                'details': req[1].replace('📋 Documento adicional solicitado:\n\n', ''),
                'created_at': req[2],
                'icon': 'request'
            })
    
    # Ordenar por data
    history.sort(key=lambda x: x['created_at'] if x['created_at'] else '')
    
    return jsonify({
        'history': history,
        'count': len(history)
    })

def get_history_icon(action):
    """Retorna o ícone apropriado para cada tipo de ação"""
    action_lower = action.lower() if action else ''
    if 'criado' in action_lower or 'criar' in action_lower:
        return 'create'
    elif 'enviado' in action_lower or 'submeter' in action_lower:
        return 'send'
    elif 'análise' in action_lower or 'analis' in action_lower:
        return 'analyze'
    elif 'devolvido' in action_lower or 'devolução' in action_lower:
        return 'return'
    elif 'aprovado' in action_lower:
        return 'approve'
    elif 'rejeitado' in action_lower:
        return 'reject'
    elif 'documento' in action_lower:
        return 'document'
    elif 'ia' in action_lower or 'inteligência' in action_lower:
        return 'ai'
    else:
        return 'default'

# ============== DOCUMENTOS ESPECIAIS (Termo de Credenciamento) ==============

@app.route('/api/process/<int:process_id>/special-documents')
@login_required
def get_special_documents(process_id):
    """Retorna documentos especiais (Termo de Credenciamento) com todas as versões"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    c.execute('''SELECT id, document_type, version, status, filename, original_filename, 
                        mime_type, uploaded_by_role, notes, created_at
                 FROM special_documents 
                 WHERE process_id = ? 
                 ORDER BY created_at ASC''', (process_id,))
    
    documents = []
    for row in c.fetchall():
        documents.append({
            'id': row[0],
            'document_type': row[1],
            'version': row[2],
            'status': row[3],
            'filename': row[4],
            'original_filename': row[5],
            'mime_type': row[6],
            'uploaded_by_role': row[7],
            'notes': row[8],
            'created_at': row[9]
        })
    
    # Verificar se há documento aguardando assinatura da IF
    awaiting_if = any(d['status'] == 'awaiting_if_signature' for d in documents)
    
    # Verificar se há documento oficial final
    has_official = any(d['status'] == 'official_final' for d in documents)
    
    # Determinar o status atual do fluxo
    current_status = None
    if documents:
        # Ordem de prioridade: official_final > signed_by_if > awaiting_if_signature > pdf_rpps_signed > excel_if
        status_priority = ['official_final', 'signed_by_if', 'awaiting_if_signature', 'pdf_rpps_signed', 'excel_if']
        for status in status_priority:
            if any(d['status'] == status for d in documents):
                current_status = status
                break
    
    conn.close()
    
    return jsonify({
        'documents': documents,
        'count': len(documents),
        'awaiting_if_signature': awaiting_if,
        'has_official_final': has_official,
        'current_status': current_status
    })

@app.route('/api/process/<int:process_id>/special-document', methods=['POST'])
@login_required
def upload_special_document(process_id):
    """Upload de documento especial (Termo de Credenciamento) pelo RPPS"""
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    
    status = request.form.get('status', 'pdf_rpps_signed')
    notes = request.form.get('notes', '')
    document_type = request.form.get('document_type', 'termo_credenciamento')
    
    # Calcular próxima versão
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    c.execute('SELECT MAX(version) FROM special_documents WHERE process_id = ? AND document_type = ?', 
              (process_id, document_type))
    max_version = c.fetchone()[0] or 0
    new_version = max_version + 1
    
    # Salvar arquivo
    original_filename = file.filename
    filename = secure_filename(f"special_{process_id}_{document_type}_v{new_version}_{file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    # Inserir no banco
    c.execute('''INSERT INTO special_documents 
                 (process_id, document_type, version, status, filename, original_filename, 
                  mime_type, uploaded_by, uploaded_by_role, notes)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (process_id, document_type, new_version, status, filename, original_filename,
               file.content_type, session.get('user_id'), session.get('role'), notes))
    
    doc_id = c.lastrowid
    conn.commit()
    conn.close()
    
    # Registrar no histórico
    status_labels = {
        'pdf_rpps_signed': 'Termo alterado e assinado pelo RPPS',
        'awaiting_if_signature': 'Termo enviado para assinatura da IF',
        'signed_by_if': 'Termo assinado pela IF',
        'official_final': 'Termo de Credenciamento oficial finalizado'
    }
    log_process_history(process_id, status_labels.get(status, 'Documento especial adicionado'), 
                        f'Versão {new_version} - {notes}' if notes else f'Versão {new_version}')
    
    return jsonify({
        'success': True,
        'document_id': doc_id,
        'version': new_version
    })

@app.route('/api/process/<int:process_id>/send-term-for-signature', methods=['POST'])
@login_required
@role_required('rpps')
def send_term_for_signature(process_id):
    """RPPS envia o termo para a IF assinar"""
    data = request.json
    special_doc_id = data.get('special_doc_id')
    message = data.get('message', 'Por favor, assine digitalmente o Termo de Credenciamento e retorne.')
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Se não foi passado special_doc_id, buscar o mais recente com status pdf_rpps_signed
    if not special_doc_id:
        c.execute('''SELECT id FROM special_documents 
                     WHERE process_id = ? AND status = 'pdf_rpps_signed'
                     ORDER BY created_at DESC LIMIT 1''', (process_id,))
        result = c.fetchone()
        if result:
            special_doc_id = result[0]
        else:
            conn.close()
            return jsonify({'error': 'Nenhum documento assinado encontrado'}), 400
    
    # Atualizar status do documento
    c.execute('UPDATE special_documents SET status = ? WHERE id = ?', 
              ('awaiting_if_signature', special_doc_id))
    
    # Criar comunicação especial
    c.execute('''INSERT INTO communications 
                 (process_id, sender_id, sender_role, message, message_type)
                 VALUES (?, ?, ?, ?, ?)''',
              (process_id, session.get('user_id'), 'rpps', 
               f'📝 Termo de Credenciamento enviado para assinatura:\n\n{message}', 
               'term_signature_request'))
    
    conn.commit()
    conn.close()
    
    # Registrar no histórico
    log_process_history(process_id, 'Termo enviado para assinatura da IF', message)
    
    return jsonify({'success': True})

@app.route('/api/process/<int:process_id>/return-signed-term', methods=['POST'])
@login_required
@role_required('financial_institution')
def return_signed_term(process_id):
    """IF retorna o termo assinado"""
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Calcular próxima versão
    c.execute('SELECT MAX(version) FROM special_documents WHERE process_id = ? AND document_type = ?', 
              (process_id, 'termo_credenciamento'))
    max_version = c.fetchone()[0] or 0
    new_version = max_version + 1
    
    # Salvar arquivo
    original_filename = file.filename
    filename = secure_filename(f"special_{process_id}_termo_signed_if_v{new_version}_{file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    # Inserir no banco
    c.execute('''INSERT INTO special_documents 
                 (process_id, document_type, version, status, filename, original_filename, 
                  mime_type, uploaded_by, uploaded_by_role, notes)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (process_id, 'termo_credenciamento', new_version, 'signed_by_if', filename, original_filename,
               file.content_type, session.get('user_id'), 'financial_institution', 
               'Termo assinado digitalmente pela Instituição Financeira'))
    
    conn.commit()
    conn.close()
    
    # Registrar no histórico
    log_process_history(process_id, 'Termo assinado pela IF', 'Documento retornado com assinatura digital')
    
    return jsonify({'success': True, 'version': new_version})

@app.route('/api/process/<int:process_id>/finalize-term', methods=['POST'])
@login_required
@role_required('rpps')
def finalize_term(process_id):
    """RPPS finaliza o termo e junta ao dossiê oficial"""
    data = request.json
    special_doc_id = data.get('special_doc_id')
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Buscar documento especial
    c.execute('SELECT filename, original_filename, mime_type FROM special_documents WHERE id = ?', 
              (special_doc_id,))
    doc = c.fetchone()
    
    if not doc:
        conn.close()
        return jsonify({'error': 'Documento não encontrado'}), 404
    
    # Marcar como oficial
    c.execute('UPDATE special_documents SET status = ? WHERE id = ?', ('official_final', special_doc_id))
    
    # Remover documento antigo do tipo termo_credenciamento da tabela documents (se existir)
    c.execute('DELETE FROM documents WHERE process_id = ? AND type = ?', 
              (process_id, 'termo_credenciamento'))
    
    # Adicionar documento oficial à tabela documents
    c.execute('''INSERT INTO documents 
                 (process_id, type, name, filename, mime_type, uploaded_by, status, analysis_data)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (process_id, 'termo_credenciamento', 'Termo de Credenciamento (Oficial Assinado)', 
               doc[0], doc[2], session.get('user_id'), 'approved', 
               json.dumps({'status': 'official', 'is_special_document': True, 'finalized_at': datetime.now().isoformat()})))
    
    conn.commit()
    conn.close()
    
    # Registrar no histórico
    log_process_history(process_id, 'Termo de Credenciamento finalizado', 
                        'Documento oficial com todas as assinaturas juntado ao dossiê')
    
    return jsonify({'success': True})

@app.route('/api/process/<int:process_id>/check-term-pending')
@login_required
def check_term_pending(process_id):
    """Verifica se há termo aguardando assinatura da IF"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    c.execute('''SELECT id, filename, original_filename, notes, created_at 
                 FROM special_documents 
                 WHERE process_id = ? AND status = 'awaiting_if_signature'
                 ORDER BY created_at DESC LIMIT 1''', (process_id,))
    
    doc = c.fetchone()
    conn.close()
    
    if doc:
        return jsonify({
            'has_pending': True,
            'document': {
                'id': doc[0],
                'filename': doc[1],
                'original_filename': doc[2],
                'notes': doc[3],
                'created_at': doc[4]
            }
        })
    
    return jsonify({'has_pending': False})

@app.route('/api/special-document/<int:doc_id>/download')
@login_required
def download_special_document(doc_id):
    """Download de documento especial"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    c.execute('SELECT filename, original_filename, mime_type FROM special_documents WHERE id = ?', (doc_id,))
    doc = c.fetchone()
    conn.close()
    
    if not doc:
        return jsonify({'error': 'Documento não encontrado'}), 404
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], doc[0])
    if not os.path.exists(filepath):
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    
    # Usar mime_type para garantir que o navegador reconheça o tipo de arquivo
    return send_file(filepath, as_attachment=True, download_name=doc[1], mimetype=doc[2])

# ============== FIM DOCUMENTOS ESPECIAIS ==============

# ============== ASSINADOR DIGITAL ==============

@app.route('/api/signer/status')
@login_required
def signer_status():
    """Retorna o status do assinador digital"""
    return jsonify({
        'available': True,
        'a1_available': PYHANKO_AVAILABLE,
        'a3_available': True,  # A3 é sempre possível via Fortify
        'message': 'Assinador digital pronto' if PYHANKO_AVAILABLE else 'Assinatura A1 indisponível (pyHanko não instalado)'
    })

@app.route('/api/signer/validate-certificate', methods=['POST'])
@login_required
def validate_certificate():
    """Valida um certificado A1 (.pfx/.p12) e retorna suas informações"""
    if 'certificate' not in request.files:
        return jsonify({'error': 'Nenhum certificado enviado'}), 400
    
    cert_file = request.files['certificate']
    password = request.form.get('password', '')
    
    if not cert_file.filename:
        return jsonify({'error': 'Arquivo inválido'}), 400
    
    try:
        pfx_data = cert_file.read()
        
        # Carregar e validar certificado
        private_key, certificate, chain, error = digital_signer.load_pfx_certificate(pfx_data, password)
        
        if error:
            return jsonify({'error': error}), 400
        
        # Obter informações do certificado
        cert_info = digital_signer.get_certificate_info(certificate)
        
        return jsonify({
            'valid': True,
            'info': cert_info
        })
        
    except Exception as e:
        return jsonify({'error': f'Erro ao processar certificado: {str(e)}'}), 400

@app.route('/api/signer/sign-a1', methods=['POST'])
@login_required
def sign_document_a1():
    """Assina um documento PDF com certificado A1"""
    if 'document' not in request.files:
        return jsonify({'error': 'Nenhum documento enviado'}), 400
    
    if 'certificate' not in request.files:
        return jsonify({'error': 'Nenhum certificado enviado'}), 400
    
    doc_file = request.files['document']
    cert_file = request.files['certificate']
    password = request.form.get('password', '')
    reason = request.form.get('reason', 'Documento assinado digitalmente')
    location = request.form.get('location', 'Brasil')
    visual_signature = request.form.get('visual_signature', 'true').lower() == 'true'
    signature_position = request.form.get('signature_position', 'bottom-right')
    page = int(request.form.get('page', '-1'))  # -1 = última página
    
    if not doc_file.filename or not cert_file.filename:
        return jsonify({'error': 'Arquivos inválidos'}), 400
    
    if not doc_file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Apenas arquivos PDF são suportados'}), 400
    
    try:
        pdf_data = doc_file.read()
        pfx_data = cert_file.read()
        
        # Assinar o documento
        signed_pdf, error = digital_signer.sign_pdf_a1(
            pdf_data=pdf_data,
            pfx_data=pfx_data,
            password=password,
            reason=reason,
            location=location,
            visual_signature=visual_signature,
            signature_position=signature_position,
            page=page
        )
        
        if error:
            return jsonify({'error': error}), 400
        
        # Criar nome do arquivo assinado
        original_name = os.path.splitext(doc_file.filename)[0]
        signed_filename = f"{original_name}_assinado.pdf"
        
        # Retornar arquivo assinado
        return send_file(
            io.BytesIO(signed_pdf),
            as_attachment=True,
            download_name=signed_filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Erro ao assinar documento: {str(e)}'}), 500

@app.route('/api/signer/sign-process-document/<int:doc_id>', methods=['POST'])
@login_required
def sign_process_document(doc_id):
    """Assina um documento do processo com certificado A1 e salva como novo documento"""
    if 'certificate' not in request.files:
        return jsonify({'error': 'Nenhum certificado enviado'}), 400
    
    cert_file = request.files['certificate']
    password = request.form.get('password', '')
    reason = request.form.get('reason', 'Documento assinado digitalmente')
    location = request.form.get('location', 'Brasil')
    visual_signature = request.form.get('visual_signature', 'true').lower() == 'true'
    signature_position = request.form.get('signature_position', 'bottom-right')
    
    # Buscar documento original
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    c.execute('SELECT filename, original_filename, process_id, document_type FROM documents WHERE id = ?', (doc_id,))
    doc = c.fetchone()
    
    if not doc:
        conn.close()
        return jsonify({'error': 'Documento não encontrado'}), 404
    
    filename, original_filename, process_id, doc_type = doc
    
    # Verificar se é PDF
    if not original_filename.lower().endswith('.pdf'):
        conn.close()
        return jsonify({'error': 'Apenas documentos PDF podem ser assinados'}), 400
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        conn.close()
        return jsonify({'error': 'Arquivo não encontrado no servidor'}), 404
    
    try:
        # Ler o PDF
        with open(filepath, 'rb') as f:
            pdf_data = f.read()
        
        pfx_data = cert_file.read()
        
        # Assinar o documento
        signed_pdf, error = digital_signer.sign_pdf_a1(
            pdf_data=pdf_data,
            pfx_data=pfx_data,
            password=password,
            reason=reason,
            location=location,
            visual_signature=visual_signature,
            signature_position=signature_position,
            page=-1  # Última página
        )
        
        if error:
            conn.close()
            return jsonify({'error': error}), 400
        
        # Salvar como novo documento
        original_base = os.path.splitext(original_filename)[0]
        signed_original_name = f"{original_base}_assinado.pdf"
        
        # Gerar nome único
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        safe_name = secure_filename(signed_original_name)
        new_filename = f"{process_id}_{doc_type}_{timestamp}_{safe_name}"
        new_filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
        
        with open(new_filepath, 'wb') as f:
            f.write(signed_pdf)
        
        # Registrar no banco
        c.execute('''
            INSERT INTO documents (process_id, document_type, name, filename, original_filename, mime_type, uploaded_by, uploaded_by_role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            process_id, 
            doc_type, 
            f"{doc_type} (Assinado)",
            new_filename, 
            signed_original_name,
            'application/pdf',
            session.get('user_id'),
            session.get('role')
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Documento assinado com sucesso',
            'signed_filename': signed_original_name
        })
        
    except Exception as e:
        conn.close()
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Erro ao assinar documento: {str(e)}'}), 500

@app.route('/api/signer/prepare-a3-hash', methods=['POST'])
@login_required
def prepare_a3_hash():
    """Prepara o hash de um documento para assinatura A3 client-side"""
    if 'document' not in request.files:
        return jsonify({'error': 'Nenhum documento enviado'}), 400
    
    doc_file = request.files['document']
    
    if not doc_file.filename or not doc_file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Apenas arquivos PDF são suportados'}), 400
    
    try:
        pdf_data = doc_file.read()
        
        # Preparar hash para assinatura A3
        hash_data, error = digital_signer.prepare_hash_for_a3(pdf_data)
        
        if error:
            return jsonify({'error': error}), 400
        
        return jsonify({
            'success': True,
            'hash_data': hash_data
        })
        
    except Exception as e:
        return jsonify({'error': f'Erro ao preparar hash: {str(e)}'}), 500

# ============== FIM ASSINADOR DIGITAL ==============

@app.route('/api/process/<int:process_id>/delete', methods=['DELETE'])
@login_required
def delete_process(process_id):
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Deletar documentos associados
    c.execute('DELETE FROM documents WHERE process_id = ?', (process_id,))
    
    # Deletar comunicações associadas
    c.execute('DELETE FROM communications WHERE process_id = ?', (process_id,))
    
    # Deletar o processo
    c.execute('DELETE FROM processes WHERE id = ?', (process_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        email = data.get('email')
        password = data.get('password')
        
        conn = sqlite3.connect('credenciamento.db')
        c = conn.cursor()
        c.execute('SELECT id, email, password, name, role FROM users WHERE email = ?', (email,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['user_email'] = user[1]
            session['user_name'] = user[3]
            session['user_role'] = user[4]
            return jsonify({'success': True, 'role': user[4]})
        else:
            return jsonify({'success': False, 'error': 'Email ou senha incorretos'}), 401
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.json
        email = data.get('email')
        password = data.get('password')
        name = data.get('name')
        cpf_cnpj = data.get('cpf_cnpj')
        role = data.get('role')
        
        conn = sqlite3.connect('credenciamento.db')
        c = conn.cursor()
        
        # Verificar se email já existe
        c.execute('SELECT id FROM users WHERE email = ?', (email,))
        if c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Email já cadastrado'}), 400
        
        # Inserir novo usuário
        hashed_password = generate_password_hash(password)
        c.execute('INSERT INTO users (email, password, name, cpf_cnpj, role) VALUES (?, ?, ?, ?, ?)',
                  (email, hashed_password, name, cpf_cnpj, role))
        conn.commit()
        user_id = c.lastrowid
        conn.close()
        
        # Fazer login automaticamente
        session['user_id'] = user_id
        session['user_email'] = email
        session['user_name'] = name
        session['user_role'] = role
        
        return jsonify({'success': True, 'role': role})
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==== ROTAS DE PERFIL DO USUÁRIO ====
@app.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    """Obter dados do perfil do usuário logado"""
    conn = sqlite3.connect('credenciamento.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''SELECT id, email, name, cpf_cnpj, role, 
                 endereco, telefone, email_institucional, foto_perfil,
                 cidade, estado, cep, razao_social
                 FROM users WHERE id = ?''', (session['user_id'],))
    user = c.fetchone()
    conn.close()
    
    if user:
        return jsonify({
            'success': True,
            'profile': {
                'id': user['id'],
                'email': user['email'],
                'name': user['name'],
                'cpf_cnpj': user['cpf_cnpj'],
                'role': user['role'],
                'endereco': user['endereco'] or '',
                'telefone': user['telefone'] or '',
                'email_institucional': user['email_institucional'] or '',
                'foto_perfil': user['foto_perfil'] or '',
                'cidade': user['cidade'] or '',
                'estado': user['estado'] or '',
                'cep': user['cep'] or '',
                'razao_social': user['razao_social'] or ''
            }
        })
    return jsonify({'success': False, 'error': 'Usuário não encontrado'}), 404

@app.route('/api/profile', methods=['POST'])
@login_required
def update_profile():
    """Atualizar dados do perfil do usuário"""
    data = request.get_json()
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Atualizar campos do perfil
    c.execute('''UPDATE users SET 
                 name = ?,
                 endereco = ?,
                 telefone = ?,
                 email_institucional = ?,
                 cidade = ?,
                 estado = ?,
                 cep = ?,
                 razao_social = ?
                 WHERE id = ?''', (
        data.get('name', ''),
        data.get('endereco', ''),
        data.get('telefone', ''),
        data.get('email_institucional', ''),
        data.get('cidade', ''),
        data.get('estado', ''),
        data.get('cep', ''),
        data.get('razao_social', ''),
        session['user_id']
    ))
    
    conn.commit()
    conn.close()
    
    # Atualizar nome na sessão se foi alterado
    if data.get('name'):
        session['user_name'] = data.get('name')
    
    return jsonify({'success': True, 'message': 'Perfil atualizado com sucesso!'})

@app.route('/api/profile/photo', methods=['POST'])
@login_required
def upload_profile_photo():
    """Upload de foto de perfil"""
    if 'photo' not in request.files:
        return jsonify({'success': False, 'error': 'Nenhuma foto enviada'}), 400
    
    file = request.files['photo']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Nenhuma foto selecionada'}), 400
    
    # Verificar extensão
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in allowed_extensions:
        return jsonify({'success': False, 'error': 'Formato não permitido. Use: PNG, JPG, JPEG, GIF ou WEBP'}), 400
    
    # Criar diretório para fotos de perfil
    profile_photos_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'profile_photos')
    os.makedirs(profile_photos_dir, exist_ok=True)
    
    # Gerar nome único para o arquivo
    import uuid
    filename = f"profile_{session['user_id']}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(profile_photos_dir, filename)
    
    # Salvar arquivo
    file.save(filepath)
    
    # Atualizar banco de dados com o caminho relativo
    relative_path = f"uploads/profile_photos/{filename}"
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Obter foto antiga para deletar
    c.execute('SELECT foto_perfil FROM users WHERE id = ?', (session['user_id'],))
    old_photo = c.fetchone()
    if old_photo and old_photo[0]:
        old_path = os.path.join(os.path.dirname(__file__), old_photo[0])
        if os.path.exists(old_path):
            os.remove(old_path)
    
    c.execute('UPDATE users SET foto_perfil = ? WHERE id = ?', (relative_path, session['user_id']))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True, 
        'message': 'Foto atualizada com sucesso!',
        'photo_url': f'/{relative_path}'
    })

# ==== ROTAS ADMINISTRATIVAS ====
@app.route('/admin/home')
@login_required
def admin_home():
    """Painel administrativo"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    c.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],))
    role = c.fetchone()
    conn.close()
    
    if not role or role[0] != 'admin':
        return redirect(url_for('login'))
    
    return render_template('admin_home.html')

@app.route('/api/admin/stats')
@login_required
def admin_stats():
    """Estatísticas para o dashboard admin"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Total de processos
    c.execute("SELECT COUNT(*) FROM processes")
    total_processos = c.fetchone()[0]
    
    # Processos em análise
    c.execute("SELECT COUNT(*) FROM processes WHERE status = 'em_analise'")
    em_analise = c.fetchone()[0]
    
    # Processos aprovados
    c.execute("SELECT COUNT(*) FROM processes WHERE status = 'aprovado'")
    aprovados = c.fetchone()[0]
    
    # Processos devolvidos
    c.execute("SELECT COUNT(*) FROM processes WHERE status = 'devolvido'")
    devolvidos = c.fetchone()[0]
    
    # Total por categoria
    c.execute("SELECT COUNT(*) FROM processes WHERE credentialing_type = 'Gestor'")
    total_gestor = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM processes WHERE credentialing_type = 'Distribuidor'")
    total_distribuidor = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM processes WHERE credentialing_type = 'Administrador'")
    total_administrador = c.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'total_processos': total_processos,
        'em_analise': em_analise,
        'aprovados': aprovados,
        'devolvidos': devolvidos,
        'total_gestor': total_gestor,
        'total_distribuidor': total_distribuidor,
        'total_administrador': total_administrador
    })

@app.route('/admin/category/<categoria>')
@login_required
def admin_category(categoria):
    """Visualizar processos por categoria"""
    # Verificar se é admin
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    c.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],))
    role = c.fetchone()
    
    if not role or role[0] != 'admin':
        conn.close()
        return redirect(url_for('login'))
    
    # Mapear categoria para nome e descrição
    categorias = {
        'gestor': {
            'nome': 'Gestor',
            'descricao': 'Processos de Gestão de Recursos'
        },
        'distribuidor': {
            'nome': 'Distribuidor',
            'descricao': 'Processos de Distribuição de Valores'
        },
        'administrador': {
            'nome': 'Administrador',
            'descricao': 'Processos de Administração e Custódia'
        }
    }
    
    if categoria not in categorias:
        conn.close()
        return "Categoria inválida", 404
    
    categoria_info = categorias[categoria]
    
    # Buscar processos da categoria
    c.execute('''
        SELECT 
            p.id,
            p.custom_id,
            p.institution_name,
            p.credentialing_type,
            p.status,
            p.created_at,
            COUNT(d.id) as document_count
        FROM processes p
        LEFT JOIN documents d ON d.process_id = p.id
        WHERE p.credentialing_type = ?
        GROUP BY p.id
        ORDER BY p.created_at DESC
    ''', (categoria_info['nome'],))
    
    processos = []
    for row in c.fetchall():
        processos.append({
            'id': row[0],
            'custom_id': row[1],
            'institution_name': row[2],
            'credentialing_type': row[3],
            'status': row[4],
            'created_at': datetime.fromisoformat(row[5]).strftime('%d/%m/%Y') if row[5] else '-',
            'document_count': row[6]
        })
    
    # Estatísticas da categoria
    c.execute("SELECT COUNT(*) FROM processes WHERE credentialing_type = ?", (categoria_info['nome'],))
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM processes WHERE credentialing_type = ? AND status = 'em_analise'", (categoria_info['nome'],))
    em_analise = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM processes WHERE credentialing_type = ? AND status = 'aprovado'", (categoria_info['nome'],))
    aprovados = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM processes WHERE credentialing_type = ? AND status = 'devolvido'", (categoria_info['nome'],))
    devolvidos = c.fetchone()[0]
    
    conn.close()
    
    stats = {
        'total': total,
        'em_analise': em_analise,
        'aprovados': aprovados,
        'devolvidos': devolvidos
    }
    
    return render_template('admin_category.html',
                         categoria_nome=categoria_info['nome'],
                         categoria_descricao=categoria_info['descricao'],
                         processos=processos,
                         stats=stats)

@app.route('/api/admin/organizations')
@login_required
def admin_get_organizations():
    """Lista todas as organizações"""
    conn = sqlite3.connect('credenciamento.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute('''
        SELECT o.*, u.email
        FROM organizations o
        LEFT JOIN users u ON u.organization_id = o.id
        GROUP BY o.id
        ORDER BY o.created_at DESC
    ''')
    
    orgs = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return jsonify(orgs)

@app.route('/api/admin/organizations', methods=['POST'])
@login_required
def admin_create_organization():
    """Cria nova organização e usuário"""
    data = request.json
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    try:
        # Criar organização
        c.execute('''
            INSERT INTO organizations (name, cnpj, phone, organization_type, status, created_at)
            VALUES (?, ?, ?, ?, 'active', ?)
        ''', (
            data['name'],
            data['cnpj'],
            data.get('phone', ''),
            data['org_type'],
            datetime.now().isoformat()
        ))
        
        org_id = c.lastrowid
        
        # Criar usuário
        role = 'rpps' if data['org_type'] == 'rpps' else 'financial'
        c.execute('''
            INSERT INTO users (name, email, password, cpf_cnpj, role, organization_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['user_name'],
            data['email'],
            data['password'],
            data['user_cpf'],
            role,
            org_id,
            datetime.now().isoformat()
        ))
        
        # Criar assinatura
        start_date = datetime.now()
        end_date = start_date.replace(year=start_date.year + 1)
        
        c.execute('''
            INSERT INTO subscriptions (
                organization_id, plan_type, annual_value,
                start_date, end_date, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, 'active', ?)
        ''', (
            org_id,
            'standard',
            float(data['annual_fee']),
            start_date.isoformat(),
            end_date.isoformat(),
            datetime.now().isoformat()
        ))
        
        # Log de auditoria
        c.execute('''
            INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details, created_at)
            VALUES (?, 'CREATE', 'organization', ?, ?, ?)
        ''', (
            session['user_id'],
            org_id,
            f'Criada organização: {data["name"]}',
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'organization_id': org_id})
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/subscriptions')
@login_required
def admin_get_subscriptions():
    """Lista todas as assinaturas"""
    conn = sqlite3.connect('credenciamento.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute('''
        SELECT s.*, o.name as organization_name
        FROM subscriptions s
        JOIN organizations o ON o.id = s.organization_id
        ORDER BY s.created_at DESC
    ''')
    
    subs = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return jsonify(subs)

@app.route('/api/admin/settings')
@login_required
def admin_get_settings():
    """Lista configurações do sistema"""
    conn = sqlite3.connect('credenciamento.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute('SELECT * FROM system_settings ORDER BY setting_key')
    settings = [dict(row) for row in c.fetchall()]
    
    conn.close()
    return jsonify(settings)

@app.route('/api/user/info')
@login_required
def user_info():
    """Retorna informações do usuário logado"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    c.execute('SELECT name, email, role FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    conn.close()
    
    if user:
        return jsonify({
            'name': user[0],
            'email': user[1],
            'role': user[2]
        })
    return jsonify({'error': 'Usuário não encontrado'}), 404

# Rotas da Instituição Financeira
@app.route('/financial/home')
@login_required
@role_required('financial_institution')
def financial_home():
    return render_template('financial_home_final.html')

@app.route('/api/financial/processes')
@login_required
@role_required('financial_institution')
def get_financial_processes():
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    c.execute('''SELECT p.*, 
                        (SELECT COUNT(*) FROM documents WHERE process_id = p.id) as doc_count
                 FROM processes p 
                 WHERE p.financial_institution_id = ? AND p.is_archived = 0
                 ORDER BY p.created_at DESC''', (session['user_id'],))
    
    processes = []
    for row in c.fetchall():
        processes.append({
            'id': row[0],
            'custom_id': row[1],  # posição 1
            'financial_institution_id': row[2],
            'financial_institution_name': row[3],
            'financial_institution_cnpj': row[4],
            'rpps_id': row[5],
            'rpps_name': row[6],
            'credentialing_type': row[7],
            'status': row[8],
            'created_at': row[9],
            'updated_at': row[10],
            'document_count': row[18]  # doc_count é a última coluna após todas as 18 colunas da tabela
        })
    
    conn.close()
    return jsonify(processes)

@app.route('/financial/new-process')
@login_required
@role_required('financial_institution')
def financial_new_process():
    return render_template('financial_new_process.html')

@app.route('/api/financial/list-rpps')
@login_required
@role_required('financial_institution')
def list_rpps():
    """Lista todos os RPPS cadastrados no sistema para a IF escolher"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Buscar todos os RPPS (usuários com role='rpps' e que são entity_id=NULL ou são o próprio entity)
    c.execute('''
        SELECT DISTINCT u.id, u.name, u.cpf_cnpj 
        FROM users u 
        WHERE u.role = 'rpps' 
        AND (u.entity_id IS NULL OR u.entity_id = u.id)
        ORDER BY u.name
    ''')
    rpps_list = c.fetchall()
    conn.close()
    
    return jsonify([
        {'id': r[0], 'name': r[1], 'cnpj': r[2] or ''}
        for r in rpps_list
    ])

@app.route('/api/financial/create-process', methods=['POST'])
@login_required
@role_required('financial_institution')
def create_process():
    data = request.json
    credentialing_type = data.get('credentialing_type')
    rpps_id = data.get('rpps_id')  # Agora recebe o RPPS selecionado
    
    if not rpps_id:
        return jsonify({'error': 'Selecione um RPPS'}), 400
    
    # Obter informações do usuário
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    c.execute('SELECT name, cpf_cnpj FROM users WHERE id = ?', (session['user_id'],))
    user_info = c.fetchone()
    
    # Obter RPPS selecionado
    c.execute('SELECT id, name FROM users WHERE id = ? AND role = "rpps"', (rpps_id,))
    rpps_info = c.fetchone()
    
    if not rpps_info:
        conn.close()
        return jsonify({'error': 'RPPS não encontrado'}), 404
    
    # Gerar ID customizado
    custom_id = generate_custom_id(user_info[0], credentialing_type)
    
    # Criar processo
    c.execute('''INSERT INTO processes 
                 (financial_institution_id, financial_institution_name, financial_institution_cnpj,
                  rpps_id, rpps_name, credentialing_type, status, custom_id)
                 VALUES (?, ?, ?, ?, ?, ?, 'draft', ?)''',
              (session['user_id'], user_info[0], user_info[1], rpps_info[0], rpps_info[1], 
               credentialing_type, custom_id))
    
    process_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'process_id': process_id, 'custom_id': custom_id})

@app.route('/financial/process/<int:process_id>')
@login_required
@role_required('financial_institution')
def financial_process_detail(process_id):
    return render_template('financial_process_detail.html', process_id=process_id)

@app.route('/api/financial/process/<int:process_id>')
@login_required
def get_process_detail(process_id):
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Obter processo
    c.execute('SELECT * FROM processes WHERE id = ?', (process_id,))
    process_row = c.fetchone()
    
    if not process_row:
        conn.close()
        return jsonify({'error': 'Processo não encontrado'}), 404
    
    # Obter documentos
    c.execute('SELECT * FROM documents WHERE process_id = ?', (process_id,))
    docs = c.fetchall()
    
    documents = []
    for doc in docs:
        analysis = json.loads(doc[9]) if doc[9] else None
        documents.append({
            'id': doc[0],
            'type': doc[2],
            'name': doc[3],
            'filename': doc[4],
            'mime_type': doc[5],
            'uploaded_at': doc[6],
            'status': doc[8],
            'analysis': analysis
        })
    
    process = {
        'id': process_row[0],
        'custom_id': process_row[1],
        'financial_institution_name': process_row[3],
        'rpps_name': process_row[6],
        'credentialing_type': process_row[7],
        'status': process_row[8],
        'created_at': process_row[9],
        'submitted_at': process_row[11],
        'documents': documents,
        'final_review_note': process_row[13],
        'final_decision': process_row[14]
    }
    
    conn.close()
    return jsonify(process)

@app.route('/api/upload-document/<int:process_id>', methods=['POST'])
@login_required
def upload_document(process_id):
    """Upload RÁPIDO - Análise de IA roda em background"""
    print(f"\n🔵 UPLOAD INICIADO - Processo #{process_id}")
    
    # Aceitar tanto 'file' quanto 'document_file'
    file = request.files.get('file') or request.files.get('document_file')
    
    if not file:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    
    document_type = request.form.get('type') or request.form.get('document_type')
    
    if not document_type or document_type == '':
        return jsonify({'error': 'Tipo de documento não informado'}), 400
    
    # Mapeamento de nomes amigáveis para os tipos
    document_names = {
        'apresentacao_institucional': 'Apresentação Institucional',
        'checklist': 'Checklist de Credenciamento',
        'cadprev': 'CadPrev Atualizado',
        'termo_credenciamento': 'Termo de Credenciamento',
        'termo_declaracao': 'Termo de Declaração',
        'declaracao_unificada': 'Declaração Unificada',
        'qdd_anbima': 'QDD Anbima Seção I',
        'formulario_referencia_cvm': 'Formulário de Referência CVM',
        'certidao_bacen_autorizacao': 'Certidão - Autorização a Funcionar BACEN',
        'certidao_bacen_nada_consta': 'Certidão Nada Consta do BACEN',
        'certidao_anbima': 'Certidão de Adesão aos Códigos ANBIMA',
        'lista_exaustiva_cmn': 'Lista Exaustiva (Art. 15 Resolução CMN)',
        'rating': 'Rating de Qualidade de Gestão',
        'contrato_distribuicao': 'Contrato de Distribuição',
        'situacao_ancord': 'Situação ANCORD (AAI)',
        'certidao_municipal': 'Certidão Municipal',
        'certidao_estadual': 'Certidão Estadual',
        'certidao_federal': 'Certidão Federal',
        'certidao_trabalhista': 'Certidão Trabalhista',
        'certidao_fgts': 'Certidão FGTS'
    }
    
    document_name = document_names.get(document_type, document_type)
    requires_signature_raw = request.form.get('requires_signature', 'false')
    # Converter string para booleano corretamente
    requires_signature = requires_signature_raw.lower() in ['true', 'on', '1', 'yes']
    
    print(f"📄 Tipo: {document_type}")
    print(f"📝 Nome: {document_name}")
    print(f"🔐 Requer assinatura RAW: '{requires_signature_raw}' (type: {type(requires_signature_raw).__name__})")
    print(f"🔐 Requer assinatura PROCESSADO: {requires_signature}")
    
    if file.filename == '':
        return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
    
    # Salvar arquivo
    filename = secure_filename(f"{process_id}_{document_type}_{file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    print(f"💾 Arquivo salvo: {filename}")
    
    # Salvar no banco COM STATUS "analyzing" (em análise)
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Análise inicial vazia
    initial_analysis = {
        'status': 'analyzing',
        'uploaded_at': datetime.now().isoformat(),
        'requires_signature': requires_signature
    }
    
    c.execute('''INSERT INTO documents 
                 (process_id, type, name, filename, mime_type, uploaded_by, status, analysis_data)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (process_id, document_type, document_name, filename, file.content_type, 
               session['user_id'], 'analyzing', json.dumps(initial_analysis)))
    
    doc_id = c.lastrowid
    
    # Atualizar processo
    c.execute('UPDATE processes SET updated_at = CURRENT_TIMESTAMP WHERE id = ?', (process_id,))
    
    # Obter informações da instituição do processo
    c.execute('SELECT financial_institution_name, financial_institution_cnpj FROM processes WHERE id = ?', (process_id,))
    process_info = c.fetchone()
    
    conn.commit()
    
    # Se for Termo de Credenciamento, criar também entrada em special_documents
    if document_type == 'termo_credenciamento':
        c.execute('''INSERT INTO special_documents 
                     (process_id, document_type, version, status, filename, original_filename, 
                      mime_type, uploaded_by, uploaded_by_role, notes)
                     VALUES (?, ?, 1, 'excel_if', ?, ?, ?, ?, 'financial_institution', 'Versão Excel original enviada pela IF')''',
                  (process_id, 'termo_credenciamento', filename, file.filename,
                   file.content_type, session['user_id']))
        conn.commit()
    
    conn.close()
    
    # Registrar no histórico
    log_process_history(process_id, 'Documento enviado', document_name)
    
    institution_name = process_info[0] if process_info else None
    institution_cnpj = process_info[1] if process_info else None
    
    # 🚀 INICIAR ANÁLISE EM BACKGROUND (não bloqueia o upload)
    def analyze_in_background():
        """Função que roda em thread separada para analisar com IA"""
        try:
            print(f"🤖 [BACKGROUND] Iniciando análise IA para documento #{doc_id}...")
            print(f"   Tipo: {document_type} | Arquivo: {document_name}")
            print(f"   Instituição: {institution_name} | CNPJ: {institution_cnpj}")
            
            # ANÁLISE DE IA RIGOROSA
            ai_result = analyze_document_rigorous(
                filepath, 
                document_type, 
                document_name,
                institution_name,
                institution_cnpj
            )
            
            print(f"📊 [BACKGROUND] Resultado da análise IA:")
            print(f"   Score: {ai_result.get('score', 0)}/100")
            print(f"   Válido: {ai_result.get('is_valid', False)}")
            print(f"   Issues: {ai_result.get('issues', [])}")
            
            # Atualizar banco com resultado
            conn_bg = sqlite3.connect('credenciamento.db')
            c_bg = conn_bg.cursor()
            
            # Preparar dados da análise
            analysis_data = {
                'status': 'analyzed',
                'analyzed_at': datetime.now().isoformat(),
                'uploaded_at': initial_analysis['uploaded_at'],
                'requires_signature': requires_signature,
                'ai_content_analysis': ai_result,
                'signature_validated': False
            }
            
            # Determinar status baseado na análise
            content_ok = ai_result.get('is_valid', False)
            
            # ========== VALIDAÇÃO TCEES (SE REQUER ASSINATURA) ==========
            tcees_result = None
            if requires_signature:
                print(f"🔐 [BACKGROUND] Documento requer assinatura - validando com TCEES...")
                try:
                    tcees_result = validate_pdf_with_tcees(filepath)
                    analysis_data['tcees_validation'] = tcees_result
                    
                    # Verificar se passou na validação TCEES
                    tcees_passed = (
                        tcees_result.get('assinado', False) and
                        tcees_result.get('autenticidade_ok', False) and
                        tcees_result.get('integridade_ok', False) and
                        tcees_result.get('resultado_final', '') == 'VALIDADO'
                    )
                    
                    analysis_data['signature_validated'] = True
                    analysis_data['tcees_passed'] = tcees_passed
                    
                    print(f"📋 [BACKGROUND] TCEES Result: {tcees_result.get('resultado_final', 'N/A')}")
                    print(f"   Assinado: {tcees_result.get('assinado', False)}")
                    print(f"   Autenticidade: {tcees_result.get('autenticidade_ok', False)}")
                    print(f"   Integridade: {tcees_result.get('integridade_ok', False)}")
                    print(f"   Pontuação: {tcees_result.get('pontuacao', 0)}/100")
                    
                except Exception as tcees_error:
                    print(f"⚠️ [BACKGROUND] Erro na validação TCEES: {str(tcees_error)}")
                    import traceback
                    traceback.print_exc()
                    analysis_data['tcees_validation'] = {
                        'resultado_final': 'ERRO',
                        'erros': [f'Erro ao validar assinatura: {str(tcees_error)[:200]}']
                    }
                    analysis_data['signature_validated'] = True
                    analysis_data['tcees_passed'] = False
                    tcees_result = analysis_data['tcees_validation']  # Garantir que tcees_result está definido
            
            # Determinar status final
            if not content_ok:
                final_status = 'rejected'
                analysis_data['rejection_summary'] = ' | '.join(ai_result.get('issues', ['Documento reprovado']))
            elif requires_signature:
                # Se requer assinatura, verificar resultado TCEES
                if tcees_result and analysis_data.get('tcees_passed', False):
                    final_status = 'approved'
                    analysis_data['approval_summary'] = 'Documento aprovado - Conteúdo e assinatura digital válidos'
                else:
                    final_status = 'rejected'
                    tcees_msg = tcees_result.get('resultado_final', 'N/A') if tcees_result else 'Não validado'
                    analysis_data['rejection_summary'] = f'Assinatura digital: {tcees_msg}'
            else:
                final_status = 'approved'
                analysis_data['approval_summary'] = 'Documento aprovado'
            
            analysis_data['final_verdict'] = final_status
            analysis_data['content_ok'] = content_ok
            
            print(f"💾 [BACKGROUND] Atualizando banco de dados...")
            print(f"   Status final: {final_status}")
            
            # Atualizar documento
            c_bg.execute('''UPDATE documents 
                           SET status = ?, analysis_data = ?
                           WHERE id = ?''',
                        (final_status, json.dumps(analysis_data), doc_id))
            
            rows_updated = c_bg.rowcount
            conn_bg.commit()
            conn_bg.close()
            
            print(f"✅ [BACKGROUND] Análise concluída para documento #{doc_id} (rows_updated: {rows_updated})")
            print(f"   Score: {ai_result.get('score', 0)}/100 | Status: {final_status}")
        
        except Exception as e:
            print(f"❌ [BACKGROUND] ERRO na análise do documento #{doc_id}: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # Iniciar thread de análise
    thread = threading.Thread(target=analyze_in_background, daemon=True)
    thread.start()
    
    # ⚡ RETORNO IMEDIATO - Upload concluído, análise rodando em background
    return jsonify({
        'success': True,
        'document_id': doc_id,
        'status': 'analyzing',
        'message': '✅ Documento enviado! A análise com IA está sendo processada...',
        'analyzing': True
    })

@app.route('/api/delete-document/<int:document_id>', methods=['DELETE'])
@login_required
def delete_document(document_id):
    """Exclui um documento enviado erroneamente"""
    print(f"\n🗑️ DELETE DOCUMENTO - ID #{document_id}")
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Buscar documento e verificar permissão
    c.execute('''SELECT d.id, d.filename, d.process_id, p.financial_institution_id, p.rpps_id 
                 FROM documents d
                 JOIN processes p ON d.process_id = p.id
                 WHERE d.id = ?''', (document_id,))
    doc = c.fetchone()
    
    if not doc:
        conn.close()
        return jsonify({'error': 'Documento não encontrado'}), 404
    
    doc_id, filename, process_id, financial_institution_id, rpps_id = doc
    
    # Verificar se o usuário tem permissão (dono do processo: IF ou RPPS, ou admin/financeiro)
    user_role = session.get('user_role', '')
    user_id = session.get('user_id')
    
    # Permitir se for admin, financial, a IF dona ou o RPPS do processo
    has_permission = (
        user_role in ['admin', 'financial'] or 
        user_id == financial_institution_id or 
        user_id == rpps_id
    )
    
    if not has_permission:
        conn.close()
        return jsonify({'error': 'Sem permissão para excluir este documento'}), 403
    
    # Deletar arquivo físico se existir
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            print(f"🗂️ Arquivo removido: {filename}")
        except Exception as e:
            print(f"⚠️ Erro ao remover arquivo: {e}")
    
    # Deletar do banco de dados
    c.execute('DELETE FROM documents WHERE id = ?', (document_id,))
    conn.commit()
    conn.close()
    
    print(f"✅ Documento #{document_id} excluído com sucesso")
    
    return jsonify({
        'success': True,
        'message': 'Documento excluído com sucesso'
    })

@app.route('/api/validate-signature/<int:document_id>', methods=['POST'])
@login_required
def validate_document_signature(document_id):
    """Valida assinatura digital de um documento usando TCEES"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Buscar documento
    c.execute('SELECT filename, analysis_data FROM documents WHERE id = ?', (document_id,))
    doc = c.fetchone()
    
    if not doc:
        conn.close()
        return jsonify({'error': 'Documento não encontrado'}), 404
    
    filename, analysis_json = doc
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if not os.path.exists(filepath):
        conn.close()
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    
    # Executar validação TCEES
    print(f"🔐 Validando assinatura do documento {document_id} via TCEES...")
    signature_validation = validate_signature_tcees(filepath)
    
    # Atualizar analysis_data
    analysis_data = json.loads(analysis_json) if analysis_json else {}
    analysis_data['signature_validation'] = signature_validation
    analysis_data['signature_validated'] = True
    analysis_data['signature_validated_at'] = datetime.now().isoformat()
    
    # Determinar novo status
    signature_ok = signature_validation.get('is_valid', False)
    content_ok = analysis_data.get('content_ok', False)
    
    if content_ok and signature_ok:
        new_status = 'approved'
        analysis_data['approval_summary'] = 'Documento aprovado em todas as verificações'
    elif not signature_ok:
        new_status = 'rejected'
        analysis_data['rejection_summary'] = 'Validação de assinatura digital falhou'
    else:
        new_status = 'pending'
    
    # Atualizar banco
    c.execute('UPDATE documents SET status = ?, analysis_data = ? WHERE id = ?',
              (new_status, json.dumps(analysis_data), document_id))
    conn.commit()
    conn.close()
    
    print(f"✅ Validação concluída: {signature_validation.get('resultado_final', 'ERRO')}")
    
    return jsonify({
        'success': True,
        'signature_valid': signature_ok,
        'new_status': new_status,
        'validation_details': signature_validation
    })

@app.route('/api/validar-assinatura', methods=['POST'])
@login_required
def validar_assinatura_rapida():
    """Endpoint para validação rápida de assinatura de PDF via modal"""
    try:
        # Verificar se arquivo foi enviado
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'Nenhum arquivo foi enviado'
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'Nenhum arquivo selecionado'
            }), 400
        
        # Validar tipo de arquivo
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({
                'success': False,
                'error': 'Apenas arquivos PDF são aceitos'
            }), 400
        
        # Salvar arquivo temporariamente
        filename = secure_filename(file.filename)
        temp_filename = f"temp_validador_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
        temp_filepath = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
        file.save(temp_filepath)
        
        try:
            # Executar validação TCEES
            print(f"🔐 Validando assinatura rápida do arquivo: {filename}")
            resultado_tcees = validate_pdf_with_tcees(temp_filepath)
            
            # Log do resultado para debug
            print(f"📊 Resultado TCEES recebido: {type(resultado_tcees)}")
            if resultado_tcees:
                print(f"   Chaves disponíveis: {list(resultado_tcees.keys())}")
            
            # Garantir que temos um dicionário válido
            if not resultado_tcees or not isinstance(resultado_tcees, dict):
                print("⚠️ TCEES retornou dados inválidos, usando estrutura padrão")
                resultado_tcees = {}
            
            # Converter formato TCEES para formato esperado pelo frontend
            # O TCEES retorna estrutura diferente, vamos adaptar
            numero_assinaturas = int(resultado_tcees.get('numero_assinaturas', 0))
            autenticidade_ok = bool(resultado_tcees.get('autenticidade_ok', False))
            integridade_ok = bool(resultado_tcees.get('integridade_ok', False))
            
            print(f"   Número de assinaturas: {numero_assinaturas}")
            print(f"   Autenticidade OK: {autenticidade_ok}")
            print(f"   Integridade OK: {integridade_ok}")
            
            # Determinar quantas assinaturas são válidas
            if numero_assinaturas > 0 and autenticidade_ok and integridade_ok:
                assinaturas_validas = numero_assinaturas
                assinaturas_invalidas = 0
            elif numero_assinaturas > 0 and (not autenticidade_ok or not integridade_ok):
                assinaturas_validas = 0
                assinaturas_invalidas = numero_assinaturas
            else:
                assinaturas_validas = 0
                assinaturas_invalidas = 0
            
            # Criar array de assinaturas com detalhes
            assinaturas = []
            if numero_assinaturas > 0:
                status = 'Válida' if (autenticidade_ok and integridade_ok) else 'Inválida'
                for i in range(numero_assinaturas):
                    assinatura = {
                        'assinante': resultado_tcees.get('titular_certificado', 'Não informado'),
                        'emissor': resultado_tcees.get('emissor_certificado', 'Não informado'),
                        'data_assinatura': resultado_tcees.get('validade_certificado', 'Não informada'),
                        'status': status
                    }
                    assinaturas.append(assinatura)
            
            # Formato esperado pelo frontend
            resultado = {
                'assinaturas_validas': assinaturas_validas,
                'assinaturas_invalidas': assinaturas_invalidas,
                'total_assinaturas': numero_assinaturas,
                'assinaturas': assinaturas,
                # Dados completos do TCEES para exibir tabela de conformidade
                'detalhes_tcees': {
                    'extensao_valida': resultado_tcees.get('extensao_valida', False),
                    'sem_senha': resultado_tcees.get('sem_senha', False),
                    'tamanho_arquivo_ok': resultado_tcees.get('tamanho_arquivo_ok', False),
                    'tamanho_pagina_ok': resultado_tcees.get('tamanho_pagina_ok', False),
                    'assinado': resultado_tcees.get('assinado', False),
                    'autenticidade_ok': resultado_tcees.get('autenticidade_ok', False),
                    'integridade_ok': resultado_tcees.get('integridade_ok', False),
                    'pesquisavel': resultado_tcees.get('pesquisavel', False),
                    'resultado_final': resultado_tcees.get('resultado_final', 'NÃO VALIDADO'),
                    'pontuacao': resultado_tcees.get('pontuacao', 0)
                }
            }
            
            print(f"✅ Resultado formatado: {resultado}")
            
            # Remover arquivo temporário
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
            
            return jsonify({
                'success': True,
                'resultado': resultado
            })
            
        except Exception as validation_error:
            # Remover arquivo temporário em caso de erro
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
            
            print(f"❌ Erro na validação TCEES: {str(validation_error)}")
            import traceback
            traceback.print_exc()
            return jsonify({
                'success': False,
                'error': f'Erro ao validar documento: {str(validation_error)}'
            }), 500
            
    except Exception as e:
        print(f"❌ Erro no endpoint de validação rápida: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Erro no servidor: {str(e)}'
        }), 500

@app.route('/api/validar-assinaturas-multiplas', methods=['POST'])
@login_required
def validar_assinaturas_multiplas():
    """Endpoint para validação de múltiplos PDFs em paralelo (até 3)"""
    try:
        # Verificar se arquivos foram enviados
        if 'files[]' not in request.files:
            return jsonify({
                'success': False,
                'error': 'Nenhum arquivo foi enviado'
            }), 400
        
        files = request.files.getlist('files[]')
        
        if not files or len(files) == 0:
            return jsonify({
                'success': False,
                'error': 'Nenhum arquivo selecionado'
            }), 400
        
        # Limitar a 3 arquivos
        if len(files) > 3:
            return jsonify({
                'success': False,
                'error': 'Máximo de 3 arquivos permitidos'
            }), 400
        
        # Validar tipos e salvar arquivos temporários
        temp_files = []
        nomes_originais = {}  # Mapeia path temporário -> nome original
        for file in files:
            if not file.filename.lower().endswith('.pdf'):
                # Limpar arquivos temporários já salvos
                for tf in temp_files:
                    if os.path.exists(tf):
                        os.remove(tf)
                return jsonify({
                    'success': False,
                    'error': f'Arquivo {file.filename} não é PDF'
                }), 400
            
            nome_original = file.filename  # Guardar nome original
            filename = secure_filename(file.filename)
            temp_filename = f"temp_multi_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
            temp_filepath = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
            file.save(temp_filepath)
            temp_files.append(temp_filepath)
            nomes_originais[temp_filepath] = nome_original  # Mapear
        
        try:
            print(f"🔐 Validando {len(temp_files)} arquivo(s) em paralelo...")
            
            # Executar validação em paralelo
            resultados_tcees = validate_multiple_pdfs(temp_files)
            
            # Formatar resultados para o frontend
            resultados = []
            for i, resultado_tcees in enumerate(resultados_tcees):
                numero_assinaturas = int(resultado_tcees.get('numero_assinaturas', 0))
                autenticidade_ok = bool(resultado_tcees.get('autenticidade_ok', False))
                integridade_ok = bool(resultado_tcees.get('integridade_ok', False))
                
                if numero_assinaturas > 0 and autenticidade_ok and integridade_ok:
                    assinaturas_validas = numero_assinaturas
                    assinaturas_invalidas = 0
                elif numero_assinaturas > 0:
                    assinaturas_validas = 0
                    assinaturas_invalidas = numero_assinaturas
                else:
                    assinaturas_validas = 0
                    assinaturas_invalidas = 0
                
                # Usar nome original ao invés do nome do arquivo temporário
                nome_temp = resultado_tcees.get('nome_arquivo', '')
                nome_original = nomes_originais.get(temp_files[i], nome_temp) if i < len(temp_files) else nome_temp
                
                resultado = {
                    'nome_arquivo': nome_original,
                    'assinaturas_validas': assinaturas_validas,
                    'assinaturas_invalidas': assinaturas_invalidas,
                    'total_assinaturas': numero_assinaturas,
                    'detalhes_tcees': {
                        'extensao_valida': resultado_tcees.get('extensao_valida', False),
                        'sem_senha': resultado_tcees.get('sem_senha', False),
                        'tamanho_arquivo_ok': resultado_tcees.get('tamanho_arquivo_ok', False),
                        'tamanho_pagina_ok': resultado_tcees.get('tamanho_pagina_ok', False),
                        'assinado': resultado_tcees.get('assinado', False),
                        'autenticidade_ok': resultado_tcees.get('autenticidade_ok', False),
                        'integridade_ok': resultado_tcees.get('integridade_ok', False),
                        'pesquisavel': resultado_tcees.get('pesquisavel', False),
                        'resultado_final': resultado_tcees.get('resultado_final', 'NÃO VALIDADO'),
                        'pontuacao': resultado_tcees.get('pontuacao', 0)
                    }
                }
                resultados.append(resultado)
            
            # Limpar arquivos temporários
            for tf in temp_files:
                if os.path.exists(tf):
                    os.remove(tf)
            
            return jsonify({
                'success': True,
                'resultados': resultados,
                'total_arquivos': len(resultados)
            })
            
        except Exception as validation_error:
            # Limpar arquivos temporários
            for tf in temp_files:
                if os.path.exists(tf):
                    os.remove(tf)
            
            print(f"❌ Erro na validação múltipla: {str(validation_error)}")
            import traceback
            traceback.print_exc()
            return jsonify({
                'success': False,
                'error': f'Erro ao validar documentos: {str(validation_error)}'
            }), 500
            
    except Exception as e:
        print(f"❌ Erro no endpoint de validação múltipla: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Erro no servidor: {str(e)}'
        }), 500


@app.route('/api/submit-process/<int:process_id>', methods=['POST'])
@login_required
@role_required('financial_institution')
def submit_process(process_id):
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    c.execute('''UPDATE processes 
                 SET status = 'submitted', submitted_at = CURRENT_TIMESTAMP 
                 WHERE id = ?''', (process_id,))
    conn.commit()
    conn.close()
    
    # Registrar no histórico
    log_process_history(process_id, 'Processo enviado ao RPPS', 'Documentos submetidos para análise')
    
    return jsonify({'success': True})

# Rotas do RPPS
@app.route('/rpps/home')
@login_required
@role_required('rpps')
def rpps_home():
    return render_template('rpps_home_final.html')

@app.route('/api/rpps/processes')
@login_required
@role_required('rpps')
def get_rpps_processes():
    show_archived = request.args.get('archived', 'false') == 'true'
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    archived_filter = 1 if show_archived else 0
    c.execute('''SELECT p.*,
                        (SELECT COUNT(*) FROM documents WHERE process_id = p.id) as doc_count
                 FROM processes p 
                 WHERE p.rpps_id = ? AND p.is_archived = ? AND p.status != 'draft'
                 ORDER BY p.created_at DESC''', (session['user_id'], archived_filter))
    
    processes = []
    for row in c.fetchall():
        processes.append({
            'id': row[0],
            'custom_id': row[1],  # posição 1
            'financial_institution_id': row[2],
            'financial_institution_name': row[3],
            'financial_institution_cnpj': row[4],
            'rpps_id': row[5],
            'rpps_name': row[6],
            'credentialing_type': row[7],
            'status': row[8],
            'created_at': row[9],
            'updated_at': row[10],
            'document_count': row[18],  # doc_count é a última coluna após todas as 18 colunas da tabela
            'final_decision': row[14]
        })
    
    conn.close()
    return jsonify(processes)

@app.route('/rpps/process/<int:process_id>')
@login_required
@role_required('rpps')
def rpps_process_detail(process_id):
    return render_template('rpps_process_detail.html', process_id=process_id)

@app.route('/api/rpps/review-process/<int:process_id>', methods=['POST'])
@login_required
@role_required('rpps')
def review_process(process_id):
    data = request.json
    decision = data.get('decision')  # 'approved' or 'rejected'
    note = data.get('note', '')
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    new_status = 'approved' if decision == 'approved' else 'rejected'
    
    c.execute('''UPDATE processes 
                 SET status = ?, 
                     final_decision = ?,
                     final_review_note = ?,
                     final_decision_at = CURRENT_TIMESTAMP,
                     final_decision_by = ?,
                     reviewed_at = CURRENT_TIMESTAMP
                 WHERE id = ?''',
              (new_status, decision, note, session['user_id'], process_id))
    
    conn.commit()
    conn.close()
    
    # Registrar no histórico
    if decision == 'approved':
        log_process_history(process_id, 'Processo aprovado', note if note else 'Credenciamento aprovado pelo RPPS')
    else:
        log_process_history(process_id, 'Processo rejeitado', note if note else 'Credenciamento recusado pelo RPPS')
    
    return jsonify({'success': True})

@app.route('/api/rpps/archive-process/<int:process_id>', methods=['POST'])
@login_required
@role_required('rpps')
def archive_process(process_id):
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    c.execute('UPDATE processes SET is_archived = 1 WHERE id = ?', (process_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/rpps/restore-process/<int:process_id>', methods=['POST'])
@login_required
@role_required('rpps')
def restore_process(process_id):
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    c.execute('UPDATE processes SET is_archived = 0 WHERE id = ?', (process_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/rpps/delete-process/<int:process_id>', methods=['DELETE'])
@login_required
@role_required('rpps')
def rpps_delete_process(process_id):
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Deletar documentos físicos
    c.execute('SELECT filename FROM documents WHERE process_id = ?', (process_id,))
    for (filename,) in c.fetchall():
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)
    
    # Deletar do banco
    c.execute('DELETE FROM documents WHERE process_id = ?', (process_id,))
    c.execute('DELETE FROM processes WHERE id = ?', (process_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# Rota para download de documentos
@app.route('/uploads/<filename>')
@login_required
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Rota para servir fotos de perfil
@app.route('/uploads/profile_photos/<filename>')
@login_required
def serve_profile_photo(filename):
    profile_photos_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'profile_photos')
    return send_from_directory(profile_photos_dir, filename)

# ==================== ROTAS ADMINISTRATIVAS - GERENCIAR USUÁRIOS ====================

@app.route('/admin/users')
@login_required
@role_required('admin')
def admin_users_page():
    return render_template('admin_users.html')

@app.route('/api/admin/entities')
@login_required
@role_required('admin')
def get_entities():
    """Lista todas as entidades (RPPS e Instituições Financeiras)"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Buscar todas as entidades (usuários únicos por role)
    c.execute('''
        SELECT DISTINCT u.id, u.name, u.role, u.cpf_cnpj, u.email,
               (SELECT COUNT(*) FROM users u2 WHERE u2.entity_id = u.id) as user_count,
               u.foto_perfil, u.telefone, u.endereco, u.cidade, u.estado, u.razao_social, u.email_institucional, u.cep
        FROM users u
        WHERE u.role IN ('financial', 'rpps')
        ORDER BY u.name
    ''')
    
    entities = []
    for row in c.fetchall():
        entities.append({
            'id': row[0],
            'name': row[1],
            'type': row[2],
            'cpf_cnpj': row[3],
            'email': row[4],
            'user_count': row[5],
            'foto_perfil': row[6],
            'telefone': row[7],
            'endereco': row[8],
            'cidade': row[9],
            'estado': row[10],
            'razao_social': row[11],
            'email_institucional': row[12],
            'cep': row[13]
        })
    
    conn.close()
    return jsonify(entities)

@app.route('/api/admin/entity/<int:entity_id>/users')
@login_required
@role_required('admin')
def get_entity_users(entity_id):
    """Lista os usuários de uma entidade específica"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Buscar entidade
    c.execute('SELECT name, role FROM users WHERE id = ?', (entity_id,))
    entity = c.fetchone()
    
    if not entity:
        conn.close()
        return jsonify({'error': 'Entidade não encontrada'}), 404
    
    # Buscar usuários da entidade
    c.execute('''
        SELECT id, name, email, user_number, is_active, last_login, created_at,
               foto_perfil, telefone, endereco, cidade, estado, razao_social, email_institucional, cep, cpf_cnpj
        FROM users
        WHERE entity_id = ?
        ORDER BY user_number
    ''', (entity_id,))
    
    users = []
    for row in c.fetchall():
        users.append({
            'id': row[0],
            'name': row[1],
            'email': row[2],
            'user_number': row[3] or 0,
            'is_active': row[4],
            'last_login': row[5],
            'created_at': row[6],
            'foto_perfil': row[7],
            'telefone': row[8],
            'endereco': row[9],
            'cidade': row[10],
            'estado': row[11],
            'razao_social': row[12],
            'email_institucional': row[13],
            'cep': row[14],
            'cpf_cnpj': row[15]
        })
    
    conn.close()
    return jsonify({
        'entity_name': entity[0],
        'entity_type': entity[1],
        'users': users
    })

@app.route('/api/admin/entity/<int:entity_id>/users', methods=['POST'])
@login_required
@role_required('admin')
def create_entity_user(entity_id):
    """Cria novo usuário para uma entidade"""
    data = request.json
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Verificar se entidade existe
    c.execute('SELECT name, role FROM users WHERE id = ?', (entity_id,))
    entity = c.fetchone()
    
    if not entity:
        conn.close()
        return jsonify({'error': 'Entidade não encontrada'}), 404
    
    # Verificar se já tem 5 usuários
    c.execute('SELECT COUNT(*) FROM users WHERE entity_id = ?', (entity_id,))
    user_count = c.fetchone()[0]
    
    if user_count >= 5:
        conn.close()
        return jsonify({'error': 'Limite de 5 usuários por entidade atingido'}), 400
    
    # Verificar se email já existe
    c.execute('SELECT id FROM users WHERE email = ?', (data['email'],))
    if c.fetchone():
        conn.close()
        return jsonify({'error': 'Email já cadastrado'}), 400
    
    # Definir número do usuário
    c.execute('SELECT MAX(user_number) FROM users WHERE entity_id = ?', (entity_id,))
    max_number = c.fetchone()[0]
    user_number = (max_number or 0) + 1
    
    # Criar usuário
    password_hash = generate_password_hash(data.get('password', 'temp123'))
    
    c.execute('''
        INSERT INTO users (name, email, password, role, cpf_cnpj, entity_id, user_number, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
    ''', (data['name'], data['email'], password_hash, entity[1], data.get('cpf_cnpj', ''), 
          entity_id, user_number, datetime.now().isoformat()))
    
    conn.commit()
    new_user_id = c.lastrowid
    conn.close()
    
    return jsonify({'success': True, 'user_id': new_user_id, 'user_number': user_number})

@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@login_required
@role_required('admin')
def update_user(user_id):
    """Atualiza dados de um usuário"""
    data = request.json
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Atualizar campos
    updates = []
    params = []
    
    if 'name' in data:
        updates.append('name = ?')
        params.append(data['name'])
    
    if 'email' in data:
        # Verificar se email já existe em outro usuário
        c.execute('SELECT id FROM users WHERE email = ? AND id != ?', (data['email'], user_id))
        if c.fetchone():
            conn.close()
            return jsonify({'error': 'Email já cadastrado'}), 400
        updates.append('email = ?')
        params.append(data['email'])
    
    if 'is_active' in data:
        updates.append('is_active = ?')
        params.append(1 if data['is_active'] else 0)
    
    if updates:
        params.append(user_id)
        c.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    
    conn.close()
    return jsonify({'success': True})

@app.route('/api/admin/users/<int:user_id>/reset-token', methods=['POST'])
@login_required
@role_required('admin')
def generate_reset_token(user_id):
    """Gera token de redefinição de senha"""
    import secrets
    from datetime import timedelta
    
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(hours=24)).isoformat()
    
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    c.execute('''
        UPDATE users 
        SET reset_token = ?, reset_token_expires = ?
        WHERE id = ?
    ''', (token, expires, user_id))
    
    conn.commit()
    
    # Buscar email do usuário
    c.execute('SELECT email, name FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    
    conn.close()
    
    # URL de redefinição
    reset_url = f"{request.host_url}reset-password?token={token}"
    
    return jsonify({
        'success': True,
        'token': token,
        'reset_url': reset_url,
        'email': user[0],
        'name': user[1],
        'expires': expires
    })

# ==================== SISTEMA DE AUTORIZAÇÃO RPPS ====================

@app.route('/api/rpps/authorize-process/<int:process_id>', methods=['POST'])
@login_required
@role_required('rpps')
def authorize_process(process_id):
    """RPPS autoriza um processo recebido após verificar senha"""
    data = request.json
    password = data.get('password')
    
    if not password:
        return jsonify({'error': 'Senha não fornecida'}), 400
    
    # Verificar senha do usuário logado
    user_id = session.get('user_id')
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    c.execute('SELECT password FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    
    if not user or not check_password_hash(user[0], password):
        conn.close()
        return jsonify({'error': 'Senha incorreta'}), 401
    
    # Autorizar processo
    c.execute('''
        UPDATE processes 
        SET is_authorized = 1, authorized_by = ?, authorized_at = ?
        WHERE id = ?
    ''', (user_id, datetime.now().isoformat(), process_id))
    
    # Registrar no histórico
    c.execute('''
        INSERT INTO action_history (process_id, user_id, action, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (process_id, user_id, 'process_authorized', datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Processo autorizado com sucesso'})

# ==================== ANÁLISE DE IA ====================

@app.route('/api/financial/analyze-documents/<int:process_id>', methods=['POST'])
@login_required
@role_required('financial')
def analyze_documents_pre(process_id):
    """Pré-análise de documentos pela IF antes de enviar"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Buscar documentos do processo
    c.execute('''
        SELECT id, type, filename, file_path
        FROM documents
        WHERE process_id = ?
    ''', (process_id,))
    
    documents = c.fetchall()
    
    if not documents:
        conn.close()
        return jsonify({'error': 'Nenhum documento encontrado'}), 404
    
    # Analisar cada documento
    analysis_results = []
    
    for doc in documents:
        doc_id, doc_type, filename, filepath = doc
        
        try:
            # Análise básica com IA
            full_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # Simular análise (substitua pela análise real de IA)
            result = {
                'document_id': doc_id,
                'document_type': doc_type,
                'filename': filename,
                'status': 'valid',  # valid, warning, invalid
                'confidence': 0.85,
                'issues': [],
                'summary': f'Documento {doc_type} aprovado na pré-análise'
            }
            
            analysis_results.append(result)
            
        except Exception as e:
            analysis_results.append({
                'document_id': doc_id,
                'document_type': doc_type,
                'filename': filename,
                'status': 'error',
                'error': str(e)
            })
    
    # Salvar análise no processo
    analysis_json = json.dumps(analysis_results, ensure_ascii=False)
    c.execute('''
        UPDATE processes 
        SET ai_pre_analysis = ?, ai_analysis_date = ?
        WHERE id = ?
    ''', (analysis_json, datetime.now().isoformat(), process_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'analysis': analysis_results
    })

@app.route('/api/rpps/process/<int:process_id>/ai-analysis')
@login_required
@role_required('rpps')
def get_ai_analysis(process_id):
    """Retorna análise completa de IA para o RPPS"""
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT ai_pre_analysis, ai_full_analysis, ai_analysis_date
        FROM processes
        WHERE id = ?
    ''', (process_id,))
    
    row = c.fetchone()
    conn.close()
    
    if not row:
        return jsonify({'error': 'Processo não encontrado'}), 404
    
    pre_analysis = json.loads(row[0]) if row[0] else None
    full_analysis = json.loads(row[1]) if row[1] else None
    
    return jsonify({
        'pre_analysis': pre_analysis,
        'full_analysis': full_analysis,
        'analysis_date': row[2]
    })

@app.route('/api/process/<int:process_id>/analysis-report', methods=['GET'])
@login_required
def get_analysis_report(process_id):
    """Retorna dados completos da análise para o relatório visual"""
    print(f"\n📊 Gerando relatório de análise para processo #{process_id}")
    
    conn = sqlite3.connect('credenciamento.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Buscar informações do processo (sem colunas ai_pre_analysis, ai_full_analysis, ai_analysis_date que não existem)
    c.execute('''SELECT id, custom_id, financial_institution_name, 
                 financial_institution_cnpj, credentialing_type, status, 
                 created_at
                 FROM processes WHERE id = ?''', (process_id,))
    process_row = c.fetchone()
    
    if not process_row:
        conn.close()
        return jsonify({'success': False, 'error': 'Processo não encontrado'}), 404
    
    process = dict(process_row)
    
    # Buscar todos os documentos do processo
    c.execute('''SELECT id, type, name, filename, status, analysis_data, 
                 uploaded_at
                 FROM documents WHERE process_id = ? ORDER BY uploaded_at''', 
              (process_id,))
    documents_rows = c.fetchall()
    
    conn.close()
    
    # Processar documentos
    documents = []
    total_score = 0
    num_docs = 0
    approved = 0
    rejected = 0
    warnings = 0
    
    for doc_row in documents_rows:
        doc = dict(doc_row)
        analysis_data = json.loads(doc['analysis_data']) if doc['analysis_data'] else {}
        
        # Extrair dados da análise
        ai_analysis = analysis_data.get('ai_content_analysis', {})
        signature_validation = analysis_data.get('signature_validation', {})
        
        # Calcular score
        score = ai_analysis.get('score', 50)
        is_valid = ai_analysis.get('is_valid', False)
        
        # Contabilizar
        total_score += score
        num_docs += 1
        
        if is_valid:
            approved += 1
        else:
            rejected += 1
        
        if len(ai_analysis.get('warnings', [])) > 0:
            warnings += 1
        
        # Montar estrutura de documento com comentários explicativos
        doc_info = {
            'id': doc['id'],
            'name': doc['name'],
            'type': doc['type'],
            'filename': doc['filename'],
            'status': doc['status'],
            'uploaded_at': doc['uploaded_at'],
            'analysis': {
                'score': score,
                'is_valid': is_valid,
                'issues': ai_analysis.get('issues', []),
                'warnings': ai_analysis.get('warnings', []),
                'summary': ai_analysis.get('summary', 'Análise concluída pela IA'),
                'tipo_correto': True,
                'tipo_correto_comentario': 'Documento corresponde ao tipo declarado',
                'instituicao_mencionada': ai_analysis.get('institution_mentioned', True),
                'instituicao_comentario': ai_analysis.get('institution_comment', 'Instituição identificada no documento'),
                'completude': ai_analysis.get('completeness', score),
                'completude_comentario': ai_analysis.get('completeness_comment', f'Documento apresenta {score}% das informações esperadas'),
                'coerencia': ai_analysis.get('coherence', score),
                'coerencia_comentario': ai_analysis.get('coherence_comment', f'Informações apresentam coerência de {score}%')
            }
        }
        
        documents.append(doc_info)
    
    # Calcular média
    average_score = round(total_score / num_docs) if num_docs > 0 else 0
    
    # Montar resposta
    report = {
        'success': True,
        'process': {
            'id': process['id'],
            'custom_id': process['custom_id'],
            'institution_name': process['financial_institution_name'],
            'institution_cnpj': process['financial_institution_cnpj'],
            'category': process['credentialing_type'],
            'status': process['status'],
            'created_at': process['created_at']
        },
        'summary': {
            'approved': approved,
            'rejected': rejected,
            'warnings': warnings,
            'average_score': average_score,
            'total_documents': num_docs
        },
        'documents': documents,
        'analysis_date': datetime.now().isoformat()
    }
    
    print(f"✅ Relatório gerado: {num_docs} documentos, média {average_score}%")
    
    return jsonify(report)

@app.route('/analysis-report', methods=['GET'])
@login_required
def analysis_report_page():
    """Página de relatório de análise"""
    return render_template('analysis_report.html')


# ========== WORKFLOW TERMO DE CREDENCIAMENTO ==========

@app.route('/api/termo/prepare-pdf/<int:doc_id>', methods=['POST'])
@login_required
def prepare_termo_pdf(doc_id):
    """
    ETAPA 1: Analista RPPS prepara PDF do Termo de Credenciamento
    - Baixa Excel aprovado
    - Converte/prepara PDF com campos de assinatura
    - Faz upload do PDF preparado
    - Muda status para "prepared_for_if"
    """
    if session.get('user_type') != 'rpps':
        return jsonify({'error': 'Apenas analistas RPPS podem preparar o PDF'}), 403
    
    try:
        # Verificar se o arquivo foi enviado
        if 'prepared_pdf' not in request.files:
            return jsonify({'error': 'PDF preparado não enviado'}), 400
        
        file = request.files['prepared_pdf']
        if file.filename == '':
            return jsonify({'error': 'Arquivo vazio'}), 400
        
        conn = sqlite3.connect('credenciamento.db')
        c = conn.cursor()
        
        # Buscar documento original
        c.execute('''SELECT filename, name, process_id FROM documents WHERE id = ?''', (doc_id,))
        doc = c.fetchone()
        
        if not doc:
            conn.close()
            return jsonify({'error': 'Documento não encontrado'}), 404
        
        original_filename = doc[0]
        doc_name = doc[1]
        process_id = doc[2]
        
        # Salvar PDF preparado
        filename = secure_filename(f"{process_id}_termo_prepared_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Atualizar documento com novo arquivo e status
        c.execute('''
            UPDATE documents 
            SET filename = ?,
                workflow_status = 'prepared_for_if',
                workflow_version = workflow_version + 1,
                original_filename = ?,
                prepared_by = ?,
                prepared_at = ?
            WHERE id = ?
        ''', (filename, original_filename, session.get('username'), datetime.now().isoformat(), doc_id))
        
        # Adicionar comunicação
        c.execute('''
            INSERT INTO communications (process_id, user_type, user_name, message, message_type)
            VALUES (?, ?, ?, ?, ?)
        ''', (process_id, 'rpps', session.get('username'), 
              f'📄 PDF do Termo de Credenciamento preparado e enviado para assinatura da IF', 'system'))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'PDF preparado com sucesso! Documento pronto para envio à IF.',
            'workflow_status': 'prepared_for_if'
        })
        
    except Exception as e:
        print(f"Erro ao preparar PDF: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/termo/if-signed/<int:doc_id>', methods=['POST'])
@login_required
def termo_if_signed(doc_id):
    """
    ETAPA 2: IF retorna Termo assinado
    - IF faz upload do PDF assinado
    - Muda status para "signed_by_if"
    """
    if session.get('user_type') != 'financial':
        return jsonify({'error': 'Apenas IFs podem enviar documento assinado'}), 403
    
    try:
        if 'signed_pdf' not in request.files:
            return jsonify({'error': 'PDF assinado não enviado'}), 400
        
        file = request.files['signed_pdf']
        if file.filename == '':
            return jsonify({'error': 'Arquivo vazio'}), 400
        
        conn = sqlite3.connect('credenciamento.db')
        c = conn.cursor()
        
        # Buscar documento
        c.execute('''SELECT filename, name, process_id, workflow_status FROM documents WHERE id = ?''', (doc_id,))
        doc = c.fetchone()
        
        if not doc:
            conn.close()
            return jsonify({'error': 'Documento não encontrado'}), 404
        
        if doc[3] != 'prepared_for_if':
            conn.close()
            return jsonify({'error': 'Documento não está no status correto'}), 400
        
        process_id = doc[2]
        
        # Salvar PDF assinado pela IF
        filename = secure_filename(f"{process_id}_termo_if_signed_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Atualizar documento
        c.execute('''
            UPDATE documents 
            SET filename = ?,
                workflow_status = 'signed_by_if',
                workflow_version = workflow_version + 1,
                signed_by_if_at = ?
            WHERE id = ?
        ''', (filename, datetime.now().isoformat(), doc_id))
        
        # Adicionar comunicação
        c.execute('''
            INSERT INTO communications (process_id, user_type, user_name, message, message_type)
            VALUES (?, ?, ?, ?, ?)
        ''', (process_id, 'financial', session.get('username'), 
              f'✅ Termo de Credenciamento assinado pela IF e devolvido ao RPPS', 'system'))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Termo assinado recebido! Aguardando assinatura final do RPPS.',
            'workflow_status': 'signed_by_if'
        })
        
    except Exception as e:
        print(f"Erro ao receber PDF assinado: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/termo/final-signed/<int:doc_id>', methods=['POST'])
@login_required
def termo_final_signed(doc_id):
    """
    ETAPA 3: RPPS assina versão final consolidada
    - RPPS faz últimos ajustes e assina
    - Faz upload do PDF final
    - Muda status para "final_signed"
    - DOCUMENTO COMPLETO!
    """
    if session.get('user_type') != 'rpps':
        return jsonify({'error': 'Apenas analistas RPPS podem finalizar'}), 403
    
    try:
        if 'final_pdf' not in request.files:
            return jsonify({'error': 'PDF final não enviado'}), 400
        
        file = request.files['final_pdf']
        if file.filename == '':
            return jsonify({'error': 'Arquivo vazio'}), 400
        
        conn = sqlite3.connect('credenciamento.db')
        c = conn.cursor()
        
        # Buscar documento
        c.execute('''SELECT filename, name, process_id, workflow_status FROM documents WHERE id = ?''', (doc_id,))
        doc = c.fetchone()
        
        if not doc:
            conn.close()
            return jsonify({'error': 'Documento não encontrado'}), 404
        
        if doc[3] != 'signed_by_if':
            conn.close()
            return jsonify({'error': 'Documento não está no status correto'}), 400
        
        process_id = doc[2]
        
        # Salvar PDF final assinado
        filename = secure_filename(f"{process_id}_termo_FINAL_SIGNED_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Atualizar documento
        c.execute('''
            UPDATE documents 
            SET filename = ?,
                workflow_status = 'final_signed',
                workflow_version = workflow_version + 1,
                final_signed_at = ?
            WHERE id = ?
        ''', (filename, datetime.now().isoformat(), doc_id))
        
        # Adicionar comunicação
        c.execute('''
            INSERT INTO communications (process_id, user_type, user_name, message, message_type)
            VALUES (?, ?, ?, ?, ?)
        ''', (process_id, 'rpps', session.get('username'), 
              f'🎉 Termo de Credenciamento FINALIZADO! Assinado por todas as partes.', 'system'))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Termo de Credenciamento FINALIZADO! Documento consolidado e assinado por todos.',
            'workflow_status': 'final_signed'
        })
        
    except Exception as e:
        print(f"Erro ao finalizar documento: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/termo/status/<int:doc_id>', methods=['GET'])
@login_required
def get_termo_status(doc_id):
    """Obter status do workflow do termo"""
    try:
        conn = sqlite3.connect('credenciamento.db')
        c = conn.cursor()
        
        c.execute('''
            SELECT workflow_status, workflow_version, original_filename, 
                   prepared_by, prepared_at, signed_by_if_at, final_signed_at
            FROM documents WHERE id = ?
        ''', (doc_id,))
        
        row = c.fetchone()
        conn.close()
        
        if not row:
            return jsonify({'error': 'Documento não encontrado'}), 404
        
        return jsonify({
            'success': True,
            'workflow_status': row[0] or 'initial',
            'workflow_version': row[1] or 1,
            'original_filename': row[2],
            'prepared_by': row[3],
            'prepared_at': row[4],
            'signed_by_if_at': row[5],
            'final_signed_at': row[6]
        })
        
    except Exception as e:
        print(f"Erro ao obter status: {e}")
        return jsonify({'error': str(e)}), 500


# ========== ROTAS DE MODELOS DE DOCUMENTOS ==========

@app.route('/modelos-documentos')
@login_required
def modelos_documentos():
    """Página de modelos de documentos oficiais"""
    import glob
    
    # Listar todos os arquivos na pasta Modelos
    modelos_path = os.path.join(app.root_path, 'Modelos')
    documentos = []
    
    if os.path.exists(modelos_path):
        # Mapear extensões para tipos de documento
        tipo_mapeamento = {
            '.pdf': 'PDF',
            '.doc': 'DOC',
            '.docx': 'DOCX',
            '.xlsx': 'XLSX',
            '.xls': 'XLS',
            '.txt': 'TXT'
        }
        
        # Mapear nomes de arquivos para descrições amigáveis
        descricoes_mapeamento = {
            'TermodeCredenciamentoAgenteAutonomo': {
                'nome': 'TERMO DE CREDENCIAMENTO - AGENTE AUTÔNOMO',
                'descricao': 'Termo oficial para credenciamento de Agente Autônomo de Investimentos junto ao IPAJM.'
            },
            'TermodeCredenciamentoAdministrador': {
                'nome': 'TERMO DE CREDENCIAMENTO - ADMINISTRADOR/GESTOR',
                'descricao': 'Termo oficial para credenciamento de Administrador ou Gestor de Fundo de Investimento.'
            },
            'TermodeCredenciamentoDistribuidor': {
                'nome': 'TERMO DE CREDENCIAMENTO - DISTRIBUIDOR',
                'descricao': 'Termo oficial para credenciamento de instituições distribuidoras junto ao IPAJM.'
            },
            'TermodeCredenciamentoCustodiante': {
                'nome': 'TERMO DE CREDENCIAMENTO - CUSTODIANTE',
                'descricao': 'Termo oficial para credenciamento de instituições custodiantes junto ao IPAJM.'
            },
            'TermodeCredenciamentoInstituio': {
                'nome': 'TERMO DE CREDENCIAMENTO - INSTITUIÇÃO BANCÁRIA',
                'descricao': 'Termo para credenciamento de Instituição Financeira Bancária emissora de ativo financeiro de renda fixa.'
            },
            'TermodeCadastramentoFundos': {
                'nome': 'TERMO DE CADASTRAMENTO - FUNDOS DE INVESTIMENTOS',
                'descricao': 'Termo oficial de cadastramento de Fundos de Investimentos no sistema.'
            },
            'Declaracao_Unificada': {
                'nome': 'DECLARAÇÃO UNIFICADA',
                'descricao': 'Declaração unificada padrão contendo todas as informações necessárias para o credenciamento.'
            },
            'Declaracao_Unificada_Intermediario': {
                'nome': 'DECLARAÇÃO UNIFICADA - INTERMEDIÁRIO TPF',
                'descricao': 'Declaração unificada específica para Intermediário de Título Público Federal (TPF).'
            },
            'Checklist_Credenciamento': {
                'nome': 'CHECKLIST DE CREDENCIAMENTO - ANEXO NP43',
                'descricao': 'Checklist completo de documentos necessários conforme Norma de Procedimento 43.'
            },
            'Checklist_Cadastro_Fundos': {
                'nome': 'CHECKLIST - CADASTRO DE FUNDOS CADPREV',
                'descricao': 'Checklist específico para cadastro de fundos de investimento no sistema CADPREV.'
            },
            'Informacoes_preenchimento_CADPREV': {
                'nome': 'INSTRUÇÕES - PREENCHIMENTO CADPREV',
                'descricao': 'Informações e orientações detalhadas para o correto preenchimento do CADPREV.'
            },
            'termo_credenciamento': {
                'nome': 'TERMO DE CREDENCIAMENTO',
                'descricao': 'Modelo oficial do termo de credenciamento para Instituições Financeiras junto ao RPPS.'
            },
            'declaracao_unificada': {
                'nome': 'DECLARAÇÃO UNIFICADA',
                'descricao': 'Modelo de declaração unificada com as informações necessárias para o processo.'
            },
            'checklist': {
                'nome': 'CHECKLIST DE DOCUMENTOS',
                'descricao': 'Lista completa de documentos necessários para o credenciamento.'
            },
            'apresentacao_institucional': {
                'nome': 'APRESENTAÇÃO INSTITUCIONAL',
                'descricao': 'Modelo de apresentação institucional da Instituição Financeira.'
            },
            'formulario_referencia': {
                'nome': 'FORMULÁRIO DE REFERÊNCIA CVM',
                'descricao': 'Modelo de formulário de referência para registro na CVM.'
            },
            'contrato_distribuicao': {
                'nome': 'CONTRATO DE DISTRIBUIÇÃO',
                'descricao': 'Modelo de contrato de distribuição de recursos.'
            }
        }
        
        # Arquivos a serem ignorados (criados como exemplo/documentação)
        arquivos_ignorados = [
            'README.md',
            'LISTA_DOCUMENTOS.md',
            'exemplo_checklist.txt',
            'Checklist_Cadastro_Fundos_CADPREV.xlsx'  # Usar apenas versão XLSM
        ]
        
        # Buscar todos os arquivos
        for filepath in glob.glob(os.path.join(modelos_path, '*')):
            if os.path.isfile(filepath):
                filename = os.path.basename(filepath)
                
                # Ignorar arquivos de exemplo e documentação
                if filename in arquivos_ignorados:
                    continue
                
                nome_base = os.path.splitext(filename)[0]
                extensao = os.path.splitext(filename)[1].lower()
                
                # Buscar descrição personalizada ou usar genérica
                info_doc = None
                for chave, dados in descricoes_mapeamento.items():
                    if chave in nome_base.lower():
                        info_doc = dados
                        break
                
                if info_doc:
                    nome_exibicao = info_doc['nome']
                    descricao = info_doc['descricao']
                else:
                    # Nome genérico formatado
                    nome_exibicao = nome_base.replace('_', ' ').title()
                    descricao = f'Modelo de documento para {nome_exibicao.lower()}.'
                
                tipo = tipo_mapeamento.get(extensao, extensao.upper().replace('.', ''))
                
                documentos.append({
                    'arquivo': filename,
                    'nome': nome_exibicao,
                    'descricao': descricao,
                    'tipo': tipo
                })
        
        # Ordenar por nome
        documentos.sort(key=lambda x: x['nome'])
    
    return render_template('modelos_documentos.html', documentos=documentos)


@app.route('/modelos-documentos/download/<filename>')
@login_required
def download_modelo(filename):
    """Download de modelo de documento"""
    try:
        modelos_path = os.path.join(app.root_path, 'Modelos')
        return send_from_directory(modelos_path, filename, as_attachment=True)
    except Exception as e:
        print(f"Erro ao baixar modelo: {e}")
        return jsonify({'error': 'Arquivo não encontrado'}), 404


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
