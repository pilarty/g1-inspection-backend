"""Compartir una edificación como archivo (.g1insp), como se comparte un plano en AutoCAD.

- GET  /archivo-inspeccion/edificacion/{eid}: arma el archivo con la edificación entera: su ficha,
  el proyecto y TODAS sus inspecciones, cada una con su planta, el camino del robot, el plano,
  los hallazgos con sus fotos (en base64) y la revisión del inspector.
- POST /archivo-inspeccion/importar?proyecto_id=N[&edificacion_id=M]: recibe ese archivo y crea una
  COPIA en la cuenta de quien lo importa: si se elige una edificación, las inspecciones se agregan a
  esa; si no, se crea una edificación nueva en el proyecto elegido. (Acepta también los archivos de
  una sola inspección de la versión 1.) También el robot (si
  no tiene uno con ese nombre), la inspección, sus hallazgos (las fotos se suben de nuevo a S3)
  y todo lo demás.

Todo pasa por este backend porque las fotos pesan: así no hay límites de tamaño de la API de
AWS ni problemas para leer las fotos de S3 desde la app.
"""
import base64
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter, Body, HTTPException

from infrastructure import nube

router = APIRouter(prefix="/archivo-inspeccion")

FORMATO = "g1-inspeccion"
VERSION = 2  # 2: una edificación entera con todas sus inspecciones (1: una sola inspección)

# Campos de la ficha de la edificación que viajan en el archivo
CAMPOS_EDIFICACION = [
    "nombre", "tipo_propiedad", "destino", "direccion", "calle_numero", "localidad", "provincia", "pais",
    "codigo_postal", "latitud", "longitud", "anio_construccion", "anio_precision", "pisos_sobre_pb",
    "cantidad_plantas", "subsuelos", "superficie_cubierta", "superficie_terreno", "modificaciones",
    "matricula", "nomenclatura_catastral", "partida_inmobiliaria", "valuacion_fiscal", "linderos",
    "ph_unidades_funcionales", "ph_unidad_funcional", "ph_porcentual", "responsable", "contacto",
]
CAMPOS_PROYECTO = ["nombre", "finalidad", "cliente_nombre", "tipo_cliente"]


def _get(ruta: str, params: Optional[dict] = None, opcional: bool = False):
    r = nube.reenviar("GET", ruta, params=params)
    if opcional and r.status_code in (404, 405):
        return None
    r.raise_for_status()
    return r.json()


def _enviar(metodo: str, ruta: str, cuerpo: Any):
    r = nube.reenviar(metodo, ruta, cuerpo=cuerpo)
    r.raise_for_status()
    return r.json() if r.content else None


def _solo(d: Optional[dict], campos: List[str]) -> dict:
    d = d or {}
    return {c: d.get(c) for c in campos if d.get(c) is not None}


def _bajar_foto(clave: Optional[str]) -> Optional[str]:
    """Foto de S3 como data URL (o None si no se pudo)."""
    if not clave:
        return None
    try:
        firmada = _get("archivos/descarga", params={"key": clave})
        r = requests.get(firmada["url"], timeout=30)
        r.raise_for_status()
        tipo = r.headers.get("content-type", "image/png").split(";")[0]
        return f"data:{tipo};base64," + base64.b64encode(r.content).decode("ascii")
    except Exception:
        return None


def _subir_foto(data_url: Optional[str], nombre: str) -> Optional[str]:
    """Sube una foto (data URL) a S3 y devuelve su clave."""
    if not data_url or not data_url.startswith("data:") or "," not in data_url:
        return None
    cabecera, contenido = data_url.split(",", 1)
    tipo = cabecera[5:].split(";")[0] or "image/png"
    try:
        s = _enviar("POST", "archivos/subida", {"carpeta": "hallazgos", "nombre": nombre, "content_type": tipo})
        r = requests.put(s["url"], data=base64.b64decode(contenido), headers={"Content-Type": tipo}, timeout=60)
        r.raise_for_status()
        return s["key"]
    except Exception:
        return None


