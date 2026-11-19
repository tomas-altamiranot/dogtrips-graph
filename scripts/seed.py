"""Genera el grafo de DogTrips con datos sinteticos de Merida.

Uso:  uv run python scripts/seed.py

Todos los datos son inventados. Las colonias son reales para que la demo sea
verosimil, pero no hay una sola persona, perro ni paseador real.

La semilla del generador es fija, asi que el grafo sale identico cada vez. Eso
importa para la demo: las consultas devuelven siempre los mismos resultados y
se pueden ensayar.
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

# El paquete core vive en backend/, que no es un paquete instalado.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from core.conexion import cerrar, sesion, verificar_conexion  # noqa: E402

SEMILLA = 42
random.seed(SEMILLA)

# ─────────────────────────────────────────────────────────────────────────────
# Catalogos
# ─────────────────────────────────────────────────────────────────────────────

ZONAS = [
    "Centro", "Garcia Gineres", "Montejo", "Altabrisa",
    "Francisco de Montejo", "Las Americas", "Chuburna", "Itzimna",
]

RAZAS = [
    "Labrador", "Pastor Aleman", "Schnauzer", "Chihuahua", "Pug", "Beagle",
    "Golden Retriever", "Criollo", "French Poodle", "Bulldog Frances",
    "Xoloitzcuintle", "Border Collie",
]

# (nombre, categoria). Las categorias agrupan los rasgos para las consultas.
RASGOS = [
    ("Sociable", "social"), ("Reservado", "social"), ("Jugueton", "social"),
    ("Dominante", "social"),
    ("Tranquilo", "temperamento"), ("Ansioso", "temperamento"),
    ("Reactivo", "temperamento"), ("Timido", "temperamento"),
    ("Jala la correa", "manejo"), ("Obediente", "manejo"),
    ("Fuerte", "manejo"), ("Escapista", "manejo"),
]

# Habilidad acreditada del paseador -> rasgo del perro que lo habilita a manejar.
# Esta tabla es la que se vuelve (:Skill)-[:QUALIFIES_FOR]->(:Trait) en el grafo,
# en vez de quedarse escondida en el codigo de la aplicacion.
HABILIDADES = {
    "Manejo de perros grandes": ["Fuerte"],
    "Manejo de reactivos": ["Reactivo", "Dominante"],
    "Adiestramiento basico": ["Jala la correa", "Escapista"],
    "Manejo de grupos": ["Dominante", "Sociable"],
    "Primeros auxilios": [],
}

NOMBRES_PERRO = [
    "Max", "Nina", "Toby", "Luna", "Rocco", "Zeus", "Kira", "Lola", "Simba",
    "Coco", "Canela", "Bruno", "Dante", "Mia", "Thor", "Maya", "Rex", "Frida",
    "Pancho", "Chica", "Bobby", "Duke", "Sasha", "Chispa", "Nala", "Balto",
    "Lucky", "Manchas", "Olivia", "Benito", "Rita", "Tomas", "Kala", "Milo",
    "Dalia", "Gordo", "Pepa", "Ruco", "Katy", "Chale", "Mota", "Pelusa",
    "Tequila", "Mezcal", "Chaac", "Itzel", "Kukul", "Sac", "Bacab", "Xuxa",
    "Morita", "Tuza", "Ceiba", "Pixan", "Yaax",
]

NOMBRES_PERSONA = [
    "Ana Cach", "Carlos Pech", "Luis Canul", "Maria Uc", "Jorge Dzul",
    "Paola Chan", "Diego May", "Sofia Ek", "Ricardo Poot", "Gabriela Tun",
    "Miguel Caamal", "Laura Balam", "Andres Cahun", "Fernanda Noh",
    "Roberto Ucan", "Valeria Mex", "Hector Cime", "Daniela Ko",
    "Alejandro Pat", "Renata Chi", "Pablo Yam", "Lucia Batun", "Mario Couoh",
    "Camila Hau", "Emilio Cen", "Regina Moo", "Oscar Tzuc", "Ximena Uicab",
    "Raul Kantun", "Elena Chable", "Guillermo Puc", "Natalia Ciau",
    "Felipe Canche", "Adriana Nahuat", "Sergio Itza", "Monica Keb",
    "Arturo Kumul", "Patricia Tec", "Ivan Zapata", "Rosa Chale",
]

NOMBRES_PASEADOR = [
    "Ana Sosa", "Beto Marin", "Cecilia Paredes", "David Loria", "Elena Rejon",
    "Fabian Correa", "Gabriela Sansores", "Hugo Peniche", "Irene Castillo",
    "Javier Ancona", "Karla Mendoza", "Leonardo Vega", "Mariana Rosado",
    "Nestor Villanueva", "Olivia Burgos",
]

MOTIVOS_CONFLICTO = [
    "Pelea por juguete", "Gruno a otro perro", "Jaloneo constante",
    "Marcaje territorial", "Intento de monta",
]

# Combinaciones de rasgos que hacen dificil un paseo grupal.
#
# Los datos sinteticos las incorporan A PROPOSITO: si las calificaciones fueran
# aleatorias, la consulta 5 devolveria ruido con apariencia de hallazgo. Al
# sembrar una correlacion conocida se puede VERIFICAR que la consulta la
# detecta, que es la unica forma de saber que funciona.
#
# En la defensa esto se dice tal cual: los datos modelan la regla de negocio que
# la consulta debe descubrir.
COMBINACIONES_DIFICILES = [
    ("Reactivo", "Dominante"),
    ("Ansioso", "Dominante"),
    ("Reactivo", "Escapista"),
]


def calificar_paseo(ids: list[str], rasgos: dict[str, set[str]]) -> int:
    """Calificacion de un paseo grupal segun los rasgos de quienes van.

    Cuenta cuantas combinaciones dificiles aparecen entre los perros del paseo y
    baja la calificacion en consecuencia, con ruido para que no sea determinista.
    """
    presentes: set[str] = set()
    for d in ids:
        presentes |= rasgos.get(d, set())

    choques = sum(1 for a, b in COMBINACIONES_DIFICILES if a in presentes and b in presentes)

    if choques == 0:
        return random.choice([5, 5, 5, 5, 4, 4])
    if choques == 1:
        return random.choice([5, 4, 4, 4, 3])
    return random.choice([4, 3, 3, 2, 2])

HOY = date(2026, 11, 14)


def iso(dias_atras: int) -> str:
    return (HOY - timedelta(days=dias_atras)).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Generacion en memoria
# ─────────────────────────────────────────────────────────────────────────────

def generar():
    """Arma todas las listas antes de tocar la base.

    Separar la generacion de la escritura permite revisar los datos sin gastar
    una conexion, y hace que la escritura sea un volcado simple.
    """
    duenos, perros, paseadores = [], [], []

    # --- Duenos, repartidos entre las ocho colonias ---
    for i, nombre in enumerate(NOMBRES_PERSONA):
        duenos.append({
            "id": f"own-{i + 1:03d}",
            "name": nombre,
            "phone": f"999{random.randint(1000000, 9999999)}",
            "zona": ZONAS[i % len(ZONAS)],
        })

    # --- Perros: cada dueno tiene uno, y algunos un segundo ---
    nombres = NOMBRES_PERRO.copy()
    random.shuffle(nombres)
    for i in range(len(nombres)):
        dueno = duenos[i % len(duenos)]
        tam, peso = random.choice([
            ("pequeno", random.randint(4, 11)),
            ("mediano", random.randint(12, 24)),
            ("grande", random.randint(25, 45)),
        ])
        perros.append({
            "id": f"dog-{i + 1:03d}",
            "name": nombres[i],
            "breed": random.choice(RAZAS),
            "sizeCategory": tam,
            "weightKg": peso,
            "ageMonths": random.randint(8, 132),
            "energyLevel": random.choice(["baja", "media", "alta"]),
            "ownerId": dueno["id"],
            "zona": dueno["zona"],
        })

    # --- Paseadores: cada uno cubre una o dos colonias ---
    for i, nombre in enumerate(NOMBRES_PASEADOR):
        propias = random.sample(ZONAS, random.choice([1, 1, 2]))
        paseadores.append({
            "id": f"wlk-{i + 1:03d}",
            "name": nombre,
            "experienceMonths": random.randint(2, 72),
            "strengthLevel": random.choice(["media", "media", "alta"]),
            "verified": random.random() < 0.75,
            "ratingAvg": None,  # se calcula al final, con las calificaciones reales
            "zonas": propias,
            "skills": random.sample(list(HABILIDADES), random.randint(1, 3)),
        })

    # --- Rasgos por perro ---
    # Se guardan dos veces: como lista de filas para escribir en el grafo, y como
    # diccionario para poder consultarlos al calificar los paseos.
    rasgos_perro = []
    rasgos_por_perro: dict[str, set[str]] = {}
    for p in perros:
        sociales = [r for r, c in RASGOS if c == "social"]
        temperamentos = [r for r, c in RASGOS if c == "temperamento"]
        manejos = [r for r, c in RASGOS if c == "manejo"]
        elegidos = {random.choice(sociales), random.choice(temperamentos)}
        if random.random() < 0.6:
            elegidos.add(random.choice(manejos))
        rasgos_por_perro[p["id"]] = elegidos
        for r in elegidos:
            rasgos_perro.append({"dogId": p["id"], "trait": r})

    # ═════════════════════════════════════════════════════════════════════════
    # CAMADAS — la pieza que sostiene el proyecto
    # ═════════════════════════════════════════════════════════════════════════
    # La compatibilidad no se guarda: se infiere de que dos perros hayan
    # coincidido en un paseo bien calificado. Si los paseos grupales juntaran
    # perros al azar entre los 55, ningun par se repetiria y la consulta del
    # clique saldria vacia.
    #
    # La realidad no es aleatoria: un paseador cubre una colonia y los mismos
    # cuatro o seis perros salen juntos una y otra vez. Eso es una camada, y es
    # de donde se sortean los paseos grupales.
    camadas = []
    for zona in ZONAS:
        de_la_zona = [p for p in perros if p["zona"] == zona]
        random.shuffle(de_la_zona)
        for k in range(2):  # dos camadas por colonia
            trozo = de_la_zona[k * 5:(k + 1) * 5]
            if len(trozo) >= 4:
                camadas.append({"zona": zona, "perros": [p["id"] for p in trozo]})

    # --- Paseos ---
    paseos, participaciones, calificaciones = [], [], []
    n = 0

    # Grupales: se sortean DE UNA CAMADA, nunca del total.
    for camada in camadas:
        candidatos = [w for w in paseadores if camada["zona"] in w["zonas"]]
        if not candidatos:
            candidatos = paseadores
        paseador = random.choice(candidatos)
        for _ in range(random.randint(8, 12)):
            n += 1
            pid = f"wal-{n:04d}"

            # Primero se elige QUIENES van, porque la calificacion depende de sus
            # rasgos. Al reves seria calificar un paseo antes de saber quien fue.
            k = random.randint(3, len(camada["perros"]))
            asistentes = random.sample(camada["perros"], k)

            paseos.append({
                "id": pid,
                "date": iso(random.randint(1, 120)),
                "durationMin": random.choice([30, 45, 60]),
                "distanceKm": round(random.uniform(1.5, 5.0), 1),
                "type": "grupal",
                "rating": calificar_paseo(asistentes, rasgos_por_perro),
                "walkerId": paseador["id"],
            })
            for dog_id in asistentes:
                participaciones.append({"dogId": dog_id, "walkId": pid})

    # Individuales: aqui si da igual quien, porque no generan compatibilidad.
    for _ in range(70):
        n += 1
        pid = f"wal-{n:04d}"
        perro = random.choice(perros)
        candidatos = [w for w in paseadores if perro["zona"] in w["zonas"]] or paseadores
        paseador = random.choice(candidatos)
        paseos.append({
            "id": pid,
            "date": iso(random.randint(1, 120)),
            "durationMin": random.choice([20, 30, 45]),
            "distanceKm": round(random.uniform(0.8, 3.5), 1),
            "type": "individual",
            "rating": random.choice([5, 5, 5, 4, 4, 3]),
            "walkerId": paseador["id"],
        })
        participaciones.append({"dogId": perro["id"], "walkId": pid})

    # --- Calificaciones del dueno al paseador ---
    indice_perro = {p["id"]: p for p in perros}
    vistos = set()
    for part in participaciones:
        paseo = next(w for w in paseos if w["id"] == part["walkId"])
        owner_id = indice_perro[part["dogId"]]["ownerId"]
        par = (owner_id, paseo["walkerId"])
        if par in vistos or random.random() < 0.35:
            continue
        vistos.add(par)
        calificaciones.append({
            "ownerId": owner_id,
            "walkerId": paseo["walkerId"],
            "score": paseo["rating"],
            "date": paseo["date"],
        })

    # Promedio real por paseador, para que ratingAvg no sea un numero inventado.
    # Sin calificaciones queda en None (null en Neo4j), no en 0.0: un paseador
    # nuevo no es un paseador malo, simplemente nadie lo ha calificado aun.
    for w in paseadores:
        suyas = [c["score"] for c in calificaciones if c["walkerId"] == w["id"]]
        w["ratingAvg"] = round(sum(suyas) / len(suyas), 2) if suyas else None

    # ═════════════════════════════════════════════════════════════════════════
    # CONFLICTOS — dentro de las camadas, nunca fuera
    # ═════════════════════════════════════════════════════════════════════════
    # La consulta del clique filtra con NOT (a)-[:CONFLICTED_WITH]-(b). Si los
    # incidentes cayeran entre perros que nunca se vieron, esa linea no filtraria
    # nada y seria decoracion. Poniendolos dentro de las camadas si rompen
    # cliques de verdad, y la consulta tiene que esquivarlos.
    conflictos = []
    for camada in random.sample(camadas, min(8, len(camadas))):
        a, b = random.sample(camada["perros"], 2)
        conflictos.append({
            "a": a, "b": b,
            "reason": random.choice(MOTIVOS_CONFLICTO),
            "date": iso(random.randint(1, 90)),
        })

    # --- Referidos entre duenos de la misma colonia ---
    referidos = []
    for zona in ZONAS:
        de_la_zona = [d["id"] for d in duenos if d["zona"] == zona]
        for i in range(len(de_la_zona) - 1):
            if random.random() < 0.5:
                referidos.append({"de": de_la_zona[i], "a": de_la_zona[i + 1]})

    # --- Mentorias: un paseador novato aprende de uno con experiencia ---
    mentorias = []
    veteranos = [w["id"] for w in paseadores if w["experienceMonths"] > 36]
    for w in paseadores:
        if w["experienceMonths"] < 12 and veteranos:
            mentorias.append({"novato": w["id"], "mentor": random.choice(veteranos)})

    return {
        "duenos": duenos, "perros": perros, "paseadores": paseadores,
        "rasgos_perro": rasgos_perro, "paseos": paseos,
        "participaciones": participaciones, "calificaciones": calificaciones,
        "conflictos": conflictos, "referidos": referidos, "mentorias": mentorias,
        "camadas": camadas,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Escritura en Neo4j
# ─────────────────────────────────────────────────────────────────────────────

RESTRICCIONES = [
    "CREATE CONSTRAINT owner_id IF NOT EXISTS FOR (o:Owner) REQUIRE o.id IS UNIQUE",
    "CREATE CONSTRAINT dog_id IF NOT EXISTS FOR (d:Dog) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT walker_id IF NOT EXISTS FOR (w:Walker) REQUIRE w.id IS UNIQUE",
    "CREATE CONSTRAINT walk_id IF NOT EXISTS FOR (k:Walk) REQUIRE k.id IS UNIQUE",
    "CREATE CONSTRAINT zone_name IF NOT EXISTS FOR (z:Zone) REQUIRE z.name IS UNIQUE",
    "CREATE CONSTRAINT trait_name IF NOT EXISTS FOR (t:Trait) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT skill_name IF NOT EXISTS FOR (s:Skill) REQUIRE s.name IS UNIQUE",
]


def escribir(datos: dict) -> None:
    with sesion() as s:
        print("  limpiando el grafo...")
        s.run("MATCH (n) DETACH DELETE n")

        print("  creando restricciones de unicidad...")
        for q in RESTRICCIONES:
            s.run(q)

        # Cada bloque usa UNWIND: se manda la lista completa en UNA consulta en
        # vez de una consulta por fila. Contra Aura Free, que esta al otro lado
        # de internet, la diferencia es de minutos a segundos.
        print("  zonas, rasgos y habilidades...")
        s.run("UNWIND $f AS n MERGE (:Zone {name: n})", f=ZONAS)
        s.run("UNWIND $f AS n MERGE (t:Trait {name: n.nombre}) SET t.category = n.cat",
              f=[{"nombre": r, "cat": c} for r, c in RASGOS])
        s.run("UNWIND $f AS n MERGE (:Skill {name: n})", f=list(HABILIDADES))
        s.run(
            """
            UNWIND $f AS n
            MATCH (s:Skill {name: n.skill}), (t:Trait {name: n.trait})
            MERGE (s)-[:QUALIFIES_FOR]->(t)
            """,
            f=[{"skill": s_, "trait": t} for s_, ts in HABILIDADES.items() for t in ts],
        )

        print("  duenos y perros...")
        s.run(
            """
            UNWIND $f AS n
            CREATE (o:Owner {id: n.id, name: n.name, phone: n.phone})
            WITH o, n
            MATCH (z:Zone {name: n.zona})
            CREATE (o)-[:LIVES_IN]->(z)
            """,
            f=datos["duenos"],
        )
        s.run(
            """
            UNWIND $f AS n
            CREATE (d:Dog {id: n.id, name: n.name, breed: n.breed,
                           sizeCategory: n.sizeCategory, weightKg: n.weightKg,
                           ageMonths: n.ageMonths, energyLevel: n.energyLevel})
            WITH d, n
            MATCH (o:Owner {id: n.ownerId})
            CREATE (o)-[:OWNS]->(d)
            """,
            f=datos["perros"],
        )
        s.run(
            """
            UNWIND $f AS n
            MATCH (d:Dog {id: n.dogId}), (t:Trait {name: n.trait})
            CREATE (d)-[:HAS_TRAIT]->(t)
            """,
            f=datos["rasgos_perro"],
        )

        print("  paseadores...")
        s.run(
            """
            UNWIND $f AS n
            CREATE (w:Walker {id: n.id, name: n.name,
                              experienceMonths: n.experienceMonths,
                              strengthLevel: n.strengthLevel,
                              verified: n.verified, ratingAvg: n.ratingAvg})
            WITH w, n
            UNWIND n.zonas AS zona
            MATCH (z:Zone {name: zona})
            CREATE (w)-[:SERVES]->(z)
            """,
            f=datos["paseadores"],
        )
        s.run(
            """
            UNWIND $f AS n
            UNWIND n.skills AS hab
            MATCH (w:Walker {id: n.id}), (s:Skill {name: hab})
            CREATE (w)-[:HAS_SKILL]->(s)
            """,
            f=datos["paseadores"],
        )

        print("  paseos y participaciones...")
        s.run(
            """
            UNWIND $f AS n
            CREATE (k:Walk {id: n.id, date: date(n.date), durationMin: n.durationMin,
                            distanceKm: n.distanceKm, type: n.type, rating: n.rating})
            WITH k, n
            MATCH (w:Walker {id: n.walkerId})
            CREATE (w)-[:PERFORMED]->(k)
            """,
            f=datos["paseos"],
        )
        s.run(
            """
            UNWIND $f AS n
            MATCH (d:Dog {id: n.dogId}), (k:Walk {id: n.walkId})
            CREATE (d)-[:JOINED]->(k)
            """,
            f=datos["participaciones"],
        )

        print("  calificaciones, conflictos, referidos y mentorias...")
        s.run(
            """
            UNWIND $f AS n
            MATCH (o:Owner {id: n.ownerId}), (w:Walker {id: n.walkerId})
            CREATE (o)-[:RATED {score: n.score, date: date(n.date)}]->(w)
            """,
            f=datos["calificaciones"],
        )
        s.run(
            """
            UNWIND $f AS n
            MATCH (a:Dog {id: n.a}), (b:Dog {id: n.b})
            CREATE (a)-[:CONFLICTED_WITH {reason: n.reason, date: date(n.date)}]->(b)
            """,
            f=datos["conflictos"],
        )
        s.run(
            """
            UNWIND $f AS n
            MATCH (a:Owner {id: n.de}), (b:Owner {id: n.a})
            CREATE (b)-[:REFERRED]->(a)
            """,
            f=datos["referidos"],
        )
        s.run(
            """
            UNWIND $f AS n
            MATCH (a:Walker {id: n.novato}), (b:Walker {id: n.mentor})
            CREATE (a)-[:MENTORED_BY]->(b)
            """,
            f=datos["mentorias"],
        )


def verificar() -> None:
    """Confirma que el grafo quedo cargado y que la consulta estrella encuentra algo.

    Esta ultima parte es la importante: un seed que carga datos pero deja la
    consulta del clique vacia es un seed roto, aunque los conteos se vean bien.
    """
    with sesion() as s:
        print("\n  conteos")
        for etiqueta in ["Owner", "Dog", "Walker", "Walk", "Zone", "Trait", "Skill"]:
            total = s.run(f"MATCH (n:{etiqueta}) RETURN count(n) AS t").single()["t"]
            print(f"    {etiqueta:<8} {total:>5}")
        rels = s.run("MATCH ()-[r]->() RETURN count(r) AS t").single()["t"]
        print(f"    {'relaciones':<8} {rels:>5}")

        print("\n  prueba de la consulta estrella")
        fila = s.run(
            """
            MATCH (a:Dog)-[:JOINED]->(k:Walk)<-[:JOINED]-(b:Dog)
            WHERE k.rating >= 4 AND elementId(a) < elementId(b)
              AND NOT (a)-[:CONFLICTED_WITH]-(b)
            RETURN count(DISTINCT [a.id, b.id]) AS pares
            """
        ).single()
        print(f"    pares compatibles       : {fila['pares']}")

        trio = s.run(
            """
            MATCH (a:Dog)-[:JOINED]->(:Walk)<-[:JOINED]-(b:Dog),
                  (b)-[:JOINED]->(:Walk)<-[:JOINED]-(c:Dog),
                  (a)-[:JOINED]->(:Walk)<-[:JOINED]-(c)
            WHERE elementId(a) < elementId(b) AND elementId(b) < elementId(c)
              AND NOT (a)-[:CONFLICTED_WITH]-(b)
              AND NOT (b)-[:CONFLICTED_WITH]-(c)
              AND NOT (a)-[:CONFLICTED_WITH]-(c)
            RETURN count(DISTINCT [a.id, b.id, c.id]) AS trios
            """
        ).single()
        print(f"    grupos de tres validos  : {trio['trios']}")

        conflictos = s.run(
            "MATCH ()-[r:CONFLICTED_WITH]->() RETURN count(r) AS t"
        ).single()["t"]
        print(f"    incidentes registrados  : {conflictos}")

        if trio["trios"] == 0:
            print("\n  AVISO: no hay grupos de tres. La consulta 2 saldria vacia.")
        else:
            print("\n  Listo: hay material para las cinco consultas.")


def main() -> None:
    print(f"Conectando...  {verificar_conexion()}")
    datos = generar()
    print(f"\nGenerado en memoria: {len(datos['perros'])} perros, "
          f"{len(datos['paseos'])} paseos, {len(datos['camadas'])} camadas")
    print("\nEscribiendo en AuraDB")
    escribir(datos)
    verificar()
    cerrar()


if __name__ == "__main__":
    main()
