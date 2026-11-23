from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, masters, prices, purchases, receipts, sales, stock, users

app = FastAPI(title="Cement Wholesaler Management System", version="0.1.0")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(masters.router)
app.include_router(prices.router)
app.include_router(purchases.router)
app.include_router(stock.router)
app.include_router(sales.router)
app.include_router(receipts.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


# In production the built React app is served from the same process (one install, one port).
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        return FileResponse(_dist / "index.html")
