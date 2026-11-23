import sys

sys.dont_write_bytecode = True  # no generar __pycache__/ en ninguna carpeta del proyecto

import os
import threading
from pathlib import Path

from config import DATA_DIR

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import archivo_inspeccion, edificios, hallazgos, mision, navegacion, nube, relevamientos, robot, sistema

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
app.include_router(navegacion.router)


@app.on_event("startup")
def cargar_modelos_en_segundo_plano():
    # Los modelos tardan varios segundos en cargar: se cargan mientras el usuario
    # ya está usando la app, en lugar de demorar la apertura.
    from domain import clasificador_danos_cnn, detector_danos_cnn

    def cargar():
        detector_danos_cnn.cargar()
        clasificador_danos_cnn.cargar()

    threading.Thread(target=cargar, daemon=True).start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("G1_HOST", "0.0.0.0"), port=int(os.environ.get("G1_PORT", "8000")))
