import threading

import requests
from pycognito import Cognito

from config import BASE_DIR

POOL = "us-east-1_s9afR6W9w"
CLIENT = "4044ectglilgk2u23qeit75pue"
API = "https://lunkxzh9q5.execute-api.us-east-1.amazonaws.com"

_usuario = None
relevamiento_actual = None


def iniciar_sesion(usuario: str, clave: str) -> None:
    """Login con Cognito (SRP). La clave no se guarda en ningun lado."""
    global _usuario
    u = Cognito(POOL, CLIENT, username=usuario)
    u.authenticate(password=clave)
    _usuario = u


def sesion_activa() -> bool:
    return _usuario is not None


def _headers() -> dict:
    _usuario.check_token()  # renueva el token si esta por vencer
    return {"Authorization": "Bearer " + _usuario.id_token}


def subir_hallazgo(registro: dict, relevamiento_id: int) -> None:
    """Sube la foto a S3 y crea el hallazgo en la base de datos."""
    h = _headers()
    ruta = BASE_DIR / registro["image"].lstrip("/")

    s = requests.post(
        API + "/archivos/subida", headers=h, timeout=15,
        json={"carpeta": "hallazgos", "nombre": ruta.name,
              "content_type": "image/png"},
    )
    s.raise_for_status()
    s = s.json()

    r = requests.put(s["url"], data=ruta.read_bytes(),
                     headers={"Content-Type": "image/png"}, timeout=60)
    r.raise_for_status()

    tipos = registro.get("types", [])
    r = requests.post(API + "/hallazgos", headers=h, timeout=15, json={
        "relevamiento_id": relevamiento_id,
        "tipo_dano": tipos[0]["type"] if tipos else "Sin clasificar",
        "severidad": registro["severity"],
        "ubicacion_x": registro["x"],
        "ubicacion_y": registro["y"],
        "imagen_representativa_url": s["key"],
        "imagenes_asociadas": [s["key"]],
        "cantidad_detecciones": 1,
        "probabilidad_promedio": registro["detection_probability"] / 100,
    })
    r.raise_for_status()


def enviar_en_segundo_plano(registro: dict, relevamiento_id: int) -> None:
    """No bloquea la deteccion local: si falla la nube, solo avisa."""
    if not sesion_activa():
        return

    def tarea():
        try:
            subir_hallazgo(registro, relevamiento_id)
        except Exception as e:
            print("[nube] no se pudo enviar el hallazgo:", e)

    threading.Thread(target=tarea, daemon=True).start()
