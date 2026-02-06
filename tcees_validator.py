"""
INTEGRAÇÃO COM TCEES - VALIDAÇÃO DE DOCUMENTOS PDF
Automatiza validação de assinaturas digitais através do site conformidadepdf.tcees.tc.br
Captura TODOS os dados de integridade retornados - detectando tanto ✓ quanto ✗

OTIMIZADO: Tempos reduzidos e suporte a processamento paralelo
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import os
import re

# Cache do ChromeDriver para evitar download repetido
_cached_driver_path = None

def get_chrome_driver_path():
    """Retorna o path do ChromeDriver, usando cache para evitar downloads repetidos"""
    global _cached_driver_path
    if _cached_driver_path is None:
        _cached_driver_path = ChromeDriverManager().install()
    return _cached_driver_path

def validate_pdf_with_tcees(pdf_path, quick_mode=False):
    """
    Valida PDF usando o site do TCEES e captura TODOS os dados
    CORRETAMENTE detectando checks verdes e X vermelhos
    
    Args:
        pdf_path: Caminho completo para o arquivo PDF
        quick_mode: Se True, usa tempos de espera reduzidos (mais rápido, menos confiável)
        
    Returns:
        dict completo com os resultados da validação
    """
    
    print(f"\n🔐 Validando documento com TCEES: {os.path.basename(pdf_path)}")
    
    # Configurar Chrome em modo headless otimizado
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')  # Novo headless mais rápido
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-infobars')
    chrome_options.add_argument('--disable-notifications')
    chrome_options.add_argument('--blink-settings=imagesEnabled=false')  # Não carregar imagens
    chrome_options.add_argument('--window-size=1280,720')
    chrome_options.add_argument('--lang=pt-BR')
    chrome_options.page_load_strategy = 'eager'  # Não esperar recursos completos
    
    # Tempos de espera AUMENTADOS para maior confiabilidade
    WAIT_PAGE_LOAD = 2 if quick_mode else 3
    WAIT_PROCESSING = 12 if quick_mode else 18  # Aumentado para dar mais tempo ao TCEES
    WAIT_RENDER = 3 if quick_mode else 5  # Tempo extra para garantir renderização completa
    
    driver = None
    
    try:
        # Inicializar o WebDriver (usa cache)
        print("   🌐 Abrindo navegador...")
        start_time = time.time()
        service = Service(get_chrome_driver_path())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(20)
        print(f"   ⚡ Navegador pronto em {time.time() - start_time:.1f}s")
        
        # Acessar o site do TCEES
        url = 'https://conformidadepdf.tcees.tc.br/'
        print(f"   📡 Acessando {url}...")
        driver.get(url)
        
        # Aguardar a página carregar
        time.sleep(WAIT_PAGE_LOAD)
        
        # Localizar e enviar o arquivo
        print("   📤 Fazendo upload do documento...")
        
        file_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="file"]'))
        )
        file_input.send_keys(os.path.abspath(pdf_path))
        print("   ✅ Arquivo enviado!")
        
        # Aguardar o processamento - verificar periodicamente se terminou
        print("   ⏳ Aguardando processamento...")
        
        # Polling: verificar a cada 2 segundos se os resultados apareceram E ESTÃO COMPLETOS
        max_wait = 35  # Aumentado para 35 segundos
        poll_interval = 2
        waited = 0
        results_ready = False
        last_html = ""
        stable_count = 0  # Contador de estabilidade - verifica se HTML parou de mudar
        
        while waited < max_wait:
            time.sleep(poll_interval)
            waited += poll_interval
            
            # Verificar se a tabela de resultados apareceu E está estável
            try:
                # Procurar por elementos que indicam que o processamento terminou
                resultado_container = driver.find_elements(By.ID, 'validacoes-arquivo')
                if resultado_container:
                    colunas = resultado_container[0].find_elements(By.CSS_SELECTOR, 'div.d-inline-block')
                    if len(colunas) >= 8:
                        # Verificar se os ícones (check ou X) já foram renderizados
                        current_html = resultado_container[0].get_attribute('innerHTML')
                        has_icons = 'fa-check' in current_html or 'fa-close' in current_html or 'fa-times' in current_html
                        
                        if has_icons:
                            # Verificar estabilidade - HTML não mudou desde última verificação
                            if current_html == last_html:
                                stable_count += 1
                                if stable_count >= 2:  # Estável por 4 segundos (2 polls)
                                    results_ready = True
                                    print(f"   ✅ Resultados prontos e estáveis em {waited}s!")
                                    break
                            else:
                                stable_count = 0
                                last_html = current_html
                        else:
                            print(f"   ⏳ Aguardando ícones... ({waited}s)")
            except Exception as e:
                print(f"   ⚠️ Erro ao verificar: {e}")
            
            print(f"   ⏳ Processando... ({waited}s)")
        
        if not results_ready:
            print("   ⚠️ Timeout - aguardando tempo extra antes de extrair...")
            time.sleep(WAIT_RENDER)  # Tempo extra de segurança
        
        print("   📊 Extraindo dados da tabela...")
        
        # Estrutura de resultados - TUDO começa como False/NÃO VALIDADO
        results = {
            'nome_arquivo': os.path.basename(pdf_path),
            'tamanho_bytes': os.path.getsize(pdf_path),
            'data_validacao': time.strftime('%Y-%m-%d %H:%M:%S'),
            'extensao_valida': False,
            'sem_senha': False,
            'tamanho_arquivo_ok': False,
            'tamanho_pagina_ok': False,
            'assinado': False,
            'numero_assinaturas': 0,
            'autenticidade_ok': False,
            'integridade_ok': False,
            'pesquisavel': False,
            'resultado_final': 'NÃO VALIDADO',
            'pontuacao': 0,
            'titular_certificado': '',
            'emissor_certificado': '',
            'validade_certificado': '',
            'mensagem_erro': ''
        }
        
        try:
            # Pegar o HTML completo da página
            page_html = driver.page_source
            page_text = driver.find_element(By.TAG_NAME, 'body').text
            
            print(f"   📄 Texto da página ({len(page_text)} chars)")
            
            # Salvar HTML para debug
            with open('tcees_debug.html', 'w', encoding='utf-8') as f:
                f.write(page_html)
            
            # ESTRATÉGIA DEFINITIVA: 
            # O site usa 8 colunas com width: 12.5% cada
            # Cada coluna é um div.d-inline-block
            # Dentro tem span com fa-check text-success (OK) ou text-danger + fa-close (ERRO)
            
            # Encontrar todas as colunas de resultado (não os headers)
            # Os resultados ficam dentro de #validacoes-arquivo ou div similar
            try:
                resultado_container = driver.find_element(By.ID, 'validacoes-arquivo')
                colunas = resultado_container.find_elements(By.CSS_SELECTOR, 'div.d-inline-block')
                
                print(f"   📊 Colunas de resultado encontradas: {len(colunas)}")
                
                if len(colunas) >= 8:
                    # Ordem das colunas:
                    # 0: Extensão, 1: Sem senha, 2: Tamanho arquivo, 3: Tamanho página
                    # 4: Assinado, 5: Autenticidade/Integridade, 6: Pesquisável, 7: Resultado final
                    
                    for i, coluna in enumerate(colunas[:8]):
                        coluna_html = coluna.get_attribute('innerHTML').lower()
                        
                        # Verificar se tem check verde ou X vermelho
                        is_ok = 'fa-check' in coluna_html and 'text-success' in coluna_html
                        is_error = 'text-danger' in coluna_html or 'fa-close' in coluna_html or 'fa-times' in coluna_html
                        
                        campo_valido = is_ok and not is_error
                        
                        if i == 0:
                            results['extensao_valida'] = campo_valido
                            print(f"      {'✓' if campo_valido else '✗'} Extensão: {campo_valido}")
                        elif i == 1:
                            results['sem_senha'] = campo_valido
                            print(f"      {'✓' if campo_valido else '✗'} Sem senha: {campo_valido}")
                        elif i == 2:
                            results['tamanho_arquivo_ok'] = campo_valido
                            print(f"      {'✓' if campo_valido else '✗'} Tamanho arquivo: {campo_valido}")
                        elif i == 3:
                            results['tamanho_pagina_ok'] = campo_valido
                            print(f"      {'✓' if campo_valido else '✗'} Tamanho página: {campo_valido}")
                        elif i == 4:
                            results['assinado'] = campo_valido
                            results['numero_assinaturas'] = 1 if campo_valido else 0
                            print(f"      {'✓' if campo_valido else '✗'} Assinado: {campo_valido}")
                        elif i == 5:
                            results['autenticidade_ok'] = campo_valido
                            results['integridade_ok'] = campo_valido
                            # Capturar mensagem de erro se houver
                            if not campo_valido:
                                if 'não assinado' in coluna_html or 'nao assinado' in coluna_html:
                                    results['mensagem_erro'] = 'Arquivo não assinado'
                            print(f"      {'✓' if campo_valido else '✗'} Autenticidade/Integridade: {campo_valido}")
                        elif i == 6:
                            results['pesquisavel'] = campo_valido
                            print(f"      {'✓' if campo_valido else '✗'} Pesquisável: {campo_valido}")
                        elif i == 7:
                            if campo_valido:
                                results['resultado_final'] = 'VALIDADO'
                            else:
                                results['resultado_final'] = 'NÃO VALIDADO'
                            print(f"      {'✓' if campo_valido else '✗'} Resultado: {results['resultado_final']}")
                            
            except Exception as e:
                print(f"   ⚠️ Método por colunas falhou: {e}")
                # Fallback: verificar texto "não assinado"
                if 'não assinado' in page_text.lower() or 'nao assinado' in page_text.lower():
                    results['assinado'] = False
                    results['autenticidade_ok'] = False
                    results['integridade_ok'] = False
                    results['resultado_final'] = 'NÃO VALIDADO'
                    results['mensagem_erro'] = 'Arquivo não assinado'
                    print("   ⚠️ DETECTADO: Arquivo não assinado!")
            
            # Calcular pontuação baseada nos campos que estão OK
            campos_ok = sum([
                results['extensao_valida'],
                results['sem_senha'],
                results['tamanho_arquivo_ok'],
                results['tamanho_pagina_ok'],
                results['assinado'],
                results['autenticidade_ok'],
                results['pesquisavel']
            ])
            
            results['pontuacao'] = int((campos_ok / 7) * 100)
            
                
        except Exception as e:
            print(f"   ⚠️ Erro ao extrair dados: {e}")
            import traceback
            traceback.print_exc()
        
        # Log detalhado dos resultados
        print("\n   📋 RESULTADOS DA VALIDAÇÃO:")
        print(f"      📄 Arquivo: {results['nome_arquivo']}")
        print(f"      {'✓' if results['extensao_valida'] else '✗'} Extensão Válida: {results['extensao_valida']}")
        print(f"      {'✓' if results['sem_senha'] else '✗'} Sem Senha: {results['sem_senha']}")
        print(f"      {'✓' if results['tamanho_arquivo_ok'] else '✗'} Tamanho OK: {results['tamanho_arquivo_ok']}")
        print(f"      {'✓' if results['tamanho_pagina_ok'] else '✗'} Tamanho Página OK: {results['tamanho_pagina_ok']}")
        print(f"      {'✓' if results['assinado'] else '✗'} Assinado: {results['assinado']} ({results['numero_assinaturas']} assinatura(s))")
        print(f"      {'✓' if results['autenticidade_ok'] else '✗'} Autenticidade: {results['autenticidade_ok']}")
        print(f"      {'✓' if results['integridade_ok'] else '✗'} Integridade: {results['integridade_ok']}")
        print(f"      {'✓' if results['pesquisavel'] else '✗'} Pesquisável: {results['pesquisavel']}")
        print(f"      🎯 Resultado Final: {results['resultado_final']}")
        print(f"      📊 Pontuação: {results['pontuacao']}/100")
        
        return results
        
    except Exception as e:
        print(f"   ❌ ERRO na validação TCEES: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Salvar screenshot para debug
        if driver:
            try:
                screenshot_path = os.path.join(os.path.dirname(pdf_path), 'tcees_error_screenshot.png')
                driver.save_screenshot(screenshot_path)
                print(f"   📸 Screenshot salvo: {screenshot_path}")
            except:
                pass
        
        return {
            'nome_arquivo': os.path.basename(pdf_path),
            'extensao_valida': False,
            'sem_senha': False,
            'tamanho_arquivo_ok': False,
            'tamanho_pagina_ok': False,
            'assinado': False,
            'numero_assinaturas': 0,
            'autenticidade_ok': False,
            'integridade_ok': False,
            'pesquisavel': False,
            'resultado_final': 'ERRO',
            'pontuacao': 0,
            'titular_certificado': '',
            'emissor_certificado': '',
            'validade_certificado': '',
            'erro': str(e)
        }
        
    finally:
        if driver:
            try:
                driver.quit()
                print("   🔒 Navegador fechado\n")
            except:
                pass


def validate_multiple_pdfs(pdf_paths, max_workers=3):
    """
    Valida múltiplos PDFs em paralelo usando ThreadPoolExecutor
    
    Args:
        pdf_paths: Lista de caminhos para arquivos PDF (máximo 3)
        max_workers: Número máximo de validações simultâneas
        
    Returns:
        Lista de dicionários com resultados de cada validação (NA MESMA ORDEM dos inputs)
    """
    if not pdf_paths:
        return []
    
    # Limitar a 3 arquivos
    pdf_paths = pdf_paths[:3]
    
    print(f"\n🚀 Iniciando validação paralela de {len(pdf_paths)} documento(s)...")
    start_time = time.time()
    
    # Usar ThreadPoolExecutor para processar em paralelo
    with ThreadPoolExecutor(max_workers=min(max_workers, len(pdf_paths))) as executor:
        # Submeter todas as tarefas E MANTER A ORDEM usando map
        # executor.map preserva a ordem dos inputs
        try:
            results = list(executor.map(validate_pdf_with_tcees, pdf_paths))
        except Exception as e:
            print(f"❌ Erro na validação paralela: {e}")
            # Fallback: retornar erro para cada arquivo
            results = []
            for pdf_path in pdf_paths:
                results.append({
                    'nome_arquivo': os.path.basename(pdf_path),
                    'resultado_final': 'ERRO',
                    'erro': str(e)
                })
    
    total_time = time.time() - start_time
    print(f"\n✅ Validação paralela concluída em {total_time:.1f}s (média: {total_time/len(pdf_paths):.1f}s por documento)")
    
    return results


def test_tcees_validation():
    """Função de teste"""
    print("🧪 TESTE DE VALIDAÇÃO TCEES")
    print("=" * 60)
    
    # Procurar por um PDF de teste
    test_dir = os.path.dirname(os.path.abspath(__file__))
    uploads_dir = os.path.join(test_dir, 'uploads')
    
    if os.path.exists(uploads_dir):
        pdfs = [f for f in os.listdir(uploads_dir) if f.endswith('.pdf')]
        if pdfs:
            test_file = os.path.join(uploads_dir, pdfs[0])
            print(f"📄 Testando com: {pdfs[0]}\n")
            start = time.time()
            results = validate_pdf_with_tcees(test_file)
            elapsed = time.time() - start
            print(f"\n✅ Teste concluído em {elapsed:.1f}s!")
            print("\n📊 RESUMO COMPLETO:")
            import json
            print(json.dumps(results, indent=2, ensure_ascii=False))
            return results
    
    print("❌ Nenhum arquivo PDF encontrado para teste")
    return None


if __name__ == '__main__':
    test_tcees_validation()
