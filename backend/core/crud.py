"""CRUD sobre los tres actores de DogTrips: duenos, perros y paseadores.

Crear, leer, actualizar y borrar. Cada funcion es una sola consulta Cypher, y
todas pasan por leer()/escribir() de conexion.py, que reintentan solas si la
red con AuraDB falla.

Diferencia con un CRUD relacional: aqui "crear un perro" no es insertar una
fila. Es crear un NODO y, en la misma consulta, sus RELACIONES: con su dueno
(OWNS) y con sus rasgos (HAS_TRAIT). En SQL eso serian varios INSERT en tablas
distintas (perros, perro_rasgo); aqui es un solo patron.
"""

from __future__ import annotations

from .conexion import escribir, leer

TAMANOS = ("pequeno", "mediano", "grande")
NIVELES = ("baja", "media", "alta")
FUERZAS = ("media", "alta")


class ErrorDeDatos(ValueError):
    """Un dato no es valido: id inexistente, zona o rasgo desconocido, etc."""


def _validar(valor, permitidos, campo):
    if valor is not None and valor not in permitidos:
        raise ErrorDeDatos(f"{campo} debe ser uno de {permitidos}, no '{valor}'.")


def _solo(cambios: dict, permitidos: set[str]) -> dict:
    """Filtra los campos que se pueden editar y descarta los vacios.

    Se usa con SET n += $cambios. Los nombres de propiedad no pueden ir como
    parametro en Cypher, pero un mapa completo si; filtrar las llaves aqui
    impide que alguien cambie el id o invente propiedades.
    """
    return {k: v for k, v in cambios.items() if k in permitidos and v is not None}


def _validar_lista(valores: list[str], catalogo: str, campo: str) -> None:
    """Revisa que cada valor exista en el catalogo ANTES de escribir.

    Se valida antes y no despues porque una consulta de escritura que ya creo
    el nodo no se puede "deshacer a medias": si un rasgo no existe, el perro
    quedaria creado sin el. Mejor rechazar la peticion completa.
    """
    if not valores:
        raise ErrorDeDatos(f"Indica al menos un valor en {campo}.")
    validos = set(catalogos()[catalogo])
    malos = [v for v in valores if v not in validos]
    if malos:
        raise ErrorDeDatos(f"{campo} desconocidos: {malos}. Opciones: {sorted(validos)}")


# ─────────────────────────────────────────────────────────────────────────────
# Catalogos (para mostrar opciones en el menu)
# ─────────────────────────────────────────────────────────────────────────────

def catalogos() -> dict:
    fila = leer(
        """
        RETURN COLLECT { MATCH (z:Zone)  RETURN z.name ORDER BY z.name } AS zonas,
               COLLECT { MATCH (t:Trait) RETURN t.name ORDER BY t.name } AS rasgos,
               COLLECT { MATCH (s:Skill) RETURN s.name ORDER BY s.name } AS habilidades
        """
    )[0]
    return fila


# ═════════════════════════════════════════════════════════════════════════════
# DUENOS  (:Owner)-[:LIVES_IN]->(:Zone)
# ═════════════════════════════════════════════════════════════════════════════

def crear_dueno(name: str, phone: str, zona: str) -> dict:
    # El id se calcula dentro de la misma consulta: el numero mas alto que
    # exista mas uno (own-041, own-042...). La restriccion de unicidad creada
    # en seed.py garantiza que nunca haya dos iguales.
    filas = escribir(
        """
        MATCH (z:Zone {name: $zona})
        CALL () {
            MATCH (o:Owner)
            RETURN coalesce(max(toInteger(substring(o.id, 4))), 0) + 1 AS n
        }
        CREATE (o:Owner {id: 'own-' + right('000' + toString(n), 3),
                         name: $name, phone: $phone})
        CREATE (o)-[:LIVES_IN]->(z)
        RETURN o.id AS id, o.name AS name
        """,
        name=name, phone=phone, zona=zona,
    )
    if not filas:
        raise ErrorDeDatos(f"La zona '{zona}' no existe.")
    return filas[0]


