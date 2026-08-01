import json
import os
import requests
from bs4 import BeautifulSoup
import certifi
import img2pdf
import streamlit as st
import tempfile
from urllib.parse import urljoin, urlparse
from PIL import Image
import concurrent.futures

os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

def download_page(idx, page_path, url, session, tmp_dir, optimize, quality):
    pure_filename = os.path.basename(page_path)
    page_url = urljoin(url, 'files/large/' + pure_filename)

    img_resp = session.get(page_url, timeout=10)
    if img_resp.status_code == 200:
        save_path = os.path.join(tmp_dir, f"{idx:04d}_{pure_filename}")
        with open(save_path, 'wb') as f:
            f.write(img_resp.content)

        if optimize:
            with Image.open(save_path) as img:
                img.save(save_path, format=img.format, quality=quality)

        return save_path, None
    else:
        return None, f"Falha ao baixar a página {idx+1}"

def get_pdf_via_playwright(url, progress_bar=None, status_text=None, optimize=False, quality=75):
    from playwright.sync_api import sync_playwright
    import time
    
    if status_text: status_text.text("Iniciando navegador headless para extrair publicação encriptada...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 960})
        page = context.new_page()
        
        captured_images = {}
        page.on('response', lambda r: captured_images.update({r.url: True}) if ('files/large/' in r.url) else None)
        
        if status_text: status_text.text("Carregando leitor do FlipHTML5...")
        page.goto(url)
        page.wait_for_load_state('networkidle')
        time.sleep(2)
        
        total_pages = page.evaluate('''() => {
            var c = window.htmlConfig || window.viewerConfig;
            return c ? (c.search_pages ? c.search_pages.length : 0) : 0;
        }''')
        
        if not total_pages:
            total_pages = 20 # Fallback padrão se não puder ler a contagem
            
        if status_text: status_text.text(f"Navegando e capturando {total_pages} páginas...")
        
        for i in range(total_pages):
            page.keyboard.press('ArrowRight')
            time.sleep(0.8)
            if progress_bar:
                progress_bar.progress(min(1.0, (i + 1) / total_pages))
            if status_text:
                status_text.text(f"Capturando páginas ({i+1}/{total_pages})...")
                
        time.sleep(2)
        browser.close()
        
        image_urls = list(captured_images.keys())
        if not image_urls:
            raise Exception("Não foi possível interceptar as imagens das páginas.")
            
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_paths = []
            for idx, img_url in enumerate(image_urls):
                resp = session.get(img_url, timeout=10)
                if resp.status_code == 200:
                    ext = '.webp' if '.webp' in img_url else '.jpg'
                    save_path = os.path.join(tmp_dir, f"{idx:04d}{ext}")
                    with open(save_path, 'wb') as f:
                        f.write(resp.content)
                    
                    if optimize or ext == '.webp':
                        with Image.open(save_path) as img:
                            rgb_img = img.convert('RGB')
                            rgb_img.save(save_path, format='JPEG', quality=quality)
                    
                    image_paths.append(save_path)
            
            image_paths.sort()
            if status_text: status_text.text("Gerando arquivo PDF final...")
            pdf_bytes = img2pdf.convert(image_paths)
            return pdf_bytes

def get_fliphtml5_pdf(url, progress_bar=None, status_text=None, optimize=False, quality=75):
    """
    Downloads images from a FlipHTML5 URL and converts them to a PDF.
    Returns the PDF bytes.
    """
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})

    if not url.endswith('/'):
        url += '/'

    try:
        if status_text: status_text.text("Obtendo índice da página...")
        page_index = session.get(url, timeout=10)
        page_index.raise_for_status()
        soup = BeautifulSoup(page_index.content, 'html.parser')

        script_tags = soup.find_all(lambda tag: tag.name=='script' and tag.attrs.get('src', '').startswith('javascript'))
        if not script_tags:
            raise Exception("Não foi possível encontrar o script de configuração do FlipHTML5.")

        config_url = script_tags[0]['src']
        config_full_url = urljoin(url, config_url)

        if status_text: status_text.text("Obtendo configuração...")
        config_resp = session.get(config_full_url, timeout=10)
        config_resp.raise_for_status()

        json_str = config_resp.text
        start_idx = json_str.find('{')
        end_idx = json_str.rfind('}')
        if start_idx == -1 or end_idx == -1:
            raise Exception("Formato de configuração inválido.")

        config = json.loads(json_str[start_idx:end_idx+1])
        pages_raw = config.get('fliphtml5_pages')

        pages = []
        if isinstance(pages_raw, list):
            pages = [p['n'][0] for p in pages_raw if isinstance(p, dict) and 'n' in p]
        elif isinstance(pages_raw, str):
            # Se a publicação for encriptada (fliphtml5_pages é string), dispara o fallback com Playwright
            st.info("Publicação encriptada detectada! Acionando modo de captura headless...")
            return get_pdf_via_playwright(url, progress_bar, status_text, optimize, quality)

        if not pages:
            st.info("Estrutura não padrão detectada! Acionando modo de captura headless...")
            return get_pdf_via_playwright(url, progress_bar, status_text, optimize, quality)

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_paths = []
            total_pages = len(pages)
            completed_pages = 0

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_idx = {
                    executor.submit(download_page, idx, page_path, url, session, tmp_dir, optimize, quality): idx
                    for idx, page_path in enumerate(pages)
                }

                for future in concurrent.futures.as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        save_path, error = future.result()
                        if save_path:
                            image_paths.append(save_path)
                        if error:
                            st.warning(error)
                    except Exception as exc:
                        st.warning(f"Falha ao baixar a página {idx+1}: {exc}")

                    completed_pages += 1
                    if status_text: status_text.text(f"Baixadas {completed_pages} de {total_pages} páginas...")
                    if progress_bar: progress_bar.progress(completed_pages / total_pages)

            if not image_paths:
                raise Exception("Nenhuma imagem pôde ser baixada.")

            image_paths.sort()

            if status_text: status_text.text("Gerando PDF...")
            pdf_bytes = img2pdf.convert(image_paths)
            return pdf_bytes

    except Exception as e:
        st.warning(f"Tentando modo alternativo devido a: {str(e)}")
        try:
            return get_pdf_via_playwright(url, progress_bar, status_text, optimize, quality)
        except Exception as fallback_err:
            st.error(f"Erro ao processar a publicação: {str(fallback_err)}")
            st.info("Dica: Certifique-se de que a URL inserida é uma publicação pública do FlipHTML5 válida.")
            return None

def main():
    st.set_page_config(page_title="FlipHTML5 to PDF Downloader", page_icon="📄")
    
    st.title("📄 FlipHTML5 to PDF Downloader")
    st.write("Insira a URL do FlipHTML5 abaixo para gerar o PDF completo.")

    url = st.text_input("URL do FlipHTML5", placeholder="https://online.fliphtml5.com/xxxx/yyyy/")

    optimize = st.checkbox("Otimizar imagens (reduz o tamanho do PDF)", value=False)
    quality = st.slider("Qualidade da compressão", 1, 100, 80, disabled=not optimize)

    if st.button("Gerar PDF"):
        if not url:
            st.error("Por favor, informe uma URL.")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()

            pdf_data = get_fliphtml5_pdf(url, progress_bar, status_text, optimize, quality)

            if pdf_data:
                status_text.success("PDF gerado com sucesso!")
                st.download_button(
                    label="Baixar PDF",
                    data=pdf_data,
                    file_name="documento.pdf",
                    mime="application/pdf"
                )

if __name__ == "__main__":
    main()
