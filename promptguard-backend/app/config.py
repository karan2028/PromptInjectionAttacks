from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    engine: str = "demo"
    db_path: str = "data/promptguard.sqlite3"
    api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    cors_origins: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver")
    requests_per_minute: int = 60
    allow_live_suite: bool = False

    @classmethod
    def from_env(cls):
        return cls(
            engine=os.getenv("PG_ENGINE", "demo"),
            db_path=os.getenv("PG_DB_PATH", "data/promptguard.sqlite3"),
            api_key=os.getenv("PG_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            cors_origins=tuple(x.strip() for x in os.getenv("PG_CORS_ORIGINS", "").split(",") if x.strip()),
            allowed_hosts=tuple(x.strip() for x in os.getenv("PG_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver").split(",") if x.strip()),
            requests_per_minute=int(os.getenv("PG_REQUESTS_PER_MINUTE", "60")),
            allow_live_suite=os.getenv("PG_ALLOW_LIVE_SUITE", "0") == "1",
        )

    def validate(self):
        if self.engine not in {"demo", "openai"}:
            raise ValueError("PG_ENGINE must be demo or openai")
        if self.engine == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for PG_ENGINE=openai")
        if self.requests_per_minute < 1:
            raise ValueError("PG_REQUESTS_PER_MINUTE must be positive")
        if not self.allowed_hosts:
            raise ValueError("PG_ALLOWED_HOSTS cannot be empty")
        if "*" in self.cors_origins:
            raise ValueError("Explicit CORS origins are required; wildcard is disabled")
