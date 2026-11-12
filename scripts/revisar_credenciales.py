"""Revisa la forma de las credenciales sin mostrar sus valores.

Uso:  uv run python scripts/revisar_credenciales.py

Imprime solo caracteristicas (longitud, espacios, comillas) para poder
diagnosticar un fallo de autenticacion sin exponer la contrasena.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]
ARCHIVO = RAIZ / ".env"

COMILLAS = ('"', "'")


def describir(nombre: str, valor: str | None, ocultar: bool) -> None:
    if valor is None:
        print(f"{nombre:<16} FALTA (no esta definida)")
        return
    if not ocultar:
        print(f"{nombre:<16} {valor!r}")
        return
    bordes = valor != valor.strip()
    comilla = valor[:1] in COMILLAS or valor[-1:] in COMILLAS
    print(f"{nombre:<16} largo={len(valor)}  espacios_en_bordes={bordes}  comillas={comilla}")


def main() -> None:
    print(f"archivo .env : {ARCHIVO}")
    print(f"existe       : {ARCHIVO.exists()}")
    print()

    load_dotenv(ARCHIVO)

    describir("NEO4J_URI", os.getenv("NEO4J_URI"), ocultar=False)
    describir("NEO4J_USERNAME", os.getenv("NEO4J_USERNAME"), ocultar=False)
    describir("NEO4J_DATABASE", os.getenv("NEO4J_DATABASE"), ocultar=False)
    describir("NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD"), ocultar=True)

    print()
    print("Referencia: una contrasena de Aura suele tener 43 caracteres,")
    print("sin espacios en los bordes y sin comillas.")


if __name__ == "__main__":
    main()
