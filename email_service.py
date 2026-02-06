"""
Sistema de Envio de E-mails Automáticos
Notifica instituições financeiras e RPPS sobre movimentações
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import sqlite3
import os

class EmailService:
    """Serviço de envio de e-mails automáticos"""
    
    def __init__(self):
        # Configurações de e-mail (devem estar em .env)
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.email_from = os.getenv('EMAIL_FROM', 'sistema@credenciamento.gov.br')
        self.email_password = os.getenv('EMAIL_PASSWORD', '')
        self.enabled = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'
    
    def send_email(self, to_email, to_name, subject, body_html):
        """Envia e-mail"""
        
        if not self.enabled:
            print(f"📧 E-mail desabilitado (modo desenvolvimento)")
            print(f"   Para: {to_email}")
            print(f"   Assunto: {subject}")
            return {'success': True, 'mode': 'development'}
        
        try:
            # Criar mensagem
            msg = MIMEMultipart('alternative')
            msg['From'] = self.email_from
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Anexar HTML
            html_part = MIMEText(body_html, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Enviar
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                if self.email_password:
                    server.login(self.email_from, self.email_password)
                server.send_message(msg)
            
            print(f"✅ E-mail enviado para: {to_email}")
            return {'success': True, 'mode': 'production'}
            
        except Exception as e:
            print(f"❌ Erro ao enviar e-mail: {e}")
            return {'success': False, 'error': str(e)}
    
    def log_email(self, process_id, recipient_email, recipient_name, subject, body, status='sent', error=None):
        """Registra e-mail no banco de dados"""
        try:
            conn = sqlite3.connect('credenciamento.db')
            c = conn.cursor()
            c.execute('''INSERT INTO email_logs 
                         (process_id, recipient_email, recipient_name, subject, body, status, error_message)
                         VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (process_id, recipient_email, recipient_name, subject, body, status, error))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Erro ao logar e-mail: {e}")
    
    def notify_document_submission(self, process_id, institution_name, rpps_email, rpps_name):
        """Notifica RPPS sobre documentos submetidos pela instituição financeira"""
        
        subject = f"📄 Novos documentos recebidos - {institution_name}"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h2 style="color: #2563eb; margin: 0;">Sistema de Credenciamento RPPS</h2>
                </div>
                
                <p>Olá, <strong>{rpps_name}</strong>,</p>
                
                <p>A instituição financeira <strong>{institution_name}</strong> enviou novos documentos para análise no processo de credenciamento <strong>#{process_id}</strong>.</p>
                
                <div style="background-color: #eff6ff; border-left: 4px solid #2563eb; padding: 15px; margin: 20px 0;">
                    <p style="margin: 0;"><strong>📋 Ação necessária:</strong></p>
                    <p style="margin: 5px 0 0 0;">Por favor, acesse o sistema para revisar e analisar os documentos enviados.</p>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="http://127.0.0.1:5000/rpps/process/{process_id}" style="background-color: #2563eb; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        Acessar Processo
                    </a>
                </div>
                
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                
                <p style="color: #6b7280; font-size: 12px; text-align: center;">
                    Este é um e-mail automático do Sistema de Credenciamento RPPS.<br>
                    Não responda a este e-mail.
                </p>
            </div>
        </body>
        </html>
        """
        
        result = self.send_email(rpps_email, rpps_name, subject, body)
        self.log_email(process_id, rpps_email, rpps_name, subject, body, 
                      'sent' if result['success'] else 'failed',
                      result.get('error'))
        
        return result
    
    def notify_process_returned(self, process_id, institution_email, institution_name, rpps_name, reason, observations):
        """Notifica instituição financeira sobre processo devolvido pelo RPPS"""
        
        subject = f"🔄 Processo devolvido para revisão - Processo #{process_id}"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h2 style="color: #dc2626; margin: 0;">Sistema de Credenciamento RPPS</h2>
                </div>
                
                <p>Olá, <strong>{institution_name}</strong>,</p>
                
                <p>O RPPS analisou o processo de credenciamento <strong>#{process_id}</strong> e solicitou revisão.</p>
                
                <div style="background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 15px; margin: 20px 0;">
                    <p style="margin: 0;"><strong>📋 Motivo da devolução:</strong></p>
                    <p style="margin: 5px 0 0 0;">{reason}</p>
                </div>
                
                {f'<div style="background-color: #f3f4f6; padding: 15px; margin: 20px 0; border-radius: 5px;"><p style="margin: 0;"><strong>💬 Observações do RPPS:</strong></p><p style="margin: 5px 0 0 0;">{observations}</p></div>' if observations else ''}
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="http://127.0.0.1:5000/financial/process/{process_id}" style="background-color: #dc2626; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        Acessar e Revisar Processo
                    </a>
                </div>
                
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                
                <p style="color: #6b7280; font-size: 12px; text-align: center;">
                    Este é um e-mail automático do Sistema de Credenciamento RPPS.<br>
                    Não responda a este e-mail.
                </p>
            </div>
        </body>
        </html>
        """
        
        result = self.send_email(institution_email, institution_name, subject, body)
        self.log_email(process_id, institution_email, institution_name, subject, body,
                      'sent' if result['success'] else 'failed',
                      result.get('error'))
        
        return result
    
    def notify_process_approved(self, process_id, institution_email, institution_name, rpps_name):
        """Notifica instituição sobre aprovação do processo"""
        
        subject = f"✅ Processo aprovado - Processo #{process_id}"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h2 style="color: #16a34a; margin: 0;">Sistema de Credenciamento RPPS</h2>
                </div>
                
                <p>Olá, <strong>{institution_name}</strong>,</p>
                
                <p>Parabéns! O processo de credenciamento <strong>#{process_id}</strong> foi <strong style="color: #16a34a;">APROVADO</strong> pelo RPPS.</p>
                
                <div style="background-color: #f0fdf4; border-left: 4px solid #16a34a; padding: 15px; margin: 20px 0;">
                    <p style="margin: 0;"><strong>✅ Status: APROVADO</strong></p>
                    <p style="margin: 5px 0 0 0;">Todos os documentos foram aprovados e o credenciamento está concluído.</p>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="http://127.0.0.1:5000/financial/process/{process_id}" style="background-color: #16a34a; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        Ver Detalhes do Processo
                    </a>
                </div>
                
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                
                <p style="color: #6b7280; font-size: 12px; text-align: center;">
                    Este é um e-mail automático do Sistema de Credenciamento RPPS.<br>
                    Não responda a este e-mail.
                </p>
            </div>
        </body>
        </html>
        """
        
        result = self.send_email(institution_email, institution_name, subject, body)
        self.log_email(process_id, institution_email, institution_name, subject, body,
                      'sent' if result['success'] else 'failed',
                      result.get('error'))
        
        return result


# Instância global
email_service = EmailService()
