# proxy_steam_manager/proxy_manager_service.py

import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Adicionar o diretório pai ao sys.path para permitir importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import REQUESTS_PER_PROXY, COOLDOWN_TIME_SECONDS
from models import Proxy

# --- CONFIGURAÇÃO PRINCIPAL ---
# Caminho para o seu ficheiro de texto com a lista de proxies.
DATA_FILE = r".\steam_live.txt"

app = FastAPI()

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

                    # Garantir que o protocolo é um dos que o nosso modelo aceita
                    if protocol in ['http', 'https', 'socks4', 'socks5']:
                        # Normalizar 'https' para 'http' para o nosso modelo
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
        self.load_proxies()

    def load_proxies(self):
        """Carrega os proxies diretamente do ficheiro de texto."""
        loaded_proxies = load_proxies_from_text_file(self.data_file)
        self.proxies = {f"{p.ip}:{p.port}:{p.protocol}": p for p in loaded_proxies}
        print(f"({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) Proxies carregados/recarregados. Total no pool: {len(self.proxies)}")

    def get_available_proxies(self) -> List[Proxy]:
        """Retorna uma lista de proxies que não estão em cooldown."""
        now = datetime.now()
        available = [p for p in self.proxies.values() if p.is_active()]
        # Ordenar por menor latência (se tivéssemos essa info) ou simplesmente retornar a lista
        return available

    def get_proxy(self, session_id: str) -> Optional[Proxy]:
        # Sticky session
        if session_id in self.session_proxy_map:
            proxy_key = self.session_proxy_map[session_id]
            if proxy_key in self.proxies:
                proxy = self.proxies[proxy_key]
                if proxy.is_active() and proxy.requests_served < REQUESTS_PER_PROXY:
                    return proxy
        
        # Procurar um novo proxy
        available_proxies = self.get_available_proxies()
        if not available_proxies:
            return None
        
        # Lógica simples: pegar no primeiro disponível
        new_proxy = available_proxies[0]
        new_proxy_key = f"{new_proxy.ip}:{new_proxy.port}:{new_proxy.protocol}"
        self.session_proxy_map[session_id] = new_proxy_key
        return new_proxy

    def report_proxy_usage(self, proxy_key: str, success: bool):
        """Gere o estado do proxy apenas em memória."""
        if proxy_key not in self.proxies:
            return

        proxy = self.proxies[proxy_key]

        if not success:
            proxy.mark_failed()
            print(f"Proxy {proxy_key} reportado com falha. Falhas: {proxy.failures}")
            # Se falhar 1 vezes, entra em cooldown longo
            if proxy.failures >= 1:
                 proxy.cooldown_until = datetime.now() + timedelta(hours=1)
                 print(f"Proxy {proxy_key} colocado em cooldown longo devido a falhas.")
            return
        
        # Se sucesso, incrementar contador e verificar cooldown
        proxy.requests_served += 1
        if proxy.requests_served >= REQUESTS_PER_PROXY:
            proxy.cooldown_until = datetime.now() + timedelta(seconds=COOLDOWN_TIME_SECONDS)
            proxy.requests_served = 0 # Resetar para a próxima utilização
            print(f"Proxy {proxy_key} atingiu o limite de requests e entrou em cooldown.")

proxy_pool = ProxyPool(DATA_FILE)

# (O resto do ficheiro permanece igual)

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
    proxy = proxy_pool.get_proxy(session_id)
    if not proxy:
        raise HTTPException(status_code=503, detail="Nenhum proxy disponível no momento.")
    
    proxy.requests_served += 1 # Incrementar o uso aqui, no momento da entrega
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