"""
Script para forçar análise de documentos que ficaram travados no status 'analyzing'
"""
import sqlite3
import os
from ai_analyzer_rigorous import analyze_document_rigorous
from datetime import datetime
import json

def force_analyze_stuck_documents():
    conn = sqlite3.connect('credenciamento.db')
    c = conn.cursor()
    
    # Buscar documentos com status 'analyzing'
    c.execute('''
        SELECT d.id, d.filename, d.type, d.process_id, 
               p.financial_institution_name, p.financial_institution_cnpj
        FROM documents d
        JOIN processes p ON p.id = d.process_id
        WHERE d.status = 'analyzing'
    ''')
    
    stuck_docs = c.fetchall()
    
    if not stuck_docs:
        print("✅ Nenhum documento travado encontrado!")
        conn.close()
        return
    
    print(f"🔍 Encontrados {len(stuck_docs)} documentos travados. Iniciando análise forçada...\n")
    
    for doc_id, filename, doc_type, process_id, inst_name, inst_cnpj in stuck_docs:
        print(f"📄 Analisando documento #{doc_id}: {filename}")
        filepath = os.path.join('uploads', filename)
        
        if not os.path.exists(filepath):
            print(f"   ❌ Arquivo não encontrado: {filepath}")
            continue
        
        try:
            # Executar análise
            ai_result = analyze_document_rigorous(
                filepath, 
                doc_type, 
                filename,
                inst_name,
                inst_cnpj
            )
            
            # Determinar se requer assinatura
            requires_signature = doc_type in ['apresentacao_institucional', 'ata_conselho', 'comprovante_representante']
            
            # Preparar dados da análise
            analysis_data = {
                'status': 'analyzed',
                'analyzed_at': datetime.now().isoformat(),
                'requires_signature': requires_signature,
                'ai_content_analysis': ai_result,
                'signature_validated': False
            }
            
            # Determinar status final
            content_ok = ai_result.get('is_valid', False)
            
            if not content_ok:
                final_status = 'rejected'
                analysis_data['rejection_summary'] = ' | '.join(ai_result.get('issues', ['Documento reprovado']))
            elif requires_signature:
                final_status = 'pending'
                analysis_data['pending_summary'] = 'Conteúdo aprovado. Aguardando validação de assinatura digital.'
            else:
                final_status = 'approved'
                analysis_data['approval_summary'] = 'Documento aprovado'
            
            analysis_data['final_verdict'] = final_status
            analysis_data['content_ok'] = content_ok
            
            # Atualizar banco
            c.execute('''UPDATE documents 
                        SET status = ?, analysis_data = ?
                        WHERE id = ?''',
                     (final_status, json.dumps(analysis_data), doc_id))
            
            conn.commit()
            
            print(f"   ✅ Análise concluída! Score: {ai_result.get('score', 0)}/100 | Status: {final_status}")
            
        except Exception as e:
            print(f"   ❌ Erro na análise: {str(e)}")
            import traceback
            traceback.print_exc()
    
    conn.close()
    print("\n✅ Processo de análise forçada concluído!")

if __name__ == '__main__':
    force_analyze_stuck_documents()
