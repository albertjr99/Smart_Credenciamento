"""
Debug do site TCEES para entender a estrutura HTML
Executa SEM headless para ver o que está acontecendo
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import os

def debug_tcees(pdf_path):
    print(f"\n🔍 DEBUG TCEES: {os.path.basename(pdf_path)}")
    
    chrome_options = Options()
    # SEM headless para visualizar
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        url = 'https://conformidadepdf.tcees.tc.br/'
        driver.get(url)
        time.sleep(3)
        
        # Upload do arquivo
        file_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="file"]'))
        )
        file_input.send_keys(os.path.abspath(pdf_path))
        print("   ✅ Arquivo enviado!")
        
        # Aguardar processamento
        print("   ⏳ Aguardando 25 segundos...")
        time.sleep(25)
        
        # Salvar HTML
        html = driver.page_source
        with open('tcees_page.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print("   📄 HTML salvo em tcees_page.html")
        
        # Salvar screenshot
        driver.save_screenshot('tcees_screenshot.png')
        print("   📸 Screenshot salvo em tcees_screenshot.png")
        
        # Analisar a estrutura
        print("\n" + "="*60)
        print("ANÁLISE DA ESTRUTURA HTML")
        print("="*60)
        
        # Encontrar a tabela/grid de resultados
        # Procurar por elementos com os textos dos campos
        campos = ['Extensão', 'Sem senha', 'Tamanho do arquivo', 'Tamanho por página', 
                  'Assinado', 'Autenticidade e Integridade', 'Pesquisável', 'Resultado final']
        
        for campo in campos:
            print(f"\n📌 Campo: {campo}")
            
            try:
                # Encontrar elemento com o texto
                elementos = driver.find_elements(By.XPATH, f"//*[contains(text(), '{campo}')]")
                print(f"   Elementos encontrados: {len(elementos)}")
                
                for i, elem in enumerate(elementos):
                    try:
                        tag = elem.tag_name
                        classes = elem.get_attribute('class') or ''
                        parent = elem.find_element(By.XPATH, './..')
                        parent_tag = parent.tag_name
                        parent_class = parent.get_attribute('class') or ''
                        
                        print(f"   [{i}] <{tag} class='{classes}'> dentro de <{parent_tag} class='{parent_class}'>")
                        
                        # Verificar irmãos
                        siblings = parent.find_elements(By.XPATH, './*')
                        print(f"       Irmãos: {[s.tag_name for s in siblings]}")
                        
                        # Verificar se há SVG no mesmo container
                        svgs = parent.find_elements(By.TAG_NAME, 'svg')
                        print(f"       SVGs no parent: {len(svgs)}")
                        
                        # Verificar cores (classe de sucesso ou erro)
                        parent_html = parent.get_attribute('innerHTML')[:500]
                        if 'text-success' in parent_html or '#28a745' in parent_html or 'green' in parent_html.lower():
                            print(f"       🟢 VERDE/SUCCESS detectado")
                        if 'text-danger' in parent_html or '#dc3545' in parent_html or 'red' in parent_html.lower():
                            print(f"       🔴 VERMELHO/DANGER detectado")
                        if 'não assinado' in parent_html.lower():
                            print(f"       ⚠️ 'Não assinado' encontrado!")
                            
                    except Exception as e:
                        print(f"   Erro: {e}")
                        
            except Exception as e:
                print(f"   ❌ Erro: {e}")
        
        # Procurar por padrão de X (erro)
        print("\n" + "="*60)
        print("PROCURANDO ÍCONES DE ERRO (X)")
        print("="*60)
        
        # Procurar por elementos com classe danger/error/x
        danger_elements = driver.find_elements(By.CSS_SELECTOR, '.text-danger, .danger, [class*="error"], [class*="invalid"]')
        print(f"Elementos com classe danger/error: {len(danger_elements)}")
        
        for elem in danger_elements[:10]:
            print(f"   - {elem.tag_name}: {elem.text[:50] if elem.text else '[vazio]'}")
        
        # Procurar por texto "não assinado"
        not_signed = driver.find_elements(By.XPATH, "//*[contains(text(), 'não assinado')]")
        print(f"\nTexto 'não assinado' encontrado: {len(not_signed)}")
        
        # Aguardar input do usuário
        input("\n⏸️ Pressione ENTER para fechar o navegador...")
        
    finally:
        driver.quit()

if __name__ == '__main__':
    uploads = os.path.join(os.path.dirname(__file__), 'uploads')
    pdfs = [f for f in os.listdir(uploads) if f.endswith('.pdf')]
    if pdfs:
        debug_tcees(os.path.join(uploads, pdfs[0]))
    else:
        print("Nenhum PDF encontrado")
