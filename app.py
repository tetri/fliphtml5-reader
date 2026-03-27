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

os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

def get_fliphtml5_pdf(url, progress_bar=None, status_text=None, optimize=False, quality=75):
    """
    Downloads images from a FlipHTML5 URL and converts them to a PDF.
    Returns the PDF bytes.
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    # Ensure URL ends with /
    if not url.endswith('/'):
        url += '/'

    try:
        if status_text: status_text.text("Obtendo índice da página...")
        page_index = requests.get(url, headers=headers, timeout=10)
        page_index.raise_for_status()
        soup = BeautifulSoup(page_index.content, 'html.parser')

        # Find the configuration script
        script_tags = soup.find_all(lambda tag: tag.name=='script' and tag.attrs.get('src', '').startswith('javascript'))
        if not script_tags:
            raise Exception("Não foi possível encontrar o script de configuração do FlipHTML5.")

        config_url = script_tags[0]['src']
        config_full_url = urljoin(url, config_url)

        if status_text: status_text.text("Obtendo configuração...")
        config_resp = requests.get(config_full_url, headers=headers, timeout=10)
        config_resp.raise_for_status()

        # The config is typically inside a JSON-like structure: window.viewerConfig = {...};
        # We need to extract the JSON part.
        json_str = config_resp.text
        start_idx = json_str.find('{')
        end_idx = json_str.rfind('}')
        if start_idx == -1 or end_idx == -1:
            raise Exception("Formato de configuração inválido.")

        config = json.loads(json_str[start_idx:end_idx+1])
        pages = [p['n'][0] for p in config['fliphtml5_pages']]

        if not pages:
            raise Exception("Nenhuma página encontrada no documento.")

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_paths = []
            total_pages = len(pages)

            for idx, page_path in enumerate(pages):
                pure_filename = os.path.basename(page_path)
                # Some fliphtml5 links use different paths, we try to be robust
                page_url = urljoin(url, 'files/large/' + pure_filename)

                if status_text: status_text.text(f"Baixando página {idx+1} de {total_pages}...")
                if progress_bar: progress_bar.progress((idx + 1) / total_pages)

                img_resp = requests.get(page_url, headers=headers, timeout=10)
                if img_resp.status_code == 200:
                    save_path = os.path.join(tmp_dir, f"{idx:04d}_{pure_filename}")
                    with open(save_path, 'wb') as f:
                        f.write(img_resp.content)

                    if optimize:
                        with Image.open(save_path) as img:
                            img.save(save_path, format=img.format, quality=quality)

                    image_paths.append(save_path)
                else:
                    # Fallback or error? For now, we continue if possible
                    st.warning(f"Falha ao baixar a página {idx+1}")

            if not image_paths:
                raise Exception("Nenhuma imagem pôde ser baixada.")

            if status_text: status_text.text("Gerando PDF...")
            pdf_bytes = img2pdf.convert(sorted(image_paths))
            return pdf_bytes

    except Exception as e:
        st.error(f"Erro: {str(e)}")
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
