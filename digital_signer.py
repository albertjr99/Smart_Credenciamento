"""
Módulo de Assinatura Digital de PDFs
Suporta certificados A1 (.pfx/.p12) e prepara dados para A3 (via Fortify/client-side)
"""
import os
import tempfile
import hashlib
from datetime import datetime
from io import BytesIO
from typing import Optional, Tuple, Dict, Any

# Imports para assinatura
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.backends import default_backend
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

try:
    from pyhanko.sign import signers, fields
    from pyhanko.sign.general import load_cert_from_pemder
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign.fields import SigFieldSpec
    from pyhanko import stamp
    PYHANKO_AVAILABLE = True
except ImportError as e:
    PYHANKO_AVAILABLE = False
    print(f"⚠️ pyHanko não disponível - assinatura A1 limitada: {e}")


class DigitalSigner:
    """Classe para assinatura digital de PDFs"""
    
    def __init__(self):
        self.last_error = None
    
    def load_pfx_certificate(self, pfx_data: bytes, password: str) -> Tuple[Optional[Any], Optional[Any], Optional[list], Optional[str]]:
        """
        Carrega um certificado A1 (.pfx/.p12)
        
        Returns:
            Tuple: (private_key, certificate, chain, error_message)
        """
        try:
            # Decodificar o PFX
            private_key, certificate, chain = pkcs12.load_key_and_certificates(
                pfx_data,
                password.encode('utf-8') if password else None,
                default_backend()
            )
            
            if not private_key or not certificate:
                return None, None, None, "Certificado inválido ou senha incorreta"
            
            return private_key, certificate, chain or [], None
            
        except Exception as e:
            error_msg = str(e)
            if "password" in error_msg.lower() or "mac" in error_msg.lower():
                return None, None, None, "Senha do certificado incorreta"
            return None, None, None, f"Erro ao carregar certificado: {error_msg}"
    
    def get_certificate_info(self, certificate) -> Dict[str, Any]:
        """Extrai informações do certificado"""
        try:
            subject = certificate.subject
            issuer = certificate.issuer
            
            # Extrair campos do subject
            def get_attr(obj, oid_name):
                try:
                    oid = getattr(x509.oid.NameOID, oid_name)
                    attrs = obj.get_attributes_for_oid(oid)
                    return attrs[0].value if attrs else None
                except:
                    return None
            
            info = {
                'comum_name': get_attr(subject, 'COMMON_NAME'),
                'organization': get_attr(subject, 'ORGANIZATION_NAME'),
                'organizational_unit': get_attr(subject, 'ORGANIZATIONAL_UNIT_NAME'),
                'email': get_attr(subject, 'EMAIL_ADDRESS'),
                'cpf_cnpj': None,
                'issuer_cn': get_attr(issuer, 'COMMON_NAME'),
                'issuer_org': get_attr(issuer, 'ORGANIZATION_NAME'),
                'valid_from': certificate.not_valid_before_utc.isoformat() if hasattr(certificate, 'not_valid_before_utc') else certificate.not_valid_before.isoformat(),
                'valid_until': certificate.not_valid_after_utc.isoformat() if hasattr(certificate, 'not_valid_after_utc') else certificate.not_valid_after.isoformat(),
                'serial_number': str(certificate.serial_number),
                'is_valid': self._check_certificate_validity(certificate)
            }
            
            # Tentar extrair CPF/CNPJ do certificado ICP-Brasil
            cn = info['comum_name'] or ''
            # Formato típico: "NOME DO TITULAR:12345678901"
            if ':' in cn:
                parts = cn.split(':')
                if len(parts) >= 2:
                    cpf_cnpj = parts[-1].strip()
                    if len(cpf_cnpj) in [11, 14]:  # CPF ou CNPJ
                        info['cpf_cnpj'] = cpf_cnpj
            
            return info
            
        except Exception as e:
            return {'error': str(e)}
    
    def _check_certificate_validity(self, certificate) -> Dict[str, Any]:
        """Verifica se o certificado está dentro da validade"""
        now = datetime.utcnow()
        
        # Pegar datas de validade
        try:
            not_before = certificate.not_valid_before_utc.replace(tzinfo=None)
            not_after = certificate.not_valid_after_utc.replace(tzinfo=None)
        except AttributeError:
            not_before = certificate.not_valid_before
            not_after = certificate.not_valid_after
        
        is_valid = not_before <= now <= not_after
        days_remaining = (not_after - now).days if is_valid else 0
        
        return {
            'is_valid': is_valid,
            'days_remaining': days_remaining,
            'expired': now > not_after,
            'not_yet_valid': now < not_before
        }
    
    def sign_pdf_a1(self, pdf_data: bytes, pfx_data: bytes, password: str, 
                    reason: str = "Documento assinado digitalmente",
                    location: str = "Brasil",
                    visual_signature: bool = True,
                    signature_position: str = "bottom-right",
                    page: int = 0) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Assina um PDF usando certificado A1 (.pfx/.p12)
        
        Args:
            pdf_data: Conteúdo do PDF em bytes
            pfx_data: Conteúdo do arquivo .pfx em bytes
            password: Senha do certificado
            reason: Motivo da assinatura
            location: Local da assinatura
            visual_signature: Se deve incluir carimbo visual
            signature_position: Posição do carimbo ('bottom-right', 'bottom-left', 'top-right', 'top-left')
            page: Página para o carimbo visual (0 = primeira, -1 = última)
        
        Returns:
            Tuple: (pdf_assinado_bytes, error_message)
        """
        if not PYHANKO_AVAILABLE:
            return None, "Biblioteca pyHanko não disponível"
        
        try:
            # Carregar certificado
            private_key, certificate, chain, error = self.load_pfx_certificate(pfx_data, password)
            if error:
                return None, error
            
            # Verificar validade
            validity = self._check_certificate_validity(certificate)
            if not validity['is_valid']:
                if validity['expired']:
                    return None, "Certificado expirado"
                if validity['not_yet_valid']:
                    return None, "Certificado ainda não é válido"
            
            # Obter info do certificado
            cert_info = self.get_certificate_info(certificate)
            signer_name = cert_info.get('comum_name', 'Assinante')
            
            # Criar o signer com pyHanko
            from pyhanko.sign import signers as pyhanko_signers
            from pyhanko.keys import keys as pyhanko_keys
            
            # Criar signer a partir do PFX
            signer = pyhanko_signers.SimpleSigner.load_pkcs12(
                pfx_file=BytesIO(pfx_data),
                passphrase=password.encode('utf-8') if password else None
            )
            
            # Preparar o PDF
            pdf_reader = PdfFileReader(BytesIO(pdf_data))
            pdf_writer = IncrementalPdfFileWriter(BytesIO(pdf_data))
            
            # Configurar metadados da assinatura
            signature_meta = pyhanko_signers.PdfSignatureMetadata(
                field_name='Signature1',
                reason=reason,
                location=location,
                name=signer_name,
                md_algorithm='sha256'
            )
            
            # Configurar aparência visual se solicitado
            if visual_signature:
                # Calcular posição do carimbo
                box = self._get_signature_box(signature_position)
                
                # Determinar página
                total_pages = len(pdf_reader.pages)
                if page == -1:
                    sig_page = total_pages - 1
                else:
                    sig_page = min(page, total_pages - 1)
                
                # Criar campo de assinatura
                sig_field_spec = SigFieldSpec(
                    sig_field_name='Signature1',
                    on_page=sig_page,
                    box=box
                )
                
                # Adicionar campo ao PDF
                fields.append_signature_field(pdf_writer, sig_field_spec)
                
                # Texto do carimbo
                stamp_style = stamp.TextStampStyle(
                    stamp_text=(
                        f"Assinado digitalmente por:\n"
                        f"%(signer)s\n"
                        f"Data: %(ts)s\n"
                        f"Razão: {reason}"
                    ),
                    background=stamp.STAMP_ART_CONTENT
                )
                
                # Assinar com aparência
                output = BytesIO()
                pyhanko_signers.sign_pdf(
                    pdf_writer,
                    signature_meta,
                    signer,
                    output=output,
                    timestamper=None,
                    existing_fields_only=False
                )
            else:
                # Assinatura invisível
                output = BytesIO()
                pyhanko_signers.sign_pdf(
                    pdf_writer,
                    signature_meta,
                    signer,
                    output=output
                )
            
            return output.getvalue(), None
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None, f"Erro ao assinar PDF: {str(e)}"
    
    def _get_signature_box(self, position: str) -> Tuple[int, int, int, int]:
        """Retorna as coordenadas do box da assinatura visual"""
        # Box: (x1, y1, x2, y2) - coordenadas do canto inferior esquerdo e superior direito
        # Página A4: aproximadamente 595 x 842 pontos
        
        width = 200
        height = 80
        margin = 30
        
        positions = {
            'bottom-right': (595 - width - margin, margin, 595 - margin, margin + height),
            'bottom-left': (margin, margin, margin + width, margin + height),
            'top-right': (595 - width - margin, 842 - height - margin, 595 - margin, 842 - margin),
            'top-left': (margin, 842 - height - margin, margin + width, 842 - margin),
            'center-bottom': (595/2 - width/2, margin, 595/2 + width/2, margin + height),
        }
        
        return positions.get(position, positions['bottom-right'])
    
    def prepare_hash_for_a3(self, pdf_data: bytes) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Prepara o hash de um PDF para assinatura A3 client-side
        
        O fluxo A3 é:
        1. Backend prepara o hash do documento
        2. Frontend envia hash para o Fortify/token
        3. Token assina o hash com a chave privada
        4. Frontend retorna a assinatura
        5. Backend incorpora a assinatura no PDF
        
        Returns:
            Tuple: (dict com dados para assinatura, error_message)
        """
        try:
            # Calcular hash SHA-256 do PDF
            pdf_hash = hashlib.sha256(pdf_data).digest()
            
            return {
                'hash': pdf_hash.hex(),
                'hash_algorithm': 'SHA-256',
                'pdf_size': len(pdf_data),
                'timestamp': datetime.utcnow().isoformat()
            }, None
            
        except Exception as e:
            return None, f"Erro ao preparar hash: {str(e)}"
    
    def finalize_a3_signature(self, pdf_data: bytes, signature_data: Dict) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Finaliza a assinatura A3 incorporando a assinatura no PDF
        
        Args:
            pdf_data: PDF original em bytes
            signature_data: Dict contendo:
                - signature: bytes da assinatura (hex ou base64)
                - certificate: certificado do assinante (PEM ou DER)
                - chain: cadeia de certificação (opcional)
        
        Returns:
            Tuple: (pdf_assinado_bytes, error_message)
        """
        # Esta função seria implementada quando tivermos o fluxo A3 completo
        # Por enquanto, retorna erro indicando que precisa do Fortify
        return None, "Assinatura A3 requer Fortify instalado no computador"


# Instância global
digital_signer = DigitalSigner()


def sign_document_a1(pdf_path: str, pfx_path: str, password: str, output_path: str = None, **kwargs) -> Tuple[bool, str]:
    """
    Função de conveniência para assinar um documento PDF com certificado A1
    
    Args:
        pdf_path: Caminho do PDF a assinar
        pfx_path: Caminho do certificado .pfx
        password: Senha do certificado
        output_path: Caminho de saída (se None, sobrescreve o original)
        **kwargs: Argumentos adicionais para sign_pdf_a1
    
    Returns:
        Tuple: (success, message)
    """
    try:
        with open(pdf_path, 'rb') as f:
            pdf_data = f.read()
        
        with open(pfx_path, 'rb') as f:
            pfx_data = f.read()
        
        signed_pdf, error = digital_signer.sign_pdf_a1(pdf_data, pfx_data, password, **kwargs)
        
        if error:
            return False, error
        
        out_path = output_path or pdf_path
        with open(out_path, 'wb') as f:
            f.write(signed_pdf)
        
        return True, f"Documento assinado com sucesso: {out_path}"
        
    except Exception as e:
        return False, f"Erro: {str(e)}"
