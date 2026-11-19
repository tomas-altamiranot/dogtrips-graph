"""Las cinco consultas especializadas de DogTrips.

Cada funcion recibe parametros y devuelve listas de diccionarios. Ninguna
imprime nada: quien decide como mostrar los resultados es la capa de arriba.

El Cypher vive en constantes al inicio de cada seccion para poder leerlo de
corrido, sin el ruido de Python alrededor.
"""

from __future__ import annotations

from .conexion import leer

# ═════════════════════════════════════════════════════════════════════════════
# 1. Recomendacion de paseador via vecinos y perros parecidos
# ═════════════════════════════════════════════════════════════════════════════
# Recorrido:
#   mi perro -> mi dueno -> [red de vecinos, 1 a 3 saltos] -> sus perros
#            -> sus paseos bien calificados -> paseador
#
# La "red de vecinos" se recorre con PROFUNDIDAD VARIABLE: *1..3 sobre
# LIVES_IN y REFERRED. Con un salto llega a quien me refirio; con dos, a quien
# vive en mi colonia o a quien refirio a mi referente; con tres, a la colonia de
# mi referente. En SQL cada uno de esos casos seria un JOIN distinto escrito a
# mano; aqui es un solo patron y la profundidad es un numero.
#
# Despues se pondera: un paseador que ya paseo bien a perros de mis vecinos
# QUE ADEMAS se parecen al mio (comparten un rasgo) sube en el ranking. Un
# promedio general ordena a los paseadores en abstracto; este los ordena por
# desempeno con perros como el mio, de gente que conozco.

Q_RECOMENDAR = """
MATCH (p:Dog {id: $perro})<-[:OWNS]-(yo:Owner)
MATCH (yo)-[:LIVES_IN|REFERRED*1..$saltos]-(vecino:Owner)
WHERE vecino <> yo
WITH DISTINCT p, vecino
MATCH (vecino)-[:OWNS]->(suyo:Dog)-[:JOINED]->(k:Walk)<-[:PERFORMED]-(w:Walker)
WHERE k.rating >= $minimo AND suyo <> p
WITH w, suyo, k,
     EXISTS { (p)-[:HAS_TRAIT]->(:Trait)<-[:HAS_TRAIT]-(suyo) } AS seParece
RETURN w.id                                          AS id,
       w.name                                        AS paseador,
       count(DISTINCT suyo)                          AS perrosDeVecinos,
       count(DISTINCT CASE WHEN seParece THEN suyo END) AS parecidosAlMio,
       round(avg(k.rating), 2)                       AS calificacionConVecinos,
       w.ratingAvg                                   AS promedioGeneral,
       w.verified                                    AS verificado
ORDER BY parecidosAlMio DESC, perrosDeVecinos DESC, calificacionConVecinos DESC
LIMIT $limite
"""


def recomendar_paseadores(
    perro: str, saltos: int = 3, minimo: int = 4, limite: int = 5
) -> list[dict]:
    """Paseadores que ya pasearon bien a perros de la red de vecinos del dueno."""
    # Neo4j no acepta parametros dentro de *1..N, asi que el limite se interpola.
    # Es un entero controlado por el codigo (int() lo garantiza), nunca texto
    # del usuario, por lo que no abre la puerta a inyeccion de Cypher.
    consulta = Q_RECOMENDAR.replace("$saltos", str(int(saltos)))
    return leer(consulta, perro=perro, minimo=minimo, limite=limite)


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
    return leer(Q_GRUPO, perro=perro, minimo=minimo, limite=limite)


def descartados(perro: str) -> list[dict]:
    """Perros con los que este no puede salir, con el motivo registrado."""
    return leer(Q_GRUPO_DESCARTADOS, perro=perro)


# ═════════════════════════════════════════════════════════════════════════════
# 3. Cadena de confianza: el camino mas corto entre un dueno y un paseador
# ═════════════════════════════════════════════════════════════════════════════
# shortestPath() devuelve el camino entero como un dato, no solo los extremos.
# Ese camino ES la explicacion de la recomendacion: "Ana pasea al perro de
# Carlos, que vive en tu colonia".
#
# En un modelo relacional no existe un tipo de dato "camino": habria que
# reconstruir la justificacion en el codigo de la aplicacion.

# Los tipos de relacion se restringen a proposito: solo saltos ENTRE PERSONAS y
# lo que hicieron (refirio, califico, es dueno de, paseo). Se dejan fuera
# LIVES_IN y SERVES porque producen atajos que no son confianza: "vives en
# Montejo y el trabaja en Montejo" es un camino valido en el grafo, pero no
# explica por que confiar en alguien. Lo mismo HAS_SKILL: "los dos tienen
# primeros auxilios" no es una recomendacion. Un camino solo explica si cada
# salto significa algo para el usuario.
Q_CAMINO = """
MATCH (o:Owner {id: $dueno}), (w:Walker {id: $paseador})
MATCH ruta = shortestPath(
    (o)-[:OWNS|JOINED|PERFORMED|RATED|REFERRED*..$saltos]-(w)
)
RETURN [n IN nodes(ruta) | coalesce(n.name, n.id)] AS nodos,
       [r IN relationships(ruta) |
            CASE WHEN type(r) = 'RATED'
                 THEN 'RATED ' + toString(r.score) + '/5'
                 ELSE type(r) END]                  AS relaciones,
       length(ruta)                                 AS saltos
"""