def listar_duenos() -> list[dict]:
    return leer(
        """
        MATCH (o:Owner)-[:LIVES_IN]->(z:Zone)
        RETURN o.id AS id, o.name AS name, o.phone AS phone, z.name AS zona,
               COUNT { (o)-[:OWNS]->(:Dog) } AS perros
        ORDER BY o.id
        """
    )


def obtener_dueno(id: str) -> dict | None:
    filas = leer(
        """
        MATCH (o:Owner {id: $id})
        OPTIONAL MATCH (o)-[:LIVES_IN]->(z:Zone)
        RETURN o.id AS id, o.name AS name, o.phone AS phone, z.name AS zona,
               COLLECT { MATCH (o)-[:OWNS]->(d:Dog) RETURN d.name + ' (' + d.id + ')' } AS perros
        """,
        id=id,
    )
    return filas[0] if filas else None


def actualizar_dueno(id: str, name: str | None = None, phone: str | None = None,
                     zona: str | None = None) -> dict:
    if zona:
        _validar_lista([zona], "zonas", "zona")
    cambios = _solo({"name": name, "phone": phone}, {"name", "phone"})
    filas = escribir(
        """
        MATCH (o:Owner {id: $id})
        SET o += $cambios
        RETURN o.id AS id
        """,
        id=id, cambios=cambios,
    )
    if not filas:
        raise ErrorDeDatos(f"No existe el dueno {id}.")
    if zona:
        # Mudarse = borrar la relacion vieja y crear la nueva. En el grafo la
        # direccion no es una columna: es una arista hacia otro nodo.
        if not escribir(
            """
            MATCH (o:Owner {id: $id}), (z:Zone {name: $zona})
            OPTIONAL MATCH (o)-[vieja:LIVES_IN]->()
            DELETE vieja
            CREATE (o)-[:LIVES_IN]->(z)
            RETURN o.id AS id
            """,
            id=id, zona=zona,
        ):
            raise ErrorDeDatos(f"La zona '{zona}' no existe.")
    return obtener_dueno(id)


def borrar_dueno(id: str) -> dict:
    # Decision de diseno: borrar un dueno borra tambien sus perros, porque un
    # perro sin dueno no tiene sentido en la plataforma. Los paseos (:Walk) se
    # conservan: son historia y otros perros pudieron estar en ellos.
    # DETACH DELETE borra el nodo junto con todas sus relaciones; un DELETE
    # simple fallaria porque Neo4j no deja relaciones "colgando".
    filas = escribir(
        """
        MATCH (o:Owner {id: $id})
        OPTIONAL MATCH (o)-[:OWNS]->(d:Dog)
        WITH o, collect(d) AS perros, o.name AS nombre
        FOREACH (d IN perros | DETACH DELETE d)
        DETACH DELETE o
        RETURN nombre, size(perros) AS perrosBorrados
        """,
        id=id,
    )
    if not filas:
        raise ErrorDeDatos(f"No existe el dueno {id}.")
    return filas[0]


# ═════════════════════════════════════════════════════════════════════════════
# PERROS  (:Owner)-[:OWNS]->(:Dog)-[:HAS_TRAIT]->(:Trait)
# ═════════════════════════════════════════════════════════════════════════════

CAMPOS_PERRO = {"name", "breed", "sizeCategory", "weightKg", "ageMonths", "energyLevel"}


