import sys

sys.dont_write_bytecode = True  # no generar __pycache__/ en ninguna carpeta del proyecto

import os
from pathlib import Path

from config import DATA_DIR

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import archivo_inspeccion, edificios, hallazgos, mision, nube, relevamientos, robot, sistema

BASE_DIR = Path(__file__).parent

app = FastAPI(title="G1 Structural Inspector - Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(DATA_DIR / "static")), name="static")

app.include_router(hallazgos.router)
app.include_router(mision.router)
app.include_router(relevamientos.router)
app.include_router(sistema.router)
app.include_router(nube.router)
app.include_router(robot.router)
app.include_router(edificios.router)
app.include_router(archivo_inspeccion.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("G1_HOST", "0.0.0.0"), port=int(os.environ.get("G1_PORT", "8000")))
