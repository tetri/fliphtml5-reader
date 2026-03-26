import json
import os
import requests
from bs4 import BeautifulSoup
import certifi

import img2pdf

os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

#page_index_url = "https://online.fliphtml5.com/nrbfc/pfhy/"
#page_index_url = "https://online.fliphtml5.com/nrbfc/tjpx/"
#page_index_url = "https://online.fliphtml5.com/nrbfc/yziu/"
page_index_url = "https://online.fliphtml5.com/nrbfc/ongi/"


# 1. Especificando o parser 'html.parser' para evitar o aviso
page_index = requests.get(page_index_url, headers={'User-Agent': 'Mozilla/5.0...'}, timeout=10)
soup = BeautifulSoup(page_index.content, 'html.parser')

config_script_tag = soup.find_all(lambda tag: tag.name=='script' and tag.attrs.get('src', '').startswith('javascript'))[0]
config_url = config_script_tag['src']
config_resp = requests.get(page_index_url + config_url, headers={'User-Agent': 'Mozilla/5.0...'}, timeout=10)

config = json.loads(config_resp.text[17:-1])
pages = [p['n'][0] for p in config['fliphtml5_pages']]

# Criar pasta para salvar se não existir
if not os.path.exists('downloads'):
    os.makedirs('downloads')

for idx, page_path in enumerate(pages):
    # page_path pode vir como './files/large/imagem.webp'
    # Extraímos apenas 'imagem.webp'
    pure_filename = os.path.basename(page_path)
    
    page_url = page_index_url + 'files/large/' + pure_filename
    save_path = os.path.join('downloads', f"{1+idx:04}-{pure_filename}")
    
    print(f"Baixando: {save_path}")
    
    one_page_resp = requests.get(page_url, headers={'User-Agent': 'Mozilla/5.0...'}, timeout=10)
    
    if one_page_resp.status_code == 200:
        with open(save_path, 'wb') as f:
            f.write(one_page_resp.content)

def generate_pdf(image_folder, output_pdf):
    print(f"Gerando PDF: {output_pdf}...")
    
    # Lista todos os arquivos .webp na pasta e ordena alfabeticamente
    # A ordenação pelo prefixo 0001, 0002 garante a sequência correta
    images = [
        os.path.join(image_folder, f) 
        for f in sorted(os.listdir(image_folder)) 
        if f.endswith('.webp')
    ]

    if not images:
        print("Nenhuma imagem encontrada para gerar o PDF.")
        return

    # Converte a lista de imagens para um único PDF
    with open(output_pdf, "wb") as f:
        f.write(img2pdf.convert(images))
    
    print(f"Sucesso! PDF gerado em: {os.path.abspath(output_pdf)}")

# Executa a função após o loop de download
generate_pdf('downloads', 'resultado_fliphtml5.pdf')