def _inspeccion(rel: dict, robots: List[dict], plantas: Dict[int, str]) -> dict:
    """Todo lo de una inspección, listo para el archivo."""
    rid = rel["id"]
    robot = next((r for r in robots if r.get("id") == rel.get("robot_id")), None)
    hallazgos = _get(f"relevamientos/{rid}/hallazgos") or []
    revisiones = {x["hallazgo_id"]: x for x in (_get(f"relevamientos/{rid}/revisiones", opcional=True) or [])}
    return {
        "fecha_inicio": rel.get("fecha_inicio"),
        "fecha_fin": rel.get("fecha_fin"),
        "estado": "finalizado" if rel.get("estado") == "en_curso" else rel.get("estado"),
        "planta": plantas.get(rid),
        "robot": {"codigo": (robot or {}).get("codigo") or "Robot", "unidad": (robot or {}).get("unidad") or "Unitree G1"},
        "trayectoria": _get(f"relevamientos/{rid}/trayectoria", opcional=True) or [],
        "plano": _get(f"relevamientos/{rid}/plano", opcional=True),
        "dictamen": _get(f"relevamientos/{rid}/dictamen", opcional=True),
        "hallazgos": [
            {
                "tipo_dano": h.get("tipo_dano"),
                "ubicacion_x": h.get("ubicacion_x"),
                "ubicacion_y": h.get("ubicacion_y"),
                "probabilidad_promedio": h.get("probabilidad_promedio"),
                "cantidad_detecciones": h.get("cantidad_detecciones"),
                "fecha_deteccion": h.get("fecha_deteccion"),
                "revision": {k: revisiones[h["id"]].get(k) for k in ("estado", "nota", "intervencion", "plazo")} if h["id"] in revisiones else None,
                "foto": _bajar_foto(h.get("imagen_representativa_url")),
            }
            for h in hallazgos
        ],
    }


@router.get("/edificacion/{eid}")
def exportar_edificacion(eid: int):
    if not nube.sesion_activa():
        raise HTTPException(401, "sin sesion")
    try:
        edif = _get(f"edificaciones/{eid}")
        proyecto = _get(f"proyectos/{edif['proyecto_id']}", opcional=True)
        robots = _get("robots") or []
        plantas = {x["relevamiento_id"]: x["planta"] for x in (_get("plantas", opcional=True) or [])}
        rels = sorted((r for r in (_get("relevamientos") or []) if r.get("edificacion_id") == eid),
                      key=lambda r: r.get("fecha_inicio") or "")
        inspecciones = [_inspeccion(r, robots, plantas) for r in rels]
    except requests.RequestException:
        raise HTTPException(502, "no se pudo leer la edificación de la nube")
    return {
        "formato": FORMATO,
        "version": VERSION,
        "exportado": datetime.now(timezone.utc).isoformat(),
        "exportado_por": nube.nombre_usuario,
        "proyecto": _solo(proyecto, CAMPOS_PROYECTO),
        "edificacion": _solo(edif, CAMPOS_EDIFICACION),
        "inspecciones": inspecciones,
    }


def _robot_id(codigo: str, unidad: str, cache: Dict[str, int]) -> int:
    """El robot del usuario con ese nombre; si no tiene, lo crea (sin datos de conexión)."""
    clave = codigo.strip().lower()
    if clave in cache:
        return cache[clave]
    for r in _get("robots") or []:
        if (r.get("codigo") or "").strip().lower() == clave:
            cache[clave] = r["id"]
            return r["id"]
    creado = _enviar("POST", "robots", {"codigo": codigo, "unidad": unidad, "estado": "activo", "conexion": None})
    cache[clave] = creado["id"]
    return creado["id"]


