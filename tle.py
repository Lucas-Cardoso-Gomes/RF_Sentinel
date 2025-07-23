# tle.py
import requests
import urllib3

# Desativa os avisos de "conexão insegura" que apareceriam no console
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fetch_tle_from_url(url: str) -> str | None:
    """
    Busca o conteúdo de uma URL de TLE, ignorando a verificação SSL.

    Args:
        url: A URL do arquivo TLE (ex: do Celestrak).

    Returns:
        O conteúdo do TLE como uma string, ou None se ocorrer um erro.
    """
    try:
        # verify=False é a chave para ignorar o erro de certificado
        response = requests.get(url, timeout=15, verify=False)
        
        # Levanta um erro para status ruins como 404 ou 500
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"❌ Falha ao buscar TLE da URL {url}: {e}")
        return None