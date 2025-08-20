import asyncio
import os
from contextlib import suppress
from typing import List, Optional
from datetime import datetime

import aiohttp
from aiohttp_proxy import ProxyConnector
from tqdm.asyncio import tqdm

# --- CONFIGURAÇÃO ---
INPUT_FILE = "live.txt"
OUTPUT_FILE = "steam_live.txt"
STEAM_URL = "https://store.steampowered.com/"
CONCURRENCY_LIMIT = 200
REQUEST_TIMEOUT = 5
VALIDATION_TEXT = "<title>Welcome to Steam</title>"


async def check_proxy(proxy: str) -> Optional[str]:
    """
    Testa um único proxy contra o URL da Steam de forma assíncrona.
    Retorna o próprio proxy se for válido, caso contrário retorna None.
    """
    try:
        connector = ProxyConnector.from_url(proxy)
        
        async with aiohttp.ClientSession(connector=connector) as proxy_session:
            async with proxy_session.get(
                STEAM_URL,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            ) as response:
                if response.status == 200:
                    text = await response.text()
                    if VALIDATION_TEXT in text:
                        return proxy
    except Exception:
        pass
    
    return None

async def main():
    """Loop principal que lê, testa e guarda os proxies."""
    print("Iniciando script de verificação de proxies contra a STEAM (Modo Python Async)...", flush=True)
    print(f"Lendo de '{INPUT_FILE}', escrevendo proxies válidos para '{OUTPUT_FILE}'.", flush=True)
    print(f"Testando com uma concorrência de {CONCURRENCY_LIMIT} e timeout de {REQUEST_TIMEOUT}s.", flush=True)

    while True:
        try:
            # CORREÇÃO: A timestamp é agora obtida diretamente, sem criar uma coroutine reutilizada.
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # 1. LER O FICHEIRO DE ENTRADA
            try:
                with open(INPUT_FILE, 'r', encoding='utf-8') as f:
                    # Filtra linhas duplicadas para evitar trabalho desnecessário
                    proxies_to_check = sorted(list(set(line.strip() for line in f if line.strip())))
            except FileNotFoundError:
                print(f"[{timestamp}] Aguardando... Ficheiro de entrada '{INPUT_FILE}' não encontrado.", flush=True)
                await asyncio.sleep(5)
                continue

            if not proxies_to_check:
                print(f"[{timestamp}] Ficheiro '{INPUT_FILE}' está vazio. Limpando o ficheiro de saída.", flush=True)
                with suppress(FileNotFoundError):
                    if os.path.exists(OUTPUT_FILE):
                        os.remove(OUTPUT_FILE)
                await asyncio.sleep(5)
                continue

            # 2. CRIAR E EXECUTAR TAREFAS DE VERIFICAÇÃO
            tasks = [check_proxy(proxy) for proxy in proxies_to_check]
            
            validated_proxies = []
            progress_bar = tqdm(
                asyncio.as_completed(tasks),
                total=len(proxies_to_check),
                desc=f"[{timestamp}] Verificando proxies",
                unit="proxy"
            )
            for task in progress_bar:
                result = await task
                if result:
                    validated_proxies.append(result)

            # 3. ESCREVER O RESULTADO
            timestamp_end = datetime.now().strftime("%H:%M:%S")
            if validated_proxies:
                print(f"\n[{timestamp_end}] Verificação concluída. {len(validated_proxies)} / {len(proxies_to_check)} proxies válidos.", flush=True)
                temp_file = OUTPUT_FILE + ".tmp"
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write("\n".join(validated_proxies))
                os.replace(temp_file, OUTPUT_FILE)
            else:
                print(f"\n[{timestamp_end}] Verificação concluída. Nenhum proxy passou no teste. Limpando '{OUTPUT_FILE}'.", flush=True)
                with suppress(FileNotFoundError):
                    if os.path.exists(OUTPUT_FILE):
                        os.remove(OUTPUT_FILE)

        except Exception as e:
            timestamp_err = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{timestamp_err}] Ocorreu um erro geral no script: {e}", flush=True)
        
        print("Aguardando 5 segundos para a próxima ronda...", flush=True)
        await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript interrompido pelo utilizador. A sair.")