def crear_perro(owner_id: str, name: str, breed: str, sizeCategory: str,
                weightKg: int, ageMonths: int, energyLevel: str,
                rasgos: list[str]) -> dict:
    _validar(sizeCategory, TAMANOS, "sizeCategory")
    _validar(energyLevel, NIVELES, "energyLevel")
    _validar_lista(rasgos, "rasgos", "rasgos")
    filas = escribir(
        """
        MATCH (o:Owner {id: $owner})
        CALL () {
            MATCH (d:Dog)
            RETURN coalesce(max(toInteger(substring(d.id, 4))), 0) + 1 AS n
        }
        CREATE (d:Dog {id: 'dog-' + right('000' + toString(n), 3),
                       name: $name, breed: $breed, sizeCategory: $size,
                       weightKg: $peso, ageMonths: $edad, energyLevel: $energia})
        CREATE (o)-[:OWNS]->(d)
        WITH d
        CALL (d) {
            UNWIND $rasgos AS r
            MATCH (t:Trait {name: r})
            CREATE (d)-[:HAS_TRAIT]->(t)
        }
        RETURN d.id AS id, d.name AS name
        """,
        owner=owner_id, name=name, breed=breed, size=sizeCategory,
        peso=weightKg, edad=ageMonths, energia=energyLevel, rasgos=rasgos,
    )
    if not filas:
        raise ErrorDeDatos(f"No existe el dueno {owner_id}.")
    return filas[0]


def listar_perros() -> list[dict]:
    return leer(
        """
        MATCH (o:Owner)-[:OWNS]->(d:Dog)
        RETURN d.id AS id, d.name AS name, d.breed AS breed,
               d.sizeCategory AS tamano, d.energyLevel AS energia,
               o.name AS dueno,
               COLLECT { MATCH (d)-[:HAS_TRAIT]->(t) RETURN t.name } AS rasgos
        ORDER BY d.id
        """
    )


def obtener_perro(id: str) -> dict | None:
    filas = leer(
        """
        MATCH (d:Dog {id: $id})
        OPTIONAL MATCH (o:Owner)-[:OWNS]->(d)
        RETURN d {.*} AS perro, o.name AS dueno,
               COLLECT { MATCH (d)-[:HAS_TRAIT]->(t) RETURN t.name } AS rasgos,
               COUNT { (d)-[:JOINED]->(:Walk) } AS paseos
        """,
        id=id,
    )
    return filas[0] if filas else None


def actualizar_perro(id: str, rasgos: list[str] | None = None, **campos) -> dict:
    _validar(campos.get("sizeCategory"), TAMANOS, "sizeCategory")
    _validar(campos.get("energyLevel"), NIVELES, "energyLevel")
    if rasgos:
        _validar_lista(rasgos, "rasgos", "rasgos")
    if not escribir(
        "MATCH (d:Dog {id: $id}) SET d += $cambios RETURN d.id AS id",
        id=id, cambios=_solo(campos, CAMPOS_PERRO),
    ):
        raise ErrorDeDatos(f"No existe el perro {id}.")
    if rasgos:
        # Reemplazar los rasgos = borrar sus aristas HAS_TRAIT y crear las
        # nuevas. Los nodos :Trait no se tocan: los comparten todos los perros.
        escribir(
            """
            MATCH (d:Dog {id: $id})
            OPTIONAL MATCH (d)-[viejo:HAS_TRAIT]->()
            DELETE viejo
            WITH DISTINCT d
            UNWIND $rasgos AS r
            MATCH (t:Trait {name: r})
            CREATE (d)-[:HAS_TRAIT]->(t)
            """,
            id=id, rasgos=rasgos,
        )
    return obtener_perro(id)


def borrar_perro(id: str) -> dict:
    filas = escribir(
        """
        MATCH (d:Dog {id: $id})
        WITH d, d.name AS nombre
        DETACH DELETE d
        RETURN nombre
        """,
        id=id,
    )
    if not filas:
        raise ErrorDeDatos(f"No existe el perro {id}.")
    return filas[0]


# ═════════════════════════════════════════════════════════════════════════════
# PASEADORES  (:Walker)-[:SERVES]->(:Zone), (:Walker)-[:HAS_SKILL]->(:Skill)
# ═════════════════════════════════════════════════════════════════════════════

CAMPOS_PASEADOR = {"name", "experienceMonths", "strengthLevel", "verified"}


