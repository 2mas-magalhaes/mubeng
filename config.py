# config.py

# =======================================================
# --- CONFIGURAÇÕES DO PROXY MANAGER SERVICE (API) ---
# --- (Estas variáveis serão ignoradas pelo checker) ---
# =======================================================

REQUESTS_PER_PROXY = 22
COOLDOWN_TIME_SECONDS = 301  # 5 minutos


# =======================================================
# --- CONFIGURAÇÕES DO PROXY CHECKER (check_steam_proxies.py) ---
# =======================================================

CHECKER_INPUT_FILE = r".\live.txt"
CHECKER_OUTPUT_FILE = r".\steam_live.txt"

CHECKER_VALIDATION_URL = "https://steamcommunity.com/market/search/render/?query=&start=10&count=10&search_descriptions=0&sort_column=popular&sort_dir=desc"

# --- CORRIGIDO ---
# O texto de validação deve procurar por "success":true na resposta da API (JSON),
# e não pelo código HTML antigo. Esta é a correção mais importante.
CHECKER_VALIDATION_TEXT = '"success":true'

# --- ADICIONADO ---
# Cabeçalhos (Headers) necessários para que o pedido à API da Steam seja aceite.
CHECKER_HEADERS = {
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://steamcommunity.com/market/search?appid=730'
}

CHECKER_CONCURRENCY = 500
CHECKER_TIMEOUT_SEC = 4
CHECKER_LOOPSLEEP_SEC = 2

# A variável CHECKER_RETRY_COUNT não é usada na versão atual do script aiohttp,
# mas pode ser mantida aqui para uso futuro.
CHECKER_RETRY_COUNT = 1

# --- MODO DE DEPURAÇÃO ---
CHECKER_DEBUG_MODE = False
CHECKER_DEBUG_LOG_FILE = "steam_debug.log"