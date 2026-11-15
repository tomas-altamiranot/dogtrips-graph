"""Las cinco consultas especializadas de DogTrips.

Cada funcion recibe parametros y devuelve listas de diccionarios. Ninguna
imprime nada: quien decide como mostrar los resultados es la capa de arriba.

El Cypher vive en constantes al inicio de cada seccion para poder leerlo de
corrido, sin el ruido de Python alrededor.
"""

from __future__ import annotations

from .conexion import sesion

# ═════════════════════════════════════════════════════════════════════════════
# 1. Recomendacion de paseador por perros parecidos
# ═════════════════════════════════════════════════════════════════════════════
# Recorrido de cuatro saltos:
#   mi perro -> sus rasgos -> otros perros con esos rasgos -> sus paseos -> paseador
#
# Lo que demuestra: un ranking por calificacion promedio ordena a los paseadores
# en abstracto. Este los ordena por desempeno CON PERROS COMO EL MIO, que es una
# pregunta distinta y mas util.

Q_RECOMENDAR = """
MATCH (p:Dog {id: $perro})-[:HAS_TRAIT]->(t:Trait)<-[:HAS_TRAIT]-(similar:Dog)
WHERE similar <> p
MATCH (similar)-[:JOINED]->(k:Walk)<-[:PERFORMED]-(w:Walker)
WHERE k.rating >= $minimo
RETURN w.id                    AS id,
       w.name                  AS paseador,
       count(DISTINCT similar) AS perrosParecidos,
       round(avg(k.rating), 2) AS calificacionConParecidos,
       w.ratingAvg             AS promedioGeneral,
       w.verified              AS verificado
ORDER BY perrosParecidos DESC, calificacionConParecidos DESC
LIMIT $limite
"""


def recomendar_paseadores(perro: str, minimo: int = 4, limite: int = 5) -> list[dict]:
    """Paseadores con buen historial en perros que comparten rasgos con este."""
    with sesion() as s:
        return [r.data() for r in s.run(Q_RECOMENDAR, perro=perro, minimo=minimo, limite=limite)]


# ═════════════════════════════════════════════════════════════════════════════
# 2. Armado de un paseo grupal compatible  (LA CONSULTA ESTRELLA)
# ═════════════════════════════════════════════════════════════════════════════
# Un clique: un grupo donde TODAS las parejas funcionan, no solo las que incluyen
# al perro base. La compatibilidad no es transitiva, asi que hay que comprobar
# los tres pares.
#
# La compatibilidad no esta guardada en ninguna parte: se infiere de haber
# coincidido en un paseo bien calificado, y se descarta si hay un incidente.
#
# Contra SQL: cada par necesita su propio NOT EXISTS, y el numero de pares crece
# con el tamano del grupo (3 perros -> 3 pares, 5 perros -> 10). La consulta SQL
# hay que reescribirla cada vez que cambia el tamano del grupo.

Q_GRUPO = """
// A y B, cada uno compatible con el perro base
MATCH (base:Dog {id: $perro})-[:JOINED]->(w1:Walk)<-[:JOINED]-(a:Dog)
WHERE w1.rating >= $minimo AND NOT (base)-[:CONFLICTED_WITH]-(a)

MATCH (base)-[:JOINED]->(w2:Walk)<-[:JOINED]-(b:Dog)
WHERE w2.rating >= $minimo AND NOT (base)-[:CONFLICTED_WITH]-(b)
  AND elementId(a) < elementId(b)          // evita contar el mismo par dos veces

  // el tercer lado del triangulo: A y B tambien tienen que llevarse entre ellos
  AND NOT (a)-[:CONFLICTED_WITH]-(b)
  AND EXISTS { (a)-[:JOINED]->(w3:Walk)<-[:JOINED]-(b) WHERE w3.rating >= $minimo }

// DISTINCT es imprescindible: un mismo par de perros puede haber coincidido en
// varios paseos, y sin el sale una fila por cada combinacion de paseos.
RETURN DISTINCT
       base.name AS base,
       a.name    AS companero1,
       b.name    AS companero2,
       [base.sizeCategory, a.sizeCategory, b.sizeCategory] AS tamanos,
       [base.energyLevel, a.energyLevel, b.energyLevel]    AS energias
ORDER BY companero1, companero2
LIMIT $limite
"""

