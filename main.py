import sys

sys.dont_write_bytecode = True  # no generar __pycache__/ en ninguna carpeta del proyecto

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import hallazgos, relevamientos, sistema

BASE_DIR = Path(__file__).parent

app = FastAPI(title="G1 Structural Inspector - Backend")

# CORS abierto para la demo. En producción, restringir a la URL real del front.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(hallazgos.router)
app.include_router(relevamientos.router)
app.include_router(sistema.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
