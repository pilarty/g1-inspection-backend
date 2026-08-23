from typing import List

from models.schemas import TipoDanoIn


def calcular_severidad(tipos: List[TipoDanoIn]) -> str:
    """La severidad se basa en la probabilidad más alta entre los
    tipos de daño detectados.
    Ajustar estos umbrales según lo que decidan en el TFI."""
    if not tipos:
        return "low"
    prob_max = max(t.probabilidad for t in tipos)
    if prob_max >= 0.85:
        return "critical"
    if prob_max >= 0.65:
        return "high"
    if prob_max >= 0.45:
        return "medium"
    return "low"