Q_GRUPO_DESCARTADOS = """
// El contrapunto para la demo: con quien NO puede salir, y por que.
MATCH (base:Dog {id: $perro})-[c:CONFLICTED_WITH]-(otro:Dog)
RETURN otro.name AS perro, c.reason AS motivo, toString(c.date) AS fecha
"""


def armar_grupo(perro: str, minimo: int = 4, limite: int = 10) -> list[dict]:
    """Tercias donde las tres parejas son compatibles entre si."""
    with sesion() as s:
        return [r.data() for r in s.run(Q_GRUPO, perro=perro, minimo=minimo, limite=limite)]


def descartados(perro: str) -> list[dict]:
    """Perros con los que este no puede salir, con el motivo registrado."""
    with sesion() as s:
        return [r.data() for r in s.run(Q_GRUPO_DESCARTADOS, perro=perro)]


# ═════════════════════════════════════════════════════════════════════════════
# 3. Cadena de confianza: el camino mas corto entre un dueno y un paseador
# ═════════════════════════════════════════════════════════════════════════════
# shortestPath() devuelve el camino entero como un dato, no solo los extremos.
# Ese camino ES la explicacion de la recomendacion: "Ana pasea al perro de
# Carlos, que vive en tu colonia".
#
# En un modelo relacional no existe un tipo de dato "camino": habria que
# reconstruir la justificacion en el codigo de la aplicacion.

# Los tipos de relacion se restringen a proposito. Sin esa lista, shortestPath
# encuentra atajos sin sentido como "los dos paseadores tienen la habilidad de
# primeros auxilios", que es un camino valido en el grafo pero no es confianza.
# Un camino solo explica si cada salto significa algo para el usuario.
Q_CAMINO = """
MATCH (o:Owner {id: $dueno}), (w:Walker {id: $paseador})
MATCH ruta = shortestPath(
    (o)-[:OWNS|JOINED|PERFORMED|RATED|LIVES_IN|SERVES|REFERRED*..$saltos]-(w)
)
RETURN [n IN nodes(ruta) | coalesce(n.name, n.id)] AS nodos,
       [r IN relationships(ruta) | type(r)]        AS relaciones,
       length(ruta)                                 AS saltos
"""


def cadena_de_confianza(dueno: str, paseador: str, saltos: int = 6) -> dict | None:
    """El camino mas corto entre un dueno y un paseador, como explicacion."""
    # El limite de saltos no admite parametro en el patron, asi que se
    # interpola; es un entero controlado por el codigo, nunca entrada del usuario.
    consulta = Q_CAMINO.replace("$saltos", str(int(saltos)))
    with sesion() as s:
        fila = s.run(consulta, dueno=dueno, paseador=paseador).single()
        return fila.data() if fila else None


Q_PAR_PARA_EXPLICAR = """
// Un dueno cuyo perro fue paseado por alguien a quien el dueno NO ha calificado.
// Es el caso que da sentido a la consulta: "no conozco a esta persona, por que
// deberia confiar en ella".
MATCH (o:Owner)-[:OWNS]->(:Dog)-[:JOINED]->(:Walk)<-[:PERFORMED]-(w:Walker)
WHERE NOT (o)-[:RATED]->(w)
RETURN o.id AS dueno, o.name AS nombreDueno,
       w.id AS paseador, w.name AS nombrePaseador
LIMIT 1
"""


def par_para_explicar() -> dict | None:
    """Encuentra un dueno y un paseador sin trato directo, para la consulta 3."""
    with sesion() as s:
        fila = s.run(Q_PAR_PARA_EXPLICAR).single()
        return fila.data() if fila else None


def explicar_camino(camino: dict) -> str:
    """Convierte el camino en una frase legible para la demo."""
    if not camino:
        return "No hay conexion entre ellos."
    partes = []
    for i, nodo in enumerate(camino["nodos"]):
        partes.append(nodo)
        if i < len(camino["relaciones"]):
            partes.append(f" --[{camino['relaciones'][i]}]--> ")
    return "".join(partes)


