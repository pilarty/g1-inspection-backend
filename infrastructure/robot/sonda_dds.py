"""Escucha un topico DDS hasta recibir un mensaje o agotar el tiempo.

Corre en un proceso aparte (python -m infrastructure.robot.sonda_dds ...) porque
la configuracion de Cyclone DDS (interfaz de red) se fija al crear el dominio y
porque un fallo de la libreria nativa no debe tirar abajo el backend.
Solo escucha: nunca publica nada, asi que no puede mover el robot.

Imprime una linea JSON: {"ok": bool, "detalle": str, "ms": int}
"""
import argparse
import json
import os
import sys
import time
from xml.sax.saxutils import quoteattr


def configurar_interfaz(ip_interfaz):
    if ip_interfaz:
        os.environ["CYCLONEDDS_URI"] = (
            "<CycloneDDS><Domain id=\"any\"><General><Interfaces>"
            f"<NetworkInterface address={quoteattr(ip_interfaz)}/>"
            "</Interfaces></General></Domain></CycloneDDS>"
        )


def escuchar(dominio, timeout):
    from cyclonedds.core import Policy, Qos
    from cyclonedds.domain import DomainParticipant
    from cyclonedds.sub import DataReader
    from cyclonedds.topic import Topic

    from infrastructure.robot.tipos_dds import TOPICO_ESTADO, LowState_

    nombre, tipo = TOPICO_ESTADO, LowState_

    # Acepta CDR clasico (el del SDK de Unitree) y XCDR2
    qos = Qos(Policy.DataRepresentation(use_cdrv0_representation=True, use_xcdrv2_representation=True))
    inicio = time.monotonic()
    dp = DomainParticipant(dominio)
    lector = DataReader(dp, Topic(dp, nombre, tipo), qos=qos)
    while time.monotonic() - inicio < timeout:
        muestras = lector.take(N=1)
        if muestras:
            m = muestras[0]
            detalle = f"Llegó el estado del robot por {nombre} (tick {m.tick}, modo {m.mode_machine})."
            return True, detalle, inicio
        time.sleep(0.05)
    return False, f"No llegó ningún mensaje por {nombre} en {timeout:g} s.", inicio


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--canal", choices=["estado"], default="estado")
    p.add_argument("--dominio", type=int, required=True)
    p.add_argument("--interfaz", default="")
    p.add_argument("--timeout", type=float, default=4.0)
    a = p.parse_args()

    configurar_interfaz(a.interfaz)
    inicio = time.monotonic()
    try:
        ok, detalle, inicio = escuchar(a.dominio, a.timeout)
    except Exception as e:  # p. ej. la interfaz no existe
        ok, detalle = False, f"Error de DDS: {e}"
    print(json.dumps({"ok": ok, "detalle": detalle, "ms": int((time.monotonic() - inicio) * 1000)}), flush=True)
    sys.stdout.flush()
    os._exit(0)  # evita esperar al cierre lento de Cyclone DDS


if __name__ == "__main__":
    main()
