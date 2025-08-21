# proxy_steam_manager/proxy_manager_service.py

import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Adicionar o diretório pai ao sys.path para permitir importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import REQUESTS_PER_PROXY, COOLDOWN_TIME_SECONDS
from models import Proxy

# --- CONFIGURAÇÃO PRINCIPAL ---
DATA_FILE = r".\steam_live.txt"
COOLDOWN_PROXIES_FILE = "cooldown_proxies.txt"
RELOAD_INTERVAL_SECONDS = 8
COOLDOWN_FILE_UPDATE_INTERVAL_SECONDS = 5 

# --- LÓGICA DO PROXY POOL ---

def load_proxies_from_text_file(file_path: str) -> List[Proxy]:
    """
    Função dedicada a ler um ficheiro de texto no formato 'protocolo://ip:porto'
    e a convertê-lo numa lista de objetos Proxy.
    """
    proxies: List[Proxy] = []
    if not os.path.exists(file_path):
        print(f"ERRO: Ficheiro de proxies não encontrado em {file_path}")
        return proxies
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or '://' not in line:
                    continue
                try:
                    protocol_part, address_part = line.split('://', 1)
                    ip, port_str = address_part.split(':', 1)
                    port = int(port_str)
                    protocol = protocol_part.lower()
                    if protocol in ['http', 'https', 'socks4', 'socks5']:
                        if protocol == 'https':
                            protocol = 'http'
                        proxies.append(Proxy(ip=ip, port=port, protocol=protocol))
                except (ValueError, IndexError):
                    print(f"Aviso: Ignorando linha mal formatada: {line}")
    except Exception as e:
        print(f"ERRO ao ler o ficheiro de proxies: {e}")
    return proxies

class ProxyPool:
    def __init__(self, data_file):
        self.data_file = data_file
        self.proxies: Dict[str, Proxy] = {}
        self.session_proxy_map: Dict[str, str] = {}
        self.lock = threading.Lock()  # Lock para garantir a atomicidade na obtenção de proxies
        self.load_proxies()

    def load_proxies(self):
        loaded_proxies = load_proxies_from_text_file(self.data_file)
        new_proxies_map = {f"{p.ip}:{p.port}:{p.protocol}": p for p in loaded_proxies}
        for key in new_proxies_map:
            if key in self.proxies:
                # Mantém o estado atual (cooldown, falhas) do proxy se ele já existir
                new_proxies_map[key] = self.proxies[key]
        self.proxies = new_proxies_map
        print(f"({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) Proxies carregados/recarregados. Total no pool: {len(self.proxies)}")

    def get_available_proxies(self) -> List[Proxy]:
        return [p for p in self.proxies.values() if p.is_active()]

    def get_cooldown_proxies(self) -> List[Proxy]:
        return [p for p in self.proxies.values() if not p.is_active()]

    def get_proxy(self, session_id: str) -> Optional[Proxy]:
        # O lock garante que apenas um thread pode executar este bloco de cada vez,
        # prevenindo que dois pedidos recebam o mesmo proxy simultaneamente.
        with self.lock:
            # Tenta manter o proxy da sessão se ainda for válido
            if session_id in self.session_proxy_map:
                proxy_key = self.session_proxy_map[session_id]
                if proxy_key in self.proxies:
                    proxy = self.proxies[proxy_key]
                    if proxy.is_active() and proxy.requests_served < REQUESTS_PER_PROXY:
                        proxy.requests_served += 1 # Incrementar o uso
                        return proxy
            
            # Se não, procura um novo proxy
            available_proxies = self.get_available_proxies()
            if not available_proxies:
                return None
            
            # Lógica simples: pegar no primeiro disponível
            new_proxy = available_proxies[0]
            
            # Marcar o proxy como "usado" imediatamente para que o próximo pedido não o apanhe
            new_proxy.requests_served += 1

            new_proxy_key = f"{new_proxy.ip}:{new_proxy.port}:{new_proxy.protocol}"
            print(f"({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) LOG: Rotação de proxy para a sessão '{session_id}'. Novo proxy: {new_proxy_key}")
            self.session_proxy_map[session_id] = new_proxy_key
            return new_proxy

    def report_proxy_usage(self, proxy_key: str, success: bool):
        if proxy_key not in self.proxies:
            return
        
        proxy = self.proxies[proxy_key]

        if not success:
            proxy.mark_failed()
            proxy.cooldown_until = datetime.now() + timedelta(seconds=COOLDOWN_TIME_SECONDS)
            print(f"({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) LOG: Proxy {proxy_key} reportado com FALHA. A entrar em cooldown.")
            return
        
        # Se sucesso, resetar o contador de falhas
        proxy.reset_failures()
        
        # Verificar se atingiu o limite de pedidos
        if proxy.requests_served >= REQUESTS_PER_PROXY:
            proxy.cooldown_until = datetime.now() + timedelta(seconds=COOLDOWN_TIME_SECONDS)
            proxy.requests_served = 0 # Resetar para a próxima utilização
            print(f"({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) LOG: Proxy {proxy_key} atingiu o limite de {REQUESTS_PER_PROXY} pedidos e entrou em cooldown.")

