"""Menu de terminal para el CRUD de duenos, perros y paseadores.

Uso:  uv run python scripts/crud.py

Toda la logica vive en core/crud.py. Este archivo solo pregunta y muestra:
si manana hubiera una interfaz web, core/crud.py no cambiaria.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from core import crud  # noqa: E402
from core.conexion import ErrorDeConexion, cerrar, verificar_conexion  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Ayudas para preguntar
# ─────────────────────────────────────────────────────────────────────────────

def pedir(texto: str, obligatorio: bool = True) -> str | None:
    """Pide un texto. Si no es obligatorio, Enter vacio devuelve None."""
    while True:
        valor = input(f"  {texto}: ").strip()
        if valor or not obligatorio:
            return valor or None
        print("    (obligatorio)")


def pedir_entero(texto: str, obligatorio: bool = True) -> int | None:
    while True:
        valor = pedir(texto, obligatorio)
        if valor is None:
            return None
        if valor.isdigit():
            return int(valor)
        print("    (escribe un numero)")


def pedir_opcion(texto: str, opciones, obligatorio: bool = True) -> str | None:
    """Muestra opciones numeradas y devuelve la elegida."""
    opciones = list(opciones)
    print(f"  {texto}:")
    for i, o in enumerate(opciones, 1):
        print(f"     {i}. {o}")
    while True:
        valor = pedir("numero", obligatorio)
        if valor is None:
            return None
        if valor.isdigit() and 1 <= int(valor) <= len(opciones):
            return opciones[int(valor) - 1]
        print("    (numero fuera de rango)")


def pedir_varias(texto: str, opciones, obligatorio: bool = True) -> list[str] | None:
    """Varias opciones separadas por coma: 1,3,4."""
    opciones = list(opciones)
    print(f"  {texto} (separa con comas, ej. 1,3):")
    for i, o in enumerate(opciones, 1):
        print(f"     {i}. {o}")
    while True:
        valor = pedir("numeros", obligatorio)
        if valor is None:
            return None
        partes = [p.strip() for p in valor.split(",")]
        if all(p.isdigit() and 1 <= int(p) <= len(opciones) for p in partes):
            return [opciones[int(p) - 1] for p in partes]
        print("    (revisa los numeros)")


def tabla(filas: list[dict]) -> None:
    if not filas:
        print("  (sin resultados)")
        return
    for f in filas:
        print("  " + " | ".join(f"{k}={v}" for k, v in f.items()))
    print(f"  -- {len(filas)} registro(s)")


def ficha(datos: dict | None) -> None:
    if not datos:
        print("  No existe.")
        return
    for k, v in datos.items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                print(f"  {k2:<18} {v2}")
        else:
            print(f"  {k:<18} {v}")


def confirmar(texto: str) -> bool:
    return (input(f"  {texto} (s/n): ").strip().lower() == "s")


# ─────────────────────────────────────────────────────────────────────────────
# Acciones por entidad
# ─────────────────────────────────────────────────────────────────────────────

def menu_duenos(cat: dict) -> None:
    accion = pedir_opcion("Duenos", ["Listar", "Ver uno", "Crear", "Actualizar", "Borrar"])
    if accion == "Listar":
        tabla(crud.listar_duenos())
    elif accion == "Ver uno":
        ficha(crud.obtener_dueno(pedir("id (ej. own-001)")))
    elif accion == "Crear":
        r = crud.crear_dueno(pedir("nombre"), pedir("telefono"),
                             pedir_opcion("zona", cat["zonas"]))
        print(f"  Creado: {r}")
    elif accion == "Actualizar":
        id_ = pedir("id")
        ficha(crud.obtener_dueno(id_))
        print("  (Enter para dejar igual)")
        ficha(crud.actualizar_dueno(
            id_, name=pedir("nombre", False), phone=pedir("telefono", False),
            zona=pedir_opcion("zona", cat["zonas"], False),
        ))
    elif accion == "Borrar":
        id_ = pedir("id")
        ficha(crud.obtener_dueno(id_))
        if confirmar("Se borraran tambien sus perros. Continuar?"):
            print(f"  Borrado: {crud.borrar_dueno(id_)}")


def menu_perros(cat: dict) -> None:
    accion = pedir_opcion("Perros", ["Listar", "Ver uno", "Crear", "Actualizar", "Borrar"])
    if accion == "Listar":
        tabla(crud.listar_perros())
    elif accion == "Ver uno":
        ficha(crud.obtener_perro(pedir("id (ej. dog-045)")))
    elif accion == "Crear":
        r = crud.crear_perro(
            owner_id=pedir("id del dueno (ej. own-001)"),
            name=pedir("nombre"),
            breed=pedir("raza"),
            sizeCategory=pedir_opcion("tamano", crud.TAMANOS),
            weightKg=pedir_entero("peso en kg"),
            ageMonths=pedir_entero("edad en meses"),
            energyLevel=pedir_opcion("energia", crud.NIVELES),
            rasgos=pedir_varias("rasgos", cat["rasgos"]),
        )
        print(f"  Creado: {r}")
    elif accion == "Actualizar":
        id_ = pedir("id")
        ficha(crud.obtener_perro(id_))
        print("  (Enter para dejar igual)")
        ficha(crud.actualizar_perro(
            id_,
            name=pedir("nombre", False),
            breed=pedir("raza", False),
            sizeCategory=pedir_opcion("tamano", crud.TAMANOS, False),
            weightKg=pedir_entero("peso en kg", False),
            ageMonths=pedir_entero("edad en meses", False),
            energyLevel=pedir_opcion("energia", crud.NIVELES, False),
            rasgos=pedir_varias("rasgos (reemplaza los actuales)", cat["rasgos"], False),
        ))
    elif accion == "Borrar":
        id_ = pedir("id")
        ficha(crud.obtener_perro(id_))
        if confirmar("Borrar este perro?"):
            print(f"  Borrado: {crud.borrar_perro(id_)}")


def menu_paseadores(cat: dict) -> None:
    accion = pedir_opcion("Paseadores", ["Listar", "Ver uno", "Crear", "Actualizar", "Borrar"])
    if accion == "Listar":
        tabla(crud.listar_paseadores())
    elif accion == "Ver uno":
        ficha(crud.obtener_paseador(pedir("id (ej. wlk-001)")))
    elif accion == "Crear":
        r = crud.crear_paseador(
            name=pedir("nombre"),
            experienceMonths=pedir_entero("meses de experiencia"),
            strengthLevel=pedir_opcion("fuerza", crud.FUERZAS),
            zonas=pedir_varias("zonas que cubre", cat["zonas"]),
            habilidades=pedir_varias("habilidades", cat["habilidades"]),
        )
        print(f"  Creado: {r}")
    elif accion == "Actualizar":
        id_ = pedir("id")
        ficha(crud.obtener_paseador(id_))
        print("  (Enter para dejar igual)")
        verificado = pedir_opcion("verificado", ["si", "no"], False)
        ficha(crud.actualizar_paseador(
            id_,
            name=pedir("nombre", False),
            experienceMonths=pedir_entero("meses de experiencia", False),
            strengthLevel=pedir_opcion("fuerza", crud.FUERZAS, False),
            verified=None if verificado is None else verificado == "si",
            zonas=pedir_varias("zonas (reemplaza las actuales)", cat["zonas"], False),
            habilidades=pedir_varias("habilidades (reemplaza)", cat["habilidades"], False),
        ))
    elif accion == "Borrar":
        id_ = pedir("id")
        ficha(crud.obtener_paseador(id_))
        if confirmar("Borrar este paseador? Sus paseos se conservan."):
            print(f"  Borrado: {crud.borrar_paseador(id_)}")


def main() -> int:
    try:
        print(f"Conectado a {verificar_conexion()}")
    except ErrorDeConexion as exc:
        print(f"ERROR: {exc}")
        return 1
    cat = crud.catalogos()
    menus = {"Duenos": menu_duenos, "Perros": menu_perros, "Paseadores": menu_paseadores}

    while True:
        print("\n=== DogTrips · CRUD ===")
        eleccion = pedir_opcion("Que quieres administrar", [*menus, "Salir"])
        if eleccion == "Salir":
            break
        try:
            menus[eleccion](cat)
        except crud.ErrorDeDatos as exc:
            # Errores de datos (id que no existe, rasgo invalido): se avisan y
            # el menu sigue. No tiene sentido tumbar el programa por un typo.
            print(f"  ERROR: {exc}")

    cerrar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