def cadena_de_confianza(dueno: str, paseador: str, saltos: int = 6) -> dict | None:
    """El camino mas corto entre un dueno y un paseador, como explicacion."""
    # El limite de saltos no admite parametro en el patron, asi que se
    # interpola; es un entero controlado por el codigo, nunca entrada del usuario.
    consulta = Q_CAMINO.replace("$saltos", str(int(saltos)))
    filas = leer(consulta, dueno=dueno, paseador=paseador)
    return filas[0] if filas else None


Q_PAR_PARA_EXPLICAR = """
// Un dueno que NUNCA ha tratado con el paseador (no lo califico y ninguno de
// sus perros salio con el), pero alguien de su red de referidos si lo califico
// bien. Es el caso que da sentido a la consulta: "no conozco a esta persona,
// por que deberia confiar en ella" -> "porque tu vecino, que te refirio, le
// puso 5".
MATCH (o:Owner)-[:REFERRED]-(:Owner)-[r:RATED]->(w:Walker)
WHERE r.score >= 4
  AND NOT (o)-[:RATED]->(w)
  AND NOT EXISTS { (o)-[:OWNS]->(:Dog)-[:JOINED]->(:Walk)<-[:PERFORMED]-(w) }
RETURN o.id AS dueno, o.name AS nombreDueno,
       w.id AS paseador, w.name AS nombrePaseador
ORDER BY o.id, w.id
LIMIT 1
"""


def par_para_explicar() -> dict | None:
    """Encuentra un dueno y un paseador sin trato directo, para la consulta 3."""
    filas = leer(Q_PAR_PARA_EXPLICAR)
    return filas[0] if filas else None


def explicar_camino(camino: dict) -> str:
    """Convierte el camino en una frase legible para la demo."""
    if not camino:
        return "No hay conexion entre ellos."
    # El camino se recorre sin direccion, asi que se dibuja con guiones y sin
    # flecha: "Ana --[REFERRED]-- Luis" no dice quien refirio a quien.
    partes = []
    for i, nodo in enumerate(camino["nodos"]):
        partes.append(nodo)
        if i < len(camino["relaciones"]):
            partes.append(f" --[{camino['relaciones'][i]}]-- ")
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
// Un paseador sin calificaciones tiene ratingAvg nulo, no 0: "nadie lo ha
// calificado" y "lo calificaron con 0" son cosas distintas. Para ordenar se usa
// coalesce(..., -1), que lo manda al final sin inventarle una nota.
RETURN w.name             AS paseador,
       rasgos             AS rasgosQueCubre,
       size(rasgos)       AS cuantosCubre,
       EXISTS { (w)-[:SERVES]->(z) } AS cubreZona,
       z.name             AS zonaDelPerro,
       w.experienceMonths AS mesesExperiencia,
       w.strengthLevel    AS fuerza,
       w.ratingAvg        AS calificacion,
       COUNT { (:Owner)-[:RATED]->(w) } AS numCalificaciones
ORDER BY cubreZona DESC, cuantosCubre DESC, coalesce(w.ratingAvg, -1) DESC
LIMIT $limite
"""


def acreditados_para(perro: str, limite: int = 5) -> list[dict]:
    """Paseadores de la zona del perro con habilidades para sus rasgos."""
    return leer(Q_ACREDITADOS, perro=perro, limite=limite)


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
#
# La unidad que se cuenta es el PASEO. Un mismo paseo puede tener la
# combinacion Ansioso+Reactivo por varios pares de perros a la vez; contar filas
# lo contaria varias veces e inflaria el total. Por eso, antes de agregar, se
# reduce a una fila por (paseo, combinacion) con WITH DISTINCT. Asi "8/10"
# significa literalmente "8 de 10 paseos grupales".
#
# r1.name <= r2.name ordena cada combinacion una sola vez (A+B, nunca B+A) y
# deja pasar la combinacion de un rasgo consigo mismo entre DOS perros
# distintos, por ejemplo dos perros reactivos en el mismo paseo.
Q_COMBINACIONES = """
MATCH (base:Walk {type: 'grupal'})
WITH avg(CASE WHEN base.rating <= 3 THEN 1.0 ELSE 0.0 END) AS media

MATCH (k:Walk {type: 'grupal'})<-[:JOINED]-(a:Dog)-[:HAS_TRAIT]->(r1:Trait)
MATCH (k)<-[:JOINED]-(b:Dog)-[:HAS_TRAIT]->(r2:Trait)
WHERE a <> b AND r1.name <= r2.name
WITH DISTINCT media, k, r1.name AS rasgoA, r2.name AS rasgoB
WITH media, rasgoA, rasgoB,
     sum(CASE WHEN k.rating <= 3 THEN 1 ELSE 0 END) AS malos,
     count(k)                                       AS total
WHERE total >= $minimoCasos AND media > 0
RETURN rasgoA, rasgoB, malos, total,
       round(100.0 * malos / total, 1)        AS porcentajeMalos,
       round(100.0 * media, 1)                AS promedioGlobal,
       round((1.0 * malos / total) / media, 2) AS lift
ORDER BY lift DESC, total DESC
LIMIT $limite
"""


# minimo_casos = 15: con menos paseos, un 80% puede ser 8 de 10 por azar. Con
# 15 o mas, la combinacion que encabeza la lista es Dominante + Reactivo, que es
# justo una de las reglas sembradas en seed.py: la consulta la redescubre.
def combinaciones_problematicas(minimo_casos: int = 15, limite: int = 10) -> list[dict]:
    """Pares de rasgos con mayor proporcion de paseos mal calificados."""
    return leer(Q_COMBINACIONES, minimoCasos=minimo_casos, limite=limite)