proxy_pool = ProxyPool(DATA_FILE)

# --- TAREFAS DE FUNDO ---

def _reload_proxies_periodically():
    while True:
        time.sleep(RELOAD_INTERVAL_SECONDS)
        print(f"({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) INFO: Tarefa de fundo a recarregar proxies de '{DATA_FILE}'...")
        proxy_pool.load_proxies()

def _update_cooldown_file_periodically():
    while True:
        time.sleep(COOLDOWN_FILE_UPDATE_INTERVAL_SECONDS)
        cooldown_proxies = proxy_pool.get_cooldown_proxies()
        try:
            temp_file = COOLDOWN_PROXIES_FILE + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                for p in cooldown_proxies:
                    f.write(f"{p.protocol}://{p.ip}:{p.port}\n")
            os.replace(temp_file, COOLDOWN_PROXIES_FILE)
        except Exception as e:
            print(f"({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ERRO: Falha ao escrever no ficheiro de cooldown '{COOLDOWN_PROXIES_FILE}': {e}")

# --- GESTOR DE CICLO DE VIDA (LIFESPAN) ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("INFO: A iniciar tarefas de fundo (recarregamento de proxies e escrita de cooldown).")
    
    reload_thread = threading.Thread(target=_reload_proxies_periodically, daemon=True)
    reload_thread.start()
    
    cooldown_thread = threading.Thread(target=_update_cooldown_file_periodically, daemon=True)
    cooldown_thread.start()
    
    yield
    
    print("INFO: Aplicação a terminar.")

# --- INICIALIZAÇÃO DA APLICAÇÃO FASTAPI ---
app = FastAPI(lifespan=lifespan)

# --- MODELOS E ENDPOINTS DA API ---

class AcquireProxyResponse(BaseModel):
    ip: str
    port: int
    protocol: str
    proxy_key: str

class ReportProxyRequest(BaseModel):
    proxy_key: str
    success: bool

@app.get("/acquire_proxy", response_model=AcquireProxyResponse)
async def acquire_proxy(session_id: str):
    print(f"({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) LOG: Recebido pedido de proxy para a sessão: '{session_id}'")
    proxy = proxy_pool.get_proxy(session_id)
    if not proxy:
        raise HTTPException(status_code=503, detail="Nenhum proxy disponível no momento.")
    
    proxy_key = f"{proxy.ip}:{proxy.port}:{proxy.protocol}"
    return AcquireProxyResponse(ip=proxy.ip, port=proxy.port, protocol=proxy.protocol, proxy_key=proxy_key)

@app.post("/report_proxy_usage")
async def report_proxy_usage(request: ReportProxyRequest):
    proxy_pool.report_proxy_usage(request.proxy_key, request.success)
    return {"message": "Relatório de uso do proxy recebido"}

@app.get("/metrics")
async def get_metrics():
    available_proxies = len(proxy_pool.get_available_proxies())
    total_proxies = len(proxy_pool.proxies)
    return {
        "total_proxies_in_pool": total_proxies,
        "available_proxies": available_proxies,
        "proxies_in_cooldown": total_proxies - available_proxies,
        "active_sessions": len(proxy_pool.session_proxy_map),
    }

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)