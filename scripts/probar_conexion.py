"""Comprueba que la aplicacion alcanza AuraDB y muestra el estado del grafo.

Uso:  uv run python scripts/probar_conexion.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from core.conexion import ErrorDeConexion, cerrar, leer, verificar_conexion


def main() -> int:
    try:
        uri = verificar_conexion()
    except ErrorDeConexion as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Conexion establecida con {uri}")

    nodos = leer("MATCH (n) RETURN count(n) AS total")[0]["total"]
    rels = leer("MATCH ()-[r]->() RETURN count(r) AS total")[0]["total"]
    etiquetas = leer("CALL db.labels() YIELD label RETURN collect(label) AS l")[0]["l"]

    print(f"  nodos        : {nodos}")
    print(f"  relaciones   : {rels}")
    print(f"  etiquetas    : {etiquetas or '(ninguna)'}")

    cerrar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
