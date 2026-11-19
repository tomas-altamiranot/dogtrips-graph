# DogTrips Graph

Capa de grafo para **DogTrips**, una plataforma de paseo de perros: los dueños contratan
paseadores, y los perros salen solos o en grupo.

El sistema responde tres preguntas que una base relacional contesta con dificultad:

1. **¿Qué paseador le conviene a este perro?** — y **¿por qué confiar en él?**
2. **¿Qué perros pueden salir juntos en un paseo grupal?**
3. **¿Qué combinaciones terminan mal?**

**Bases de Datos Avanzadas — Universidad Anáhuac Mayab**
Proyecto individual · Neo4j AuraDB · Django REST Framework

---

## Estado

| Componente | Estado |
|---|---|
| Conexión a Neo4j AuraDB con credenciales por entorno | ✅ Operativa |
| Modelo del grafo | ✅ Cerrado |
| Script de datos sintéticos | 🚧 Siguiente |
| CRUD sobre dueños, perros y paseadores | 🚧 Pendiente |
| Las 5 consultas especializadas | 🚧 Pendiente |
| API REST con Django | 🚧 Pendiente |
| Cliente de demostración | 🚧 Pendiente |

---

## 1. El dominio

Dejar a tu perro con un desconocido es un acto de confianza. Una plataforma de paseos vive
o muere por dos cosas: **acertar en el emparejamiento** y **poder explicarlo**.

El sistema modela cuatro realidades del negocio: quién es el dueño y dónde vive, cómo es el
perro (tamaño, energía y sobre todo carácter), qué sabe hacer el paseador, y qué pasó en
cada paseo.

### El problema central: los paseos grupales

Un paseo grupal es más barato para el dueño y más rentable para el paseador. Pero no
cualquier grupo funciona, y **la compatibilidad no es transitiva**:

```
        Max ──✓── Nina
         │         │
         ✗         ✓        Max y Nina se llevan bien.
         │         │        Nina y Toby se llevan bien.
         └── Toby ─┘        Max y Toby NO.
```

Armar un grupo de tres no es elegir tres perros compatibles con el primero: es encontrar un
subconjunto donde **todos los pares** funcionan. Eso tiene nombre en teoría de grafos
—buscar un **clique**— y es el requisito que define este proyecto.

> **Datos sintéticos.** Todo se genera por script. No hay información de personas, perros ni
> paseadores reales. Las colonias son de Mérida, Yucatán, para que la demo sea verosímil.

---

## 2. Por qué un grafo y no SQL

### 2.1 Formar grupos es un problema de grafos, literalmente

Dos perros son compatibles si **ya coincidieron en un paseo bien calificado** y **no existe
un incidente registrado** entre ellos. En Cypher, "no hay conflicto entre A y B" se escribe
tal cual:

```cypher
WHERE NOT (a)-[:CONFLICTED_WITH]-(b)
```

En SQL eso es un `NOT EXISTS` con subconsulta **por cada par del grupo**, y el número de
pares crece con el tamaño del grupo: uno de 3 necesita 3 comprobaciones, uno de 5 necesita
10. **La consulta SQL hay que reescribirla cada vez que cambia el tamaño del grupo.** La de
Cypher no.

### 2.2 Recorridos de profundidad variable

La cadena de confianza que justifica una recomendación es un recorrido:

```
tú → tu colonia → vecinos → sus perros → paseadores que los pasearon → calificaciones
```

En SQL **cada salto es un JOIN escrito a mano** y la profundidad queda fija al escribir la
consulta. En Cypher es un parámetro:

```cypher
MATCH (yo:Owner)-[:LIVES_IN|OWNS|JOINED|PERFORMED*1..3]-(w:Walker)
```

Ese `*1..3` es la diferencia.

### 2.3 El camino es la explicación

Cuando un dueño pregunta *"¿por qué me recomiendas a esta persona?"*, la respuesta no es un
número de similitud. Es **el camino**:

```
Tú → vives en García Ginerés → Carlos también → Carlos tiene a Nina
   → a Nina la pasea Ana → Carlos calificó a Ana con 5
```

Ese camino existe como dato consultable: se obtiene con `shortestPath()` y se muestra al
usuario tal cual. En un modelo relacional habría que reconstruir la justificación por fuera,
en código de aplicación.

### 2.4 Dónde **no** conviene el grafo

Parte del valor de esta decisión está en reconocer sus límites:

| Problema | Dónde pertenece realmente |
|---|---|
| Reservas, pagos, facturación | **Relacional** — importa la integridad y la auditoría |
| Ubicación del perro en tiempo real | **Series de tiempo** — es un flujo de puntos, no una red |
| Fotos y documentos | Almacenamiento de objetos |