def crear_paseador(name: str, experienceMonths: int, strengthLevel: str,
                   zonas: list[str], habilidades: list[str]) -> dict:
    # Un paseador nuevo entra sin verificar y sin calificacion (null, no 0):
    # todavia nadie lo ha calificado.
    _validar(strengthLevel, FUERZAS, "strengthLevel")
    _validar_lista(zonas, "zonas", "zonas")
    _validar_lista(habilidades, "habilidades", "habilidades")
    filas = escribir(
        """
        CALL () {
            MATCH (w:Walker)
            RETURN coalesce(max(toInteger(substring(w.id, 4))), 0) + 1 AS n
        }
        CREATE (w:Walker {id: 'wlk-' + right('000' + toString(n), 3),
                          name: $name, experienceMonths: $exp,
                          strengthLevel: $fuerza, verified: false, ratingAvg: null})
        WITH w
        CALL (w) {
            UNWIND $zonas AS z
            MATCH (zona:Zone {name: z})
            CREATE (w)-[:SERVES]->(zona)
        }
        CALL (w) {
            UNWIND $habilidades AS h
            MATCH (s:Skill {name: h})
            CREATE (w)-[:HAS_SKILL]->(s)
        }
        RETURN w.id AS id, w.name AS name
        """,
        name=name, exp=experienceMonths, fuerza=strengthLevel,
        zonas=zonas, habilidades=habilidades,
    )
    return filas[0]


def listar_paseadores() -> list[dict]:
    return leer(
        """
        MATCH (w:Walker)
        RETURN w.id AS id, w.name AS name, w.experienceMonths AS meses,
               w.verified AS verificado, w.ratingAvg AS calificacion,
               COLLECT { MATCH (w)-[:SERVES]->(z) RETURN z.name } AS zonas
        ORDER BY w.id
        """
    )


def obtener_paseador(id: str) -> dict | None:
    filas = leer(
        """
        MATCH (w:Walker {id: $id})
        RETURN w {.*} AS paseador,
               COLLECT { MATCH (w)-[:SERVES]->(z) RETURN z.name } AS zonas,
               COLLECT { MATCH (w)-[:HAS_SKILL]->(s) RETURN s.name } AS habilidades,
               COUNT { (w)-[:PERFORMED]->(:Walk) } AS paseos
        """,
        id=id,
    )
    return filas[0] if filas else None


def actualizar_paseador(id: str, zonas: list[str] | None = None,
                        habilidades: list[str] | None = None, **campos) -> dict:
    _validar(campos.get("strengthLevel"), FUERZAS, "strengthLevel")
    if zonas:
        _validar_lista(zonas, "zonas", "zonas")
    if habilidades:
        _validar_lista(habilidades, "habilidades", "habilidades")
    if not escribir(
        "MATCH (w:Walker {id: $id}) SET w += $cambios RETURN w.id AS id",
        id=id, cambios=_solo(campos, CAMPOS_PASEADOR),
    ):
        raise ErrorDeDatos(f"No existe el paseador {id}.")
    if zonas:
        escribir(
            """
            MATCH (w:Walker {id: $id})
            OPTIONAL MATCH (w)-[vieja:SERVES]->()
            DELETE vieja
            WITH DISTINCT w
            UNWIND $zonas AS z
            MATCH (zona:Zone {name: z})
            CREATE (w)-[:SERVES]->(zona)
            """,
            id=id, zonas=zonas,
        )
    if habilidades:
        escribir(
            """
            MATCH (w:Walker {id: $id})
            OPTIONAL MATCH (w)-[vieja:HAS_SKILL]->()
            DELETE vieja
            WITH DISTINCT w
            UNWIND $habilidades AS h
            MATCH (s:Skill {name: h})
            CREATE (w)-[:HAS_SKILL]->(s)
            """,
            id=id, habilidades=habilidades,
        )
    return obtener_paseador(id)


def borrar_paseador(id: str) -> dict:
    # Sus paseos se conservan (son historia de los perros), solo pierden la
    # arista PERFORMED. DETACH DELETE se encarga de eso.
    filas = escribir(
        """
        MATCH (w:Walker {id: $id})
        WITH w, w.name AS nombre
        DETACH DELETE w
        RETURN nombre
        """,
        id=id,
    )
    if not filas:
        raise ErrorDeDatos(f"No existe el paseador {id}.")
    return filas[0]
