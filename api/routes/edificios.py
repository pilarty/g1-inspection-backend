"""Ayudas para la pantalla "Nuevo edificio": ubicar la dirección y subir documentos.

- /edificio/ubicar: coordenadas y dirección normalizada con Georef, el servicio
  oficial de normalización de direcciones del Estado argentino
  (https://apis.datos.gob.ar/georef). No necesita clave.
- /edificio/documentos: sube un archivo a S3 por la misma vía que las fotos de
  hallazgos (URL prefirmada de la API de AWS) y lo registra en documento_edificacion.
"""
import re
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException, Request, Response

from infrastructure import nube

router = APIRouter(prefix="/edificio")

GEOREF = "https://apis.datos.gob.ar/georef/api"
MAX_BYTES = 50 * 1024 * 1024
TIPOS_DOCUMENTO = {"plano_aprobado", "final_obra", "escritura", "foto", "informe_anterior", "plano_ph"}
EXTENSIONES = {".pdf", ".dwg", ".dxf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}


@router.get("/ubicar")
def ubicar(calle: str, localidad: str = "", provincia: str = ""):
    """Busca la dirección en Georef. Si no la encuentra, devuelve encontrado=False (no es un error)."""
    if not re.search(r"\d", calle):
        return {"encontrado": False, "motivo": "Falta la altura (número) de la calle."}
    params = {"direccion": calle, "max": 1}
    if provincia:
        params["provincia"] = provincia
    if localidad:
        params["localidad"] = localidad
    try:
        r = requests.get(f"{GEOREF}/direcciones", params=params, timeout=8)
        r.raise_for_status()
        direcciones = r.json().get("direcciones", [])
        if not direcciones and localidad:
            # Georef usa localidades censales: si no coincide el nombre, se prueba solo con la provincia
            params.pop("localidad")
            r = requests.get(f"{GEOREF}/direcciones", params=params, timeout=8)
            r.raise_for_status()
            direcciones = r.json().get("direcciones", [])
    except requests.RequestException:
        return {"encontrado": False, "motivo": "No se pudo consultar el servicio de direcciones."}
    if not direcciones:
        return {"encontrado": False, "motivo": "No se encontró esa dirección."}
    d = direcciones[0]
    ubicacion = d.get("ubicacion") or {}
    if ubicacion.get("lat") is None:
        return {"encontrado": False, "motivo": "La dirección existe, pero sin coordenadas."}
    return {
        "encontrado": True,
        "lat": round(ubicacion["lat"], 7),
        "lon": round(ubicacion["lon"], 7),
        "direccion_normalizada": d.get("nomenclatura"),
    }


@router.post("/documentos")
async def subir_documento(request: Request, edificacion_id: int, tipo: str, nombre: str,
                          content_type: Optional[str] = None):
    """Recibe el archivo como cuerpo crudo de la petición (sin multipart)."""
    if not nube.sesion_activa():
        raise HTTPException(401, "sin sesion")
    if tipo not in TIPOS_DOCUMENTO:
        raise HTTPException(400, "tipo de documento invalido")
    extension = ("." + nombre.rsplit(".", 1)[-1].lower()) if "." in nombre else ""
    if extension not in EXTENSIONES:
        raise HTTPException(400, "tipo de archivo no permitido")
    datos = await request.body()
    if not datos:
        raise HTTPException(400, "archivo vacio")
    if len(datos) > MAX_BYTES:
        raise HTTPException(413, "el archivo supera los 50 MB")
    tipo_contenido = content_type or "application/octet-stream"
    try:
        s = nube.reenviar("POST", "archivos/subida", cuerpo={
            "carpeta": "documentos", "nombre": nombre, "content_type": tipo_contenido,
        })
        s.raise_for_status()
        s = s.json()
        r = requests.put(s["url"], data=datos, headers={"Content-Type": tipo_contenido}, timeout=120)
        r.raise_for_status()
        r = nube.reenviar("POST", "documentos", cuerpo={
            "edificacion_id": edificacion_id,
            "archivo_url": s["key"],
            "tipo_archivo": tipo,
            "descripcion": nombre,
        })
        r.raise_for_status()
    except requests.RequestException:
        raise HTTPException(502, "no se pudo subir el archivo a la nube")
    return r.json()


@router.get("/documento")
def descargar_documento(key: str, nombre: str = "documento"):
    """Trae el archivo desde S3 (enlace temporal de la API de AWS) y lo entrega para descargar."""
    if not nube.sesion_activa():
        raise HTTPException(401, "sin sesion")
    try:
        r = nube.reenviar("GET", "archivos/descarga", params={"key": key})
        r.raise_for_status()
        archivo = requests.get(r.json()["url"], timeout=120)
        archivo.raise_for_status()
    except requests.RequestException:
        raise HTTPException(502, "no se pudo traer el archivo de la nube")
    seguro = re.sub(r'[^\w.\- ]', "_", nombre)[:150] or "documento"
    return Response(
        content=archivo.content,
        media_type=archivo.headers.get("content-type", "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{seguro}"'},
    )
