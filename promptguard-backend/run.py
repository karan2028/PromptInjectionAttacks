"""Run the localhost-first lab server. Importable ASGI factory: app.main:create_app."""
import argparse
import os
import uvicorn

def main():
    parser = argparse.ArgumentParser(description="PromptGuard MDC educational backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not os.getenv("PG_API_KEY"):
        parser.error("Remote binding requires PG_API_KEY. Use localhost for an unauthenticated local lab.")
    uvicorn.run("app.main:create_app", factory=True, host=args.host, port=args.port,
                limit_concurrency=32, timeout_keep_alive=5, proxy_headers=False)

if __name__ == "__main__":
    main()
