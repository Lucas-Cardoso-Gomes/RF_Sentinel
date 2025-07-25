# tle.py
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fetch_tle_from_url(url: str) -> str | None:
    """Busca o conteúdo TLE de uma URL usando um User-Agent de navegador."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, timeout=15, verify=False, headers=headers)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"❌ Falha ao buscar grupo TLE da URL {url}: {e}")
        return None

def extract_tle_from_group(tle_group_text: str, satellite_name: str) -> list[str] | None:
    """
    Extrai as 3 linhas de TLE para um satélite específico de um texto que contém vários.
    """
    lines = tle_group_text.strip().splitlines()
    try:
        # Encontra a linha que corresponde ao nome do satélite
        # .strip() é crucial para remover espaços extras
        idx = [i for i, line in enumerate(lines) if satellite_name.strip() == line.strip()][0]
        
        # O TLE são as 3 linhas: nome, linha 1, linha 2
        return lines[idx:idx+3]
    except IndexError:
        # O satélite não foi encontrado no grupo
        return None