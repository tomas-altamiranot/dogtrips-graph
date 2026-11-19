"""Conexión a Neo4j AuraDB.

Este módulo es la única puerta de entrada a la base de datos. El resto de `core`
pide sesiones aquí y nunca construye su propio driver.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path

import certifi
from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase, Result, RoutingControl
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

# El .env vive en la raíz del repositorio, dos niveles arriba de este archivo.
RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(RAIZ / ".env")

# En Windows, el módulo ssl de Python verifica contra el almacén de certificados
# del sistema operativo, no contra certifi. El certificado de AuraDB encadena a
# "SSL.com TLS RSA Root CA 2022", una raíz que Windows no siempre tiene
# instalada, y la conexión falla con CERTIFICATE_VERIFY_FAILED aunque el
# certificado del servidor sea válido.
#
# Apuntar SSL_CERT_FILE al bundle de certifi, que sí incluye esa raíz, resuelve
# el problema SIN desactivar la verificación: la alternativa habitual
# (neo4j+ssc://) acepta cualquier certificado y deja la conexión expuesta a
# suplantación. Se usa setdefault para respetar un valor que ya venga del
# entorno.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

# Cuando el driver reintenta una consulta (ver leer() mas abajo) escribe un
# aviso por cada intento fallido, algunos con nivel ERROR justo antes de lanzar
# la excepcion que el reintento atrapa. Son reintentos que terminan bien, asi
# que el log del driver se silencia para no ensuciar la terminal. Un fallo
# definitivo NO se pierde: llega al codigo como excepcion y se muestra.
logging.getLogger("neo4j").setLevel(logging.CRITICAL)

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
    # verify_connectivity() no reintenta por su cuenta, y el saludo TLS con
    # Aura a veces se corta a medias (ver leer()). Por eso la verificacion es
    # una consulta trivial que pasa por leer(): hereda sus reintentos de hasta
    # 30 segundos antes de declarar que la base no responde.
    try:
        leer("RETURN 1 AS ok")
    except AuthError as exc:
        raise ErrorDeConexion(
            "Credenciales rechazadas por AuraDB. Revisa NEO4J_USERNAME y NEO4J_PASSWORD."
        ) from exc
    except (ServiceUnavailable, SessionExpired) as exc:
        raise ErrorDeConexion(
            f"No se pudo alcanzar {uri}. Revisa la URI y que la instancia esté activa "
            "(Aura Free suspende las instancias inactivas por varios días)."
        ) from exc
    return uri


# ─────────────────────────────────────────────────────────────────────────────
# Ejecutar consultas con reintento automatico
# ─────────────────────────────────────────────────────────────────────────────
# Desde algunas redes, el saludo cifrado (TLS) con AuraDB se corta a medias de
# vez en cuando (SSL UNEXPECTED_EOF). No es un error de la consulta: si se
# vuelve a intentar un segundo despues, funciona.
#
# session.run() NO reintenta. driver.execute_query() si: corre la consulta
# dentro de una transaccion administrada que reintenta sola ante
# ServiceUnavailable y SessionExpired durante hasta 30 segundos (documentacion
# oficial del driver). Por eso todo el proyecto ejecuta Cypher a traves de
# estas dos funciones y no con sesiones sueltas.
#
# leer() pide un servidor de lectura y escribir() uno de escritura; en Aura
# Free es el mismo, pero declararlo deja claro que hace cada consulta.


def leer(consulta: str, **parametros) -> list[dict]:
    """Ejecuta una consulta de solo lectura y devuelve las filas como dicts."""
    _, _, _, base = _leer_config()
    filas, _, _ = obtener_driver().execute_query(
        consulta, parametros, routing_=RoutingControl.READ, database_=base
    )
    return [f.data() for f in filas]


def leer_grafo(consulta: str, **parametros):
    """Ejecuta una consulta de lectura y devuelve un neo4j.graph.Graph.

    Result.graph() junta todos los nodos y relaciones que aparecen en el
    resultado (sueltos, en listas o dentro de caminos) en un solo objeto. Es lo
    que se dibuja en el cliente: el dibujo muestra exactamente lo que devolvio
    la base, no una reconstruccion.
    """
    _, _, _, base = _leer_config()
    return obtener_driver().execute_query(
        consulta, parametros, routing_=RoutingControl.READ, database_=base,
        result_transformer_=Result.graph,
    )


def escribir(consulta: str, **parametros) -> list[dict]:
    """Ejecuta una consulta que modifica el grafo y devuelve las filas."""
    _, _, _, base = _leer_config()
    filas, _, _ = obtener_driver().execute_query(
        consulta, parametros, routing_=RoutingControl.WRITE, database_=base
    )
    return [f.data() for f in filas]


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