Este grafo resuelve **emparejamiento, confianza y análisis**. Un sistema real usaría varios
motores, y este sería uno de ellos.

---

## 3. Arquitectura

```
┌──────────────────────────────────────────────┐
│  Cliente  (demo web · app móvil Flutter)     │
└──────────────────┬───────────────────────────┘
                   │ HTTP / JSON
┌──────────────────▼───────────────────────────┐
│  backend/   Django 5 + Django REST Framework │
│             capa HTTP, SIN ORM relacional    │
│  ┌────────────────────────────────────────┐  │
│  │  core/   driver oficial de neo4j       │  │
│  │          toda la lógica y las consultas│  │
│  └────────────────────┬───────────────────┘  │
└───────────────────────┼──────────────────────┘
                        │ bolt+s  (TLS)
┌───────────────────────▼──────────────────────┐
│          Neo4j AuraDB  —  nube               │
└──────────────────────────────────────────────┘
```

### 3.1 Django corre con el ORM deshabilitado

```python
DATABASES = {}
```

No es un descuido: es la decisión de diseño más deliberada del proyecto.

**La única persistencia del sistema es Neo4j.** Django aporta exclusivamente la capa HTTP
—ruteo, serialización, manejo de errores— y no almacena nada. Dejar el ORM activo
habilitaría dos fuentes de verdad, que es precisamente el problema que este diseño evita.

### 3.2 `core/` no sabe que existe una web

El paquete `core/` es Python puro con el driver `neo4j`. **No importa Django.** Las
dependencias apuntan en una sola dirección:

```
cliente  →  api  →  core  →  neo4j
```

Así la lógica se prueba sin levantar servidores, y cambiar de interfaz no toca el núcleo.

`core/conexion.py` es el único módulo que construye un driver: es un singleton (el driver
administra su propio pool y es caro de crear) y verifica la conexión con
`verify_connectivity()`, porque `GraphDatabase.driver()` **no contacta al servidor** —solo
guarda la configuración— y un fallo de credenciales pasaría desapercibido hasta la primera
consulta.

### 3.3 Estructura

```
dogtrips-graph/
├── README.md
├── pyproject.toml          dependencias (gestionado con uv)
├── uv.lock                 versiones exactas
├── .env.example            molde de las credenciales
│
├── backend/
│   ├── config/             proyecto Django: settings, urls
│   ├── api/                app DRF: views, serializers, urls
│   └── core/               ← driver, consultas, lógica de dominio
│       └── conexion.py
│
├── scripts/
│   ├── probar_conexion.py  diagnóstico de conectividad
│   └── seed.py             generación de datos sintéticos
│
└── docs/                   documentación técnica y diagramas
```

---

## 4. Modelo del grafo

```
              ┌──────┐  LIVES_IN   ┌──────┐   SERVES   ┌────────┐
              │ Owner│────────────►│ Zone │◄───────────│ Walker │
              └──┬───┘             └──────┘            └───┬────┘
                 │                                         │
                 │ OWNS                     RATED {score}  │
                 │        ┌────────────────────────────────┘
                 ▼        ▼                                │ HAS_SKILL
              ┌─────┐                                      ▼
              │ Dog │                                  ┌───────┐
              └──┬──┘                                  │ Skill │
        HAS_TRAIT│  │ JOINED                           └───┬───┘
                 │  │                                      │ QUALIFIES_FOR
                 ▼  ▼                                      │
          ┌───────┐ ┌──────┐   PERFORMED                   │
          │ Trait │ │ Walk │◄──────────────── Walker       │
          └───▲───┘ └──────┘                               │
              └───────────────────────────────────────────-┘

      Dog ──CONFLICTED_WITH {reason}── Dog     (incidente registrado)
    Owner ──REFERRED──► Owner                  (red de referidos)
   Walker ──MENTORED_BY──► Walker              (progresión del paseador)
```

### 4.1 Nodos

| Label | Propiedades | Para qué |
|---|---|---|
| `:Owner` | `id`, `name`, `phone` | El dueño |
| `:Dog` | `id`, `name`, `breed`, `sizeCategory`, `weightKg`, `ageMonths`, `energyLevel` | El perro |
| `:Walker` | `id`, `name`, `experienceMonths`, `strengthLevel`, `verified`, `ratingAvg` | El paseador |
| `:Trait` | `name`, `category` | Rasgo del perro: sociable, reactivo, tímido |
| `:Skill` | `name` | Habilidad acreditada del paseador |
| `:Zone` | `name` | Colonia |
| `:Walk` | `id`, `date`, `durationMin`, `distanceKm`, `type`, `rating` | El paseo ocurrido |

### 4.2 Relaciones

