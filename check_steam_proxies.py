import asyncio
import os
import sys
import threading
from contextlib import suppress
from typing import Optional
from datetime import datetime

# --- Tenta importar as bibliotecas e avisa o utilizador se não estiverem instaladas ---
try:
    import aiohttp
    # --- MUDANÇA CRÍTICA: Importar do pacote correto 'aiohttp_socks' ---
    from aiohttp_socks import ProxyConnector
    from tqdm.asyncio import tqdm
except ImportError:
    print("Erro: Bibliotecas necessárias não encontradas. Por favor, instale-as com:")
    print("python -m pip install aiohttp aiohttp_socks tqdm")
    sys.exit(1)

# =======================================================
# --- CONFIGURAÇÕES ---
# =======================================================
INPUT_FILE = "live.txt"
OUTPUT_FILE = "steam_live.txt"
STEAM_URL = "https://steamcommunity.com/market/search/render/?query=&start=10&count=10&search_descriptions=0&sort_column=popular&sort_dir=desc"
VALIDATION_TEXT = '"success":true'
CONCURRENCY_LIMIT = 300
REQUEST_TIMEOUT = 5
LOOPSLEEP_SEC = 5
HEADERS = {
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://steamcommunity.com/market/search?appid=730'
}
DEBUG_MODE = True
DEBUG_LOG_FILE = "steam_debug_api.log"

log_lock = threading.Lock()

def write_log_sync(log_message: str):
    """Função síncrona que escreve no ficheiro. Será executada num thread separado."""
    try:
        with log_lock:
            with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_message)
    except Exception as e:
        print(f"ERRO CRÍTICO AO ESCREVER NO LOG: {e}", flush=True)

async def log_debug(proxy: str, stage: str, details: str):
    """Regista logs de forma segura e não-bloqueante."""
    if not DEBUG_MODE:
        return
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_message = f"[{timestamp}] PROXY {proxy} | {stage}\nDETAILS: {details}\n--- END ---\n\n"
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, write_log_sync, log_message)


async def check_proxy(proxy: str) -> Optional[str]:
    """Testa um proxy contra a API da Steam."""
    await log_debug(proxy, "TASK_START", "Iniciando verificação")
    try:
        # Esta linha continua a funcionar porque o método .from_url é o mesmo
        connector = ProxyConnector.from_url(proxy)
    except Exception as e:
        await log_debug(proxy, "INVALID_PROXY_FORMAT", f"{type(e).__name__}: {e}")
        return None

    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(STEAM_URL, headers=HEADERS) as response:
                await log_debug(proxy, "HTTP_RESPONSE", f"Status: {response.status}")
                if response.status == 200:
                    text = await response.text()
                    if VALIDATION_TEXT in text:
                        await log_debug(proxy, "SUCCESS", "Proxy válido ✅")
                        return proxy
                    else:
                        await log_debug(proxy, "VALIDATION_FAIL", "Texto de validação não encontrado ❌")
                else:
                    await log_debug(proxy, "BAD_STATUS", f"Recebido status {response.status}")
    except Exception as e:
        error_type = type(e).__name__
        await log_debug(proxy, "ERROR", f"{error_type}: {e}")
    return None

async def main():
    """Loop principal que lê, testa e guarda os proxies."""
    print("🚀 Iniciando verificação de proxies contra a API do Steam Market...", flush=True)
    if DEBUG_MODE:
        print(f"🐛 MODO DEBUG ATIVO. Logs detalhados em '{DEBUG_LOG_FILE}'", flush=True)
        with suppress(FileNotFoundError):
            if os.path.exists(DEBUG_LOG_FILE):
                os.remove(DEBUG_LOG_FILE)

    while True:
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            try:
                with open(INPUT_FILE, "r", encoding="utf-8") as f:
                    proxies_to_check = sorted(list(set(line.strip() for line in f if line.strip())))
            except FileNotFoundError:
                print(f"[{timestamp}] Ficheiro '{INPUT_FILE}' não encontrado. Aguardando...", flush=True)
                await asyncio.sleep(LOOPSLEEP_SEC)
                continue
            if not proxies_to_check:
                print(f"[{timestamp}] Ficheiro '{INPUT_FILE}' está vazio. Verificando novamente...", flush=True)
                await asyncio.sleep(LOOPSLEEP_SEC)
                continue

            sem = asyncio.Semaphore(CONCURRENCY_LIMIT)
            tasks = [limited_check(proxy, sem) for proxy in proxies_to_check]
            validated_proxies = []
            progress_bar = tqdm(asyncio.as_completed(tasks), total=len(proxies_to_check), desc=f"[{timestamp}] Verificando", unit="proxy")
            for task_future in progress_bar:
                result = await task_future
                if result:
                    validated_proxies.append(result)
                progress_bar.set_postfix({'Válidos': len(validated_proxies)})

            timestamp_end = datetime.now().strftime("%H:%M:%S")
            if validated_proxies:
                print(f"\n[{timestamp_end}] {len(validated_proxies)} / {len(proxies_to_check)} proxies válidos ✅", flush=True)
                temp_file = OUTPUT_FILE + ".tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(sorted(validated_proxies)))
                os.replace(temp_file, OUTPUT_FILE)
            else:
                print(f"\n[{timestamp_end}] Nenhum proxy válido encontrado ❌", flush=True)
                with suppress(FileNotFoundError):
                    if os.path.exists(OUTPUT_FILE):
                        os.remove(OUTPUT_FILE)
        except Exception as e:
            print(f"[{timestamp}] Erro geral no loop principal: {type(e).__name__}: {e}", flush=True)
        print(f"⏳ Aguardando {LOOPSLEEP_SEC} segundos para a próxima ronda...\n", flush=True)
        await asyncio.sleep(LOOPSLEEP_SEC)

async def limited_check(proxy: str, sem: asyncio.Semaphore) -> Optional[str]:
    """Wrapper para respeitar o limite de concorrência."""
    async with sem:
        return await check_proxy(proxy)

if __name__ == "__main__":
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Interrompido pelo utilizador. Saindo...")