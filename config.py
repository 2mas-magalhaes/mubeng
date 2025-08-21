# proxy_steam_manager/config.py

# =======================================================
# --- CONFIGURAÇÕES DO PROXY MANAGER SERVICE (API) ---
# =======================================================

REQUESTS_PER_PROXY = 23

COOLDOWN_TIME_SECONDS = 300  # 5 minutos


# =======================================================
# --- CONFIGURAÇÕES DO PROXY CHECKER (check_steam_proxies.py) ---
# =======================================================

CHECKER_INPUT_FILE = r".\live.txt"
CHECKER_OUTPUT_FILE = r".\steam_live.txt"

CHECKER_VALIDATION_URL = "https://steamcommunity.com/market/search/render/?query=&start=10&count=10&search_descriptions=0&sort_column=popular&sort_dir=desc"

CHECKER_LOOPSLEEP_SEC = 5

# --- CORRIGIDO ---
# Adicionado o espaço em falta para corresponder exatamente ao HTML da Steam.
CHECKER_VALIDATION_TEXT = '<html class=" responsive DesktopUI"'

CHECKER_CONCURRENCY = 300
CHECKER_TIMEOUT_SEC = 4
CHECKER_RETRY_COUNT = 2

# --- MODO DE DEPURAÇÃO ---
# Pode desativar isto (mudar para False) quando confirmar que tudo funciona,
# para não gerar ficheiros de log desnecessários.
CHECKER_DEBUG_MODE = True
CHECKER_DEBUG_LOG_FILE = "steam_debug.log"