# proxy_steam_manager/utils.py

import requests
from requests.exceptions import RequestException
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
import json
import os
import threading
try:
    import fcntl  # Unix file locking
except ImportError:
    fcntl = None

from .config import STEAM_PING_URL, PROXY_VALIDATION_TIMEOUT, PROXY_VALIDATION_RETRIES, MAX_ACCEPTABLE_LATENCY_MS
from .models import Proxy

_file_write_lock = threading.Lock()

def build_requests_proxies(proxy: Proxy) -> Dict[str, str]:
    """Constrói o dicionário de proxies para a biblioteca requests."""
    protocol_prefix = proxy.protocol
    if protocol_prefix.startswith("socks"):
        # Usar socks5h/socks4h para garantir que o DNS é resolvido através do proxy
        protocol_prefix = f"{proxy.protocol}h"
    
    proxy_url = f"{protocol_prefix}://{proxy.ip}:{proxy.port}"
    return {"http": proxy_url, "https": proxy_url}


def validate_proxy(proxy: Proxy) -> Optional[Proxy]:
    """
    Valida a proxy fazendo um GET ao endpoint da Steam.
    Retorna o Proxy com latência preenchida se bem-sucedido; caso contrário, None.
    """
    proxies = build_requests_proxies(proxy)
    
    # ALTERADO: Headers melhorados para parecer mais com um navegador real
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
    
    start_time = time.time()
    try:
        # ALTERADO: Permitir redirecionamentos e verificar o status code manualmente
        resp = requests.get(
            STEAM_PING_URL,
            proxies=proxies,
            timeout=PROXY_VALIDATION_TIMEOUT,
            stream=True,
            allow_redirects=True, # MUDANÇA IMPORTANTE
            headers=headers,
        )

        # MUDANÇA IMPORTANTE: Verificar se a resposta final (após redirecionamentos) foi bem-sucedida
        if resp.status_code == 200:
            latency_ms = (time.time() - start_time) * 1000.0
            if latency_ms <= MAX_ACCEPTABLE_LATENCY_MS:
                proxy.latency = latency_ms
                proxy.last_validated = datetime.now()
                proxy.reset_failures()
                return proxy
            else:
                # O proxy funciona, mas é muito lento
                proxy.mark_failed()
                return None
        else:
            # O proxy conectou-se mas a Steam retornou um erro (403, 503, etc.)
            proxy.mark_failed()
            return None
            
    except RequestException:
        # Falha de conexão, timeout, etc.
        proxy.mark_failed()
    except Exception:
        # Outros erros inesperados
        proxy.mark_failed()
        
    return None

# (O resto do ficheiro utils.py permanece igual ao da resposta anterior)

def get_proxies_from_file(file_path: str) -> List[Proxy]:
    """
    Lê proxies de um ficheiro de texto local.
    Suporta os formatos: 'IP:PORTO' e 'protocolo://IP:PORTO'.
    """
    proxies: List[Proxy] = []
    print(f"[DEBUG] A tentar ler proxies do ficheiro: {file_path}")
    if not os.path.exists(file_path):
        print(f"[AVISO] Ficheiro de proxies não encontrado: {file_path}")
        return proxies

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                if '://' in line:
                    try:
                        protocol_part, address_part = line.split('://', 1)
                        ip, port_str = address_part.split(':', 1)
                        port = int(port_str)
                        protocol = protocol_part.lower()

                        if protocol in ['http', 'https']:
                            proxies.append(Proxy(ip=ip, port=port, protocol='http'))
                        elif protocol in ['socks4', 'socks5']:
                            proxies.append(Proxy(ip=ip, port=port, protocol=protocol))
                    except (ValueError, IndexError):
                        pass
                elif ':' in line:
                    try:
                        ip, port_str = line.split(':')
                        port = int(port_str.strip())
                        proxies.append(Proxy(ip=ip.strip(), port=port, protocol="http"))
                        proxies.append(Proxy(ip=ip.strip(), port=port, protocol="socks4"))
                        proxies.append(Proxy(ip=ip.strip(), port=port, protocol="socks5"))
                    except ValueError:
                        pass
    except Exception as e:
        print(f"[ERRO] Falha ao ler o ficheiro {file_path}: {e}")
    
    print(f"[DEBUG] {len(proxies)} proxies potenciais lidos de {file_path}")
    return proxies


def fetch_proxies_from_url(source_url: str) -> List[Proxy]:
    """Busca proxies de uma fonte URL (formato esperado: IP:PORTO)."""
    try:
        response = requests.get(source_url, timeout=10)
        response.raise_for_status()
        proxies: List[Proxy] = []
        for line in response.text.splitlines():
            line = line.strip()
            if line and ':' in line:
                try:
                    ip, port_str = line.split(':')
                    port = int(port_str)
                    proxies.append(Proxy(ip=ip.strip(), port=port, protocol="http"))
                    proxies.append(Proxy(ip=ip.strip(), port=port, protocol="socks5"))
                except ValueError:
                    continue
        return proxies
    except RequestException as e:
        print(f"[AVISO] Falha ao buscar proxies da URL {source_url}: {e}")
        return []


def get_all_proxies(proxy_sources: List[Dict]) -> List[Proxy]:
    """Coleta proxies de todas as fontes definidas (ficheiros locais ou URLs)."""
    all_proxies: List[Proxy] = []
    
    for source in proxy_sources:
        if source.get("type") == "file":
            all_proxies.extend(get_proxies_from_file(source["url"]))
        elif source.get("type") == "url":
            all_proxies.extend(fetch_proxies_from_url(source["url"]))

    return all_proxies


def load_proxies_from_file(filename: str) -> List[Proxy]:
    if not os.path.exists(filename):
        return []
    try:
        with open(filename, "r") as f:
            content = f.read()
            if not content:
                return []
            data = json.loads(content)
            return [Proxy.from_dict(d) for d in data]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_proxies_to_file(proxies: List[Proxy], filename: str):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    tmp_filename = filename + ".tmp"
    data_to_save = [p.to_dict() for p in proxies]
    
    with _file_write_lock:
        with open(tmp_filename, "w") as f:
            if fcntl:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX)
                except Exception:
                    pass
            json.dump(data_to_save, f, indent=4)
        os.replace(tmp_filename, filename)


def save_or_update_single_proxy(proxy: Proxy, filename: str):
    """Atualiza o ficheiro JSON para inserir/atualizar um único proxy de forma segura."""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with _file_write_lock:
        all_proxies = load_proxies_from_file(filename)
        existing_proxies: Dict[str, Proxy] = {f"{p.ip}:{p.port}:{p.protocol}": p for p in all_proxies}
        
        key = f"{proxy.ip}:{proxy.port}:{p.protocol}"
        existing_proxies[key] = proxy
        
        save_proxies_to_file(list(existing_proxies.values()), filename)