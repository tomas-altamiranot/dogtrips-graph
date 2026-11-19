"""Subgrafos para dibujar: cada funcion devuelve los nodos y relaciones reales
que explican un resultado.

consultas.py contesta con tablas ("Gabriela, 4 perros, 4.42"). Este modulo
contesta con el DIBUJO de por que: los caminos que recorrio la consulta. Todas
las funciones devuelven el mismo formato, un dict con "nodos" y "aristas", que
cualquier interfaz puede dibujar. Aqui no hay nada de Streamlit ni de HTML.
"""

from __future__ import annotations

from collections import deque

from .conexion import leer_grafo


def _a_dict(grafo) -> dict:
    """Convierte un neo4j.graph.Graph en listas simples de nodos y aristas."""
    nodos = []
    for n in grafo.nodes:
        props = dict(n.items())
        etiqueta = next(iter(n.labels), "?")
        nombre = props.get("name") or props.get("id") or etiqueta
        if etiqueta == "Walk":
            nombre = f"Paseo {props.get('type', '')} {props.get('rating', '')}/5"
        nodos.append({
            "key": n.element_id, "tipo": etiqueta, "nombre": nombre,
            "props": {k: str(v) if not isinstance(v, (int, float, bool, str, type(None))) else v
                      for k, v in props.items()},
        })
    aristas = [{
        "s": r.start_node.element_id, "d": r.end_node.element_id, "tipo": r.type,
        "props": {k: str(v) if not isinstance(v, (int, float, bool, str)) else v
                  for k, v in r.items()},
    } for r in grafo.relationships]
    return {"nodos": nodos, "aristas": aristas}


def distancias(sub: dict, centro_key: str) -> dict[str, int]:
    """Cuantos saltos separan a cada nodo del centro (busqueda en anchura)."""
    vecinos: dict[str, list[str]] = {}
    for a in sub["aristas"]:
        vecinos.setdefault(a["s"], []).append(a["d"])
        vecinos.setdefault(a["d"], []).append(a["s"])
    dist = {centro_key: 0}
    cola = deque([centro_key])
    while cola:
        x = cola.popleft()
        for y in vecinos.get(x, []):
            if y not in dist:
                dist[y] = dist[x] + 1
                cola.append(y)
    return dist


def clave_de(sub: dict, propiedad: str, valor) -> str | None:
    for n in sub["nodos"]:
        if n["props"].get(propiedad) == valor:
            return n["key"]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Vecindario: todo lo que hay a N saltos de un nodo
# ─────────────────────────────────────────────────────────────────────────────
# apoc.path.subgraphAll recorre en anchura y devuelve cada nodo una sola vez.
# Un MATCH p=(c)-[*1..3]-() devolveria TODOS los caminos posibles, que con
# 3 saltos son miles de filas repetidas para unos cuantos cientos de nodos.

Q_VECINDARIO = """
MATCH (c) WHERE c.id = $centro
CALL apoc.path.subgraphAll(c, {maxLevel: $saltos}) YIELD nodes, relationships
RETURN nodes, relationships
"""


def vecindario(centro: str, saltos: int) -> dict:
    return _a_dict(leer_grafo(Q_VECINDARIO, centro=centro, saltos=int(saltos)))


# ─────────────────────────────────────────────────────────────────────────────
# Explicacion de cada consulta, como caminos
# ─────────────────────────────────────────────────────────────────────────────

Q_EXPLICA_RECOMENDACION = """
// Consulta 1 dibujada: los caminos que unen al dueno con el paseador elegido
MATCH dueno = (yo:Owner)-[:OWNS]->(p:Dog {id: $perro})
MATCH red = (yo)-[:LIVES_IN|REFERRED*1..3]-(vecino:Owner)
WHERE vecino <> yo
MATCH paseo = (vecino)-[:OWNS]->(suyo:Dog)-[:JOINED]->(k:Walk)<-[:PERFORMED]-(w:Walker {id: $paseador})
WHERE k.rating >= 4 AND suyo <> p
RETURN dueno, red, paseo
"""


def explica_recomendacion(perro: str, paseador: str) -> dict:
    return _a_dict(leer_grafo(Q_EXPLICA_RECOMENDACION, perro=perro, paseador=paseador))


Q_EXPLICA_GRUPO = """
// Consulta 2 dibujada: los paseos buenos que unen a cada par del grupo,
// y los incidentes de sus integrantes (con quien NO pueden salir)
MATCH (a:Dog), (b:Dog)
WHERE a.id IN $perros AND b.id IN $perros AND elementId(a) < elementId(b)
MATCH juntos = (a)-[:JOINED]->(k:Walk)<-[:JOINED]-(b)
WHERE k.rating >= 4
RETURN juntos AS camino
UNION
MATCH incidente = (a:Dog)-[:CONFLICTED_WITH]-(:Dog)
WHERE a.id IN $perros
RETURN incidente AS camino
"""


def explica_grupo(perros: list[str]) -> dict:
    return _a_dict(leer_grafo(Q_EXPLICA_GRUPO, perros=perros))


Q_EXPLICA_CAMINO = """
// Consulta 3 dibujada: el camino mas corto, tal cual lo devuelve la base
MATCH (o:Owner {id: $dueno}), (w:Walker {id: $paseador})
MATCH ruta = shortestPath((o)-[:OWNS|JOINED|PERFORMED|RATED|REFERRED*..6]-(w))
RETURN ruta
"""


def explica_camino(dueno: str, paseador: str) -> dict:
    return _a_dict(leer_grafo(Q_EXPLICA_CAMINO, dueno=dueno, paseador=paseador))


Q_EXPLICA_ACREDITADOS = """
// Consulta 4 dibujada: rasgo del perro <- habilidad <- paseador
MATCH c = (d:Dog {id: $perro})-[:HAS_TRAIT]->(:Trait)<-[:QUALIFIES_FOR]-(:Skill)<-[:HAS_SKILL]-(w:Walker)
WHERE w.name IN $paseadores
RETURN c
"""


def explica_acreditados(perro: str, paseadores: list[str]) -> dict:
    return _a_dict(leer_grafo(Q_EXPLICA_ACREDITADOS, perro=perro, paseadores=paseadores))
