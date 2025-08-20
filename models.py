from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Optional

@dataclass
class Proxy:
    ip: str
    port: int
    protocol: Literal["http", "socks4", "socks5"]
    latency: Optional[float] = None
    last_validated: Optional[datetime] = None
    failures: int = 0
    # Para sticky sessions e cooldown
    requests_served: int = 0
    cooldown_until: Optional[datetime] = None

    def is_active(self) -> bool:
        if self.cooldown_until:
            return datetime.now() > self.cooldown_until
        return True

    def mark_failed(self):
        self.failures += 1

    def reset_failures(self):
        self.failures = 0

    def to_dict(self):
        return {
            "ip": self.ip,
            "port": self.port,
            "protocol": self.protocol,
            "latency": self.latency,
            "last_validated": self.last_validated.isoformat() if self.last_validated else None,
            "failures": self.failures,
            "requests_served": self.requests_served,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
        }

    @classmethod
    def from_dict(cls, data: dict):
        last_validated = datetime.fromisoformat(data["last_validated"]) if data.get("last_validated") else None
        cooldown_until = datetime.fromisoformat(data["cooldown_until"]) if data.get("cooldown_until") else None
        return cls(
            ip=data["ip"],
            port=data["port"],
            protocol=data["protocol"],
            latency=data.get("latency"),
            last_validated=last_validated,
            failures=data.get("failures", 0),
            requests_served=data.get("requests_served", 0),
            cooldown_until=cooldown_until,
        )


