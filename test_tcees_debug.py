"""
Script de teste para debugar a extração do TCEES
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

def test_tcees():
    # Encontrar um PDF para testar
    uploads_dir = 'uploads'
    pdfs = [f for f in os.listdir(uploads_dir) if f.endswith('.pdf')]
    
    if not pdfs:
        print("❌ Nenhum PDF encontrado na pasta uploads")
        return
    
    pdf_path = os.path.join(uploads_dir, pdfs[0])
    print(f"📄 Testando com: {pdf_path}")
    
    # Configurar Chrome (NÃO headless para ver o que acontece)
    chrome_options = Options()
    # chrome_options.add_argument('--headless')  # Comentado para ver a tela
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    
    print("🌐 Abrindo navegador...")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        # Acessar site
        url = 'https://conformidadepdf.tcees.tc.br/'
        print(f"📡 Acessando {url}...")
        driver.get(url)
        time.sleep(3)
        
        # Upload do arquivo
        print("📤 Fazendo upload...")
        file_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="file"]'))
        )
        file_input.send_keys(os.path.abspath(pdf_path))
        
        print("⏳ Aguardando 10 segundos para processamento...")
        time.sleep(10)
        
        # Salvar screenshot
        driver.save_screenshot('debug_screenshot.png')
        print("📸 Screenshot salvo: debug_screenshot.png")
        
        # Salvar HTML
        with open('debug_page.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print("💾 HTML salvo: debug_page.html")
        
        # Mostrar texto da página
        body_text = driver.find_element(By.TAG_NAME, 'body').text
        print("\n" + "="*60)
        print("📄 TEXTO DA PÁGINA:")
        print("="*60)
        print(body_text)
        print("="*60)
        
        # Procurar checkmarks
        print("\n🔍 Procurando checkmarks no texto...")
        print(f"   ✓ encontrados: {body_text.count('✓')}")
        print(f"   ✔ encontrados: {body_text.count('✔')}")
        
        # Listar elementos TH
        print("\n📋 Elementos TH (cabeçalhos):")
        ths = driver.find_elements(By.TAG_NAME, 'th')
        for i, th in enumerate(ths):
            print(f"   {i}: '{th.text}'")
        
        # Listar elementos TD
        print("\n📋 Elementos TD (células):")
        tds = driver.find_elements(By.TAG_NAME, 'td')
        for i, td in enumerate(tds):
            text = td.text.strip()
            html = td.get_attribute('innerHTML')[:100]
            print(f"   {i}: texto='{text}' | html_preview='{html}'")
        
        # Procurar por SVG ou ícones
        print("\n🎨 Elementos SVG:")
        svgs = driver.find_elements(By.TAG_NAME, 'svg')
        print(f"   Total: {len(svgs)}")
        
        print("\n🎨 Elementos com class contendo 'check':")
        checks = driver.find_elements(By.XPATH, "//*[contains(@class, 'check')]")
        for c in checks:
            print(f"   Tag: {c.tag_name}, Class: {c.get_attribute('class')}")
        
        print("\n🎨 Elementos com class contendo 'success' ou 'valid':")
        success = driver.find_elements(By.XPATH, "//*[contains(@class, 'success') or contains(@class, 'valid')]")
        for s in success:
            print(f"   Tag: {s.tag_name}, Class: {s.get_attribute('class')}")
        
        input("\n⏸️ Pressione ENTER para fechar o navegador...")
        
    finally:
        driver.quit()
        print("🔒 Navegador fechado")

if __name__ == '__main__':
    test_tcees()