def _importar_inspeccion(eid: int, insp: dict, num: int, avisos: List[str], robots: Dict[str, int]) -> int:
    """Crea una inspección (con todo lo suyo) dentro de la edificación eid."""
    robot = insp.get("robot") or {}
    robot_id = _robot_id(robot.get("codigo") or "Robot", robot.get("unidad") or "Unitree G1", robots)
    rid = _enviar("POST", "relevamientos", {
        "edificacion_id": eid, "robot_id": robot_id,
        "fecha_inicio": insp.get("fecha_inicio") or datetime.now(timezone.utc).isoformat(),
        "estado": "en_curso",
    })["id"]
    _enviar("PUT", f"relevamientos/{rid}", {"fecha_fin": insp.get("fecha_fin") or insp.get("fecha_inicio"),
                                             "estado": insp.get("estado") or "finalizado"})

    # Si la nube todavía no acepta alguna de estas partes, se avisa y se sigue
    def extra(desc: str, metodo: str, ruta: str, cuerpo: Any):
        try:
            _enviar(metodo, ruta, cuerpo)
        except requests.RequestException:
            avisos.append(f"Inspección {num}: no se pudo importar {desc}.")

    if insp.get("planta"):
        extra("la planta", "PUT", f"relevamientos/{rid}/planta", {"planta": insp["planta"]})
    if insp.get("plano"):
        extra("el plano", "PUT", f"relevamientos/{rid}/plano", insp["plano"])
    puntos = insp.get("trayectoria") or []
    for i in range(0, len(puntos), 2000):
        extra("el camino del robot", "POST", f"relevamientos/{rid}/trayectoria", {"puntos": puntos[i:i + 2000]})
    if insp.get("dictamen"):
        d = insp["dictamen"]
        extra("el dictamen", "PUT", f"relevamientos/{rid}/dictamen", {k: d.get(k) for k in ("uso", "estado_general", "recomendaciones")})

    for n, h in enumerate(insp.get("hallazgos") or [], start=1):
        clave = _subir_foto(h.get("foto"), f"importado-{rid}-{n}.png")
        if h.get("foto") and not clave:
            avisos.append(f"Inspección {num}: no se pudo subir la foto del hallazgo {n}.")
        creado = _enviar("POST", "hallazgos", {
            "relevamiento_id": rid,
            "tipo_dano": h.get("tipo_dano") or "Sin clasificar",
            "ubicacion_x": h.get("ubicacion_x"),
            "ubicacion_y": h.get("ubicacion_y"),
            "imagen_representativa_url": clave,
            "imagenes_asociadas": [clave] if clave else [],
            "cantidad_detecciones": h.get("cantidad_detecciones") or 1,
            "probabilidad_promedio": h.get("probabilidad_promedio"),
        })
        if h.get("revision") and creado and creado.get("id"):
            extra(f"la revisión del hallazgo {n}", "PUT", f"hallazgos/{creado['id']}/revision", h["revision"])
    return rid


def _crear_edificacion(datos: Optional[dict], proyecto_id: int) -> int:
    """Crea la copia de la edificación. Si en ese proyecto ya hay una con el mismo nombre
    (la nube no acepta nombres repetidos), se le agrega «(importada)», «(importada 2)»…"""
    edif = {**_solo(datos, CAMPOS_EDIFICACION), "proyecto_id": proyecto_id}
    base = (edif.get("nombre") or "Edificación").strip()
    for intento in range(1, 11):
        edif["nombre"] = base if intento == 1 else f"{base} (importada{'' if intento == 2 else f' {intento - 1}'})"
        r = nube.reenviar("POST", "edificaciones", cuerpo=edif)
        if r.ok:
            return r.json()["id"]
        if r.status_code != 400:
            break
    raise requests.HTTPError(f"{r.status_code}: {r.text[:300]}")


def inspecciones_del_archivo(archivo: Dict[str, Any]) -> List[dict]:
    """Las inspecciones del archivo (versión 2: lista; versión 1: una sola, con sus partes sueltas)."""
    if isinstance(archivo.get("inspecciones"), list):
        return archivo["inspecciones"]
    insp = dict(archivo.get("inspeccion") or {})
    for k in ("trayectoria", "plano", "dictamen", "hallazgos"):
        insp[k] = archivo.get(k)
    return [insp] if archivo.get("inspeccion") else []


@router.post("/importar")
def importar(proyecto_id: int, edificacion_id: Optional[int] = None, archivo: Dict[str, Any] = Body(...)):
    if not nube.sesion_activa():
        raise HTTPException(401, "sin sesion")
    if archivo.get("formato") != FORMATO:
        raise HTTPException(400, "no es un archivo de G1 Structural Inspector")
    if int(archivo.get("version") or 0) > VERSION:
        raise HTTPException(400, "el archivo es de una versión más nueva de la app")
    avisos: List[str] = []
    robots: Dict[str, int] = {}
    try:
        # La edificación: una que ya tenés, o una copia nueva dentro del proyecto elegido
        if edificacion_id:
            eid = _get(f"edificaciones/{edificacion_id}")["id"]  # también comprueba que sea tuya
        else:
            eid = _crear_edificacion(archivo.get("edificacion"), proyecto_id)
        importadas = [_importar_inspeccion(eid, insp, n, avisos, robots)
                      for n, insp in enumerate(inspecciones_del_archivo(archivo), start=1)]
    except requests.RequestException as e:
        raise HTTPException(502, f"no se pudo crear la copia en la nube ({e})")
    return {"ok": True, "edificacion_id": eid, "inspecciones": len(importadas), "avisos": avisos}
