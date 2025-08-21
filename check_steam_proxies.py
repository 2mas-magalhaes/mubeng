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
    from aiohttp_socks import ProxyConnector
    from tqdm.asyncio import tqdm
except ImportError:
    print("Erro: Bibliotecas necessárias não encontradas. Por favor, instale-as com:")
    print("python -m pip install aiohttp aiohttp_socks tqdm")
    sys.exit(1)

# --- IMPORTAÇÃO DAS CONFIGURAÇÕES ---
try:
    from config import *
except ImportError:
    print("ERRO: O ficheiro 'config.py' não foi encontrado. Certifique-se de que ele está no mesmo diretório que este script.")
    sys.exit(1)


log_lock = threading.Lock()

def write_log_sync(log_message: str):
    """Função síncrona que escreve no ficheiro. Será executada num thread separado."""
    try:
        with log_lock:
            with open(CHECKER_DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_message)
    except Exception as e:
        print(f"ERRO CRÍTICO AO ESCREVER NO LOG: {e}", flush=True)

async def log_debug(proxy: str, stage: str, details: str):
    """Regista logs de forma segura e não-bloqueante."""
    if not CHECKER_DEBUG_MODE:
        return
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_message = f"[{timestamp}] PROXY {proxy} | {stage}\nDETAILS: {details}\n--- END ---\n\n"
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, write_log_sync, log_message)


async def check_proxy(proxy: str, sem: asyncio.Semaphore) -> Optional[str]:
    """Testa um proxy contra a API da Steam, gerindo o semáforo."""
    async with sem: # O semáforo agora é gerido aqui dentro
        await log_debug(proxy, "TASK_START", "Iniciando verificação")
        try:
            connector = ProxyConnector.from_url(proxy)
        except Exception as e:
            await log_debug(proxy, "INVALID_PROXY_FORMAT", f"{type(e).__name__}: {e}")
            return None

        try:
            timeout = aiohttp.ClientTimeout(total=CHECKER_TIMEOUT_SEC)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(CHECKER_VALIDATION_URL, headers=CHECKER_HEADERS) as response:
                    await log_debug(proxy, "HTTP_RESPONSE", f"Status: {response.status}")
                    if response.status == 200:
                        text = await response.text()
                        if CHECKER_VALIDATION_TEXT in text:
                            await log_debug(proxy, "SUCCESS", "Proxy válido ✅")
                            return proxy
                        else:
                            await log_debug(proxy, "VALIDATION_FAIL", "Texto de validação não encontrado ❌")
                    else:
                        await log_debug(proxy, "BAD_STATUS", f"Recebido status {response.status}")
        except asyncio.CancelledError:
            await log_debug(proxy, "CANCELLED", "Tarefa cancelada durante a execução.")
            # É importante propagar o CancelledError para que o asyncio saiba que a tarefa foi cancelada.
            raise
        except Exception as e:
            error_type = type(e).__name__
            await log_debug(proxy, "ERROR", f"{error_type}: {e}")
        return None


async def main():
    """Loop principal que lê, testa e guarda os proxies."""
    print("🚀 Iniciando verificação de proxies contra a API do Steam Market...", flush=True)
    if CHECKER_DEBUG_MODE:
        print(f"🐛 MODO DEBUG ATIVO. Logs detalhados em '{CHECKER_DEBUG_LOG_FILE}'", flush=True)
        with suppress(FileNotFoundError):
            if os.path.exists(CHECKER_DEBUG_LOG_FILE):
                os.remove(CHECKER_DEBUG_LOG_FILE)

    while True:
        tasks = []
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            try:
                with open(CHECKER_INPUT_FILE, "r", encoding="utf-8") as f:
                    proxies_to_check = sorted(list(set(line.strip() for line in f if line.strip())))
            except FileNotFoundError:
                print(f"[{timestamp}] Ficheiro '{CHECKER_INPUT_FILE}' não encontrado. Aguardando...", flush=True)
                await asyncio.sleep(CHECKER_LOOPSLEEP_SEC)
                continue
            if not proxies_to_check:
                print(f"[{timestamp}] Ficheiro '{CHECKER_INPUT_FILE}' está vazio. Verificando novamente...", flush=True)
                await asyncio.sleep(CHECKER_LOOPSLEEP_SEC)
                continue

            sem = asyncio.Semaphore(CHECKER_CONCURRENCY)
            
            # Criar todas as tarefas de uma vez
            tasks = [asyncio.create_task(check_proxy(proxy, sem)) for proxy in proxies_to_check]
            
            validated_proxies = []
            
            # Usar tqdm com as_completed para a barra de progresso
            progress_bar = tqdm(asyncio.as_completed(tasks), total=len(tasks), desc=f"[{timestamp}] Verificando", unit="proxy")
            for task_future in progress_bar:
                try:
                    result = await task_future
                    if result:
                        validated_proxies.append(result)
                    progress_bar.set_postfix({'Válidos': len(validated_proxies)})
                except asyncio.CancelledError:
                    # Se uma tarefa for cancelada, apenas o registamos e continuamos
                    await log_debug("N/A", "CLEANUP", "Uma tarefa foi apanhada durante o cancelamento.")

            # Escrita de resultados após a conclusão de todas as tarefas
            timestamp_end = datetime.now().strftime("%H:%M:%S")
            if validated_proxies:
                print(f"\n[{timestamp_end}] {len(validated_proxies)} / {len(proxies_to_check)} proxies válidos ✅", flush=True)
                temp_file = CHECKER_OUTPUT_FILE + ".tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(sorted(validated_proxies)))
                os.replace(temp_file, CHECKER_OUTPUT_FILE)
            else:
                print(f"\n[{timestamp_end}] Nenhum proxy válido encontrado ❌", flush=True)
                with suppress(FileNotFoundError):
                    if os.path.exists(CHECKER_OUTPUT_FILE):
                        os.remove(CHECKER_OUTPUT_FILE)
                        
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n🛑 Interrupção detetada. Cancelando tarefas pendentes de forma graciosa...", flush=True)
            # --- CORREÇÃO CRÍTICA: Bloco de limpeza explícito ---
            # Este bloco garante que todas as tarefas criadas são canceladas antes de sair.
            for task in tasks:
                task.cancel()
            # Esperar que todas as tarefas processem o cancelamento.
            await asyncio.gather(*tasks, return_exceptions=True)
            print("✨ Limpeza concluída. A sair.", flush=True)
            break # Sai do loop while

        except Exception as e:
            print(f"[{timestamp}] Erro geral no loop principal: {type(e).__name__}: {e}", flush=True)
            
        print(f"⏳ Aguardando {CHECKER_LOOPSLEEP_SEC} segundos para a próxima ronda...\n", flush=True)
        await asyncio.sleep(CHECKER_LOOPSLEEP_SEC)


if __name__ == "__main__":
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        # Este bloco serve apenas como uma segurança final, a lógica principal está no loop.
        print("\n👋 Programa terminado.")