# ═════════════════════════════════════════════════════════════════════════════
# 4. Paseadores acreditados para un perro dificil
# ═════════════════════════════════════════════════════════════════════════════
# Une dos vocabularios distintos: los rasgos describen al perro, las habilidades
# describen al paseador. La relacion (:Skill)-[:QUALIFIES_FOR]->(:Trait) traduce
# entre ambos DENTRO del grafo, en vez de dejar esa correspondencia escondida en
# el codigo de la aplicacion.
#
# Ademas filtra por zona: de nada sirve el paseador perfecto que no cubre la
# colonia del dueno.

# La zona NO se usa como filtro duro sino como criterio de orden. Un filtro
# dejaba fuera a paseadores acreditados solo por no cubrir la colonia, y con
# pocos datos devolvia una sola fila. Ordenar por cubreZona pone primero a los
# de la zona sin esconder al resto, que es lo que un usuario querria ver.
Q_ACREDITADOS = """
MATCH (d:Dog {id: $perro})-[:HAS_TRAIT]->(t:Trait)
MATCH (t)<-[:QUALIFIES_FOR]-(:Skill)<-[:HAS_SKILL]-(w:Walker)
MATCH (d)<-[:OWNS]-(:Owner)-[:LIVES_IN]->(z:Zone)
WITH w, z, collect(DISTINCT t.name) AS rasgos
RETURN w.name             AS paseador,
       rasgos             AS rasgosQueCubre,
       size(rasgos)       AS cuantosCubre,
       EXISTS { (w)-[:SERVES]->(z) } AS cubreZona,
       z.name             AS zonaDelPerro,
       w.experienceMonths AS mesesExperiencia,
       w.strengthLevel    AS fuerza,
       w.ratingAvg        AS calificacion
ORDER BY cubreZona DESC, cuantosCubre DESC, calificacion DESC
LIMIT $limite
"""


def acreditados_para(perro: str, limite: int = 5) -> list[dict]:
    """Paseadores de la zona del perro con habilidades para sus rasgos."""
    with sesion() as s:
        return [r.data() for r in s.run(Q_ACREDITADOS, perro=perro, limite=limite)]


# ═════════════════════════════════════════════════════════════════════════════
# 5. Combinaciones de rasgos que terminan en paseos mal calificados
# ═════════════════════════════════════════════════════════════════════════════
# La unica consulta que no responde sobre un individuo sino sobre el sistema
# entero. Es la que convierte el historial en una regla de negocio:
# "no juntes un perro dominante con uno ansioso".
#
# El filtro total >= $minimoCasos evita conclusiones sacadas de dos paseos.

# Un porcentaje suelto no dice nada: si el 55% de TODOS los paseos grupales sale
# mal, una combinacion al 58% es ruido. Por eso se calcula primero la media
# global y se reporta el "lift": cuantas veces peor que el promedio es esta
# combinacion. lift = 1.0 significa "igual que cualquier otro paseo".
Q_COMBINACIONES = """
MATCH (base:Walk {type: 'grupal'})
WITH avg(CASE WHEN base.rating <= 3 THEN 1.0 ELSE 0.0 END) AS media

MATCH (k:Walk {type: 'grupal'})<-[:JOINED]-(a:Dog)-[:HAS_TRAIT]->(r1:Trait)
MATCH (k)<-[:JOINED]-(b:Dog)-[:HAS_TRAIT]->(r2:Trait)
WHERE elementId(a) < elementId(b) AND r1.name < r2.name
WITH media, r1.name AS rasgoA, r2.name AS rasgoB,
     sum(CASE WHEN k.rating <= 3 THEN 1 ELSE 0 END) AS malos,
     count(*)                                       AS total
WHERE total >= $minimoCasos
RETURN rasgoA, rasgoB, malos, total,
       round(100.0 * malos / total, 1)        AS porcentajeMalos,
       round(100.0 * media, 1)                AS promedioGlobal,
       round((1.0 * malos / total) / media, 2) AS lift
ORDER BY lift DESC, total DESC
LIMIT $limite
"""


def combinaciones_problematicas(minimo_casos: int = 8, limite: int = 10) -> list[dict]:
    """Pares de rasgos con mayor proporcion de paseos mal calificados."""
    with sesion() as s:
        return [
            r.data()
            for r in s.run(Q_COMBINACIONES, minimoCasos=minimo_casos, limite=limite)
        ]
