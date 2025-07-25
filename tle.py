# tle.py
import requests
import urllib3

# Desativa os avisos de "conexão insegura" que apareceriam no console
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fetch_tle_from_url(url: str) -> str | None:
    """
    Busca o conteúdo de uma URL de TLE, ignorando a verificação SSL
    e usando um User-Agent de navegador.
    """
    # --- NOVIDADE: Adiciona um cabeçalho para simular um navegador ---
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        # verify=False para ignorar erro de certificado
        # headers=headers para evitar o erro 403 Forbidden
        response = requests.get(url, timeout=15, verify=False, headers=headers)
        
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"❌ Falha ao buscar TLE da URL {url}: {e}")
        return None