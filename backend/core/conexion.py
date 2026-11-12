"""Conexión a Neo4j AuraDB.

Este módulo es la única puerta de entrada a la base de datos. El resto de `core`
pide sesiones aquí y nunca construye su propio driver.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

# El .env vive en la raíz del repositorio, dos niveles arriba de este archivo.
RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(RAIZ / ".env")

_driver: Driver | None = None


class ErrorDeConexion(RuntimeError):
    """La aplicación no pudo hablar con AuraDB."""


def _leer_config() -> tuple[str, str, str, str | None]:
    """Lee las credenciales del entorno y falla temprano si falta alguna.

    Las credenciales nunca se escriben en el código: viajan por variables de
    entorno cargadas desde .env, que está excluido del control de versiones.
    """
    # Se usa "" como valor por omisión en lugar de None para que el tipo sea
    # str desde el inicio; la ausencia real se detecta abajo con `not valor`.
    uri = os.getenv("NEO4J_URI", "")
    usuario = os.getenv("NEO4J_USERNAME", "")
    password = os.getenv("NEO4J_PASSWORD", "")

    # En Aura la base no siempre se llama "neo4j": suele llevar el id de la
    # instancia. Si la variable viene vacía se pasa None y el driver usa la
    # base por defecto del usuario, que es lo correcto en la mayoría de casos.
    base = os.getenv("NEO4J_DATABASE") or None

    faltantes = [
        nombre
        for nombre, valor in (
            ("NEO4J_URI", uri),
            ("NEO4J_USERNAME", usuario),
            ("NEO4J_PASSWORD", password),
        )
        if not valor
    ]
    if faltantes:
        raise ErrorDeConexion(
            "Faltan variables de entorno: "
            + ", ".join(faltantes)
            + ". Copia .env.example como .env y rellena los valores."
        )
    return uri, usuario, password, base


def obtener_driver() -> Driver:
    """Devuelve el driver, creándolo la primera vez.

    El driver es caro de construir y administra su propio pool de conexiones,
    por lo que se reutiliza durante toda la vida del proceso. Crear uno por
    consulta desperdiciaría conexiones contra la capa gratuita de Aura.
    """
    global _driver
    if _driver is None:
        uri, usuario, password, _ = _leer_config()
        _driver = GraphDatabase.driver(uri, auth=(usuario, password))
    return _driver


def verificar_conexion() -> str:
    """Comprueba que AuraDB responde de verdad.

    El constructor del driver no contacta al servidor: solo guarda la
    configuración. verify_connectivity() sí viaja por la red, de modo que un
    servidor caído o unas credenciales inválidas se detectan aquí y no más
    tarde, en medio de una consulta.

    Returns:
        La URI a la que se conectó, útil para mostrarla en la demo.

    Raises:
        ErrorDeConexion: si el servidor no responde o las credenciales fallan.
    """
    uri, _, _, _ = _leer_config()
    try:
        obtener_driver().verify_connectivity()
    except AuthError as exc:
        raise ErrorDeConexion(
            "Credenciales rechazadas por AuraDB. Revisa NEO4J_USERNAME y NEO4J_PASSWORD."
        ) from exc
    except ServiceUnavailable as exc:
        raise ErrorDeConexion(
            f"No se pudo alcanzar {uri}. Revisa la URI y que la instancia esté activa "
            "(Aura Free suspende las instancias inactivas por varios días)."
        ) from exc
    return uri


@contextmanager
def sesion():
    """Entrega una sesión y garantiza su cierre.

    Uso:
        with sesion() as s:
            resultado = s.run("MATCH (n) RETURN count(n) AS total")
    """
    _, _, _, base = _leer_config()
    with obtener_driver().session(database=base) as s:
        yield s


def cerrar() -> None:
    """Cierra el driver y libera el pool de conexiones."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