```cypher
(:Owner)  -[:OWNS]->                         (:Dog)
(:Owner)  -[:LIVES_IN]->                     (:Zone)
(:Walker) -[:SERVES]->                       (:Zone)
(:Dog)    -[:HAS_TRAIT]->                    (:Trait)
(:Walker) -[:HAS_SKILL]->                    (:Skill)
(:Skill)  -[:QUALIFIES_FOR]->                (:Trait)
(:Walker) -[:PERFORMED]->                    (:Walk)
(:Dog)    -[:JOINED]->                       (:Walk)
(:Owner)  -[:RATED {score, date}]->          (:Walker)
(:Dog)    -[:CONFLICTED_WITH {reason, date}]-(:Dog)
(:Owner)  -[:REFERRED]->                     (:Owner)
(:Walker) -[:MENTORED_BY]->                  (:Walker)
```

### 4.3 Las dos decisiones que sostienen el modelo

**`:Walk` es un nodo, no una relación.** Un paseo individual podría ser una relación. Pero
**un paseo grupal conecta varios perros con un paseador**, y una relación en Neo4j solo une
dos nodos. Convertir el paseo en nodo propio permite que N perros apunten al mismo paseo —
y ese nodo se vuelve el punto de unión para inferir compatibilidad.

**La compatibilidad se infiere, no se almacena.** Deliberadamente **no existe** una relación
`[:COMPATIBLE_WITH]`:

```cypher
(a)-[:JOINED]->(w:Walk)<-[:JOINED]-(b)  WHERE w.rating >= 4
  AND NOT (a)-[:CONFLICTED_WITH]-(b)
```

Almacenarla sería guardar un dato derivado, que se desincroniza en cuanto ocurre un paseo
nuevo. El grafo la calcula al recorrer, siempre actualizada. `:CONFLICTED_WITH` sí se
almacena, porque un incidente es un **hecho observado**, no algo derivable.

---

## 5. Catálogo de consultas

🚧 *Diseñadas; la implementación está en curso. Esta sección se completa con el Cypher
verificado y su salida real conforme se prueban contra la nube.*

| # | Consulta | Qué demuestra del paradigma |
|---|---|---|
| 1 | Recomendación de paseador a 3 saltos, vía vecinos y perros similares | Profundidad variable |
| 2 | **Armado de grupo compatible para un paseo grupal** | Clique — el argumento central |
| 3 | Camino más corto dueño ↔ paseador: la cadena de confianza | El camino es la explicación |
| 4 | Paseadores acreditados para un perro difícil, con puntaje | Agregación sobre recorridos |
| 5 | Combinaciones de rasgos que producen paseos mal calificados | Insight accionable |

**Trabajo futuro:** tarifa dinámica por peso y distancia · planes recurrentes · módulo de
cuidadores · directorio de veterinarias.

---

## 6. Puesta en marcha

**Requisitos:** Python 3.13+ · [`uv`](https://docs.astral.sh/uv/) · una instancia de Neo4j
AuraDB (la capa gratuita alcanza).

```bash
git clone https://github.com/tomas-altamiranot/dogtrips-graph.git
cd dogtrips-graph
uv sync
```

`uv sync` lee `uv.lock` y reconstruye el entorno con las versiones exactas del desarrollo.

### Credenciales

Las credenciales **no están en el repositorio** y nunca deben estarlo. Copia el molde y
rellénalo con tu propia instancia:

```bash
cp .env.example .env
```

```ini
NEO4J_URI=neo4j+s://XXXXXXXX.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=tu_password_de_aura
NEO4J_DATABASE=
```

> `NEO4J_DATABASE` puede quedar **vacío**. En AuraDB la base suele llamarse como el id de la
> instancia y no `neo4j`; vacío usa la base por omisión del usuario.

`core/conexion.py` falla al arrancar si falta alguna variable, diciendo cuál.

### Verificar

```bash
uv run python scripts/probar_conexion.py
```

```
Conexion establecida con neo4j+s://XXXXXXXX.databases.neo4j.io
  nodos        : 0
  relaciones   : 0
  etiquetas    : (ninguna)
```

Si falla, el mensaje indica si el problema son las credenciales o la instancia. **AuraDB
Free suspende las instancias inactivas** tras varios días: si no alcanza el servidor, revisa
que esté despierta en la consola de Aura.

### 🚧 Aún no disponibles

```bash
uv run python scripts/seed.py           # cargar datos sintéticos
uv run python backend/manage.py runserver
```

---

## Autor

**Tomás Altamirano**
Ingeniería · Universidad Anáhuac Mayab

DogTrips es un proyecto propio, iniciado junto a Isaac Padilla y Stephanie Bayona como
ejercicio de ingeniería de requerimientos.
