# DogTrips Graph

Capa de grafo para **DogTrips**, una plataforma de paseo de perros: los dueños contratan
paseadores, y los perros salen solos o en grupo.

El sistema responde tres preguntas que una base relacional contesta con dificultad:

1. **¿Qué paseador le conviene a este perro?** — y **¿por qué confiar en él?**
2. **¿Qué perros pueden salir juntos en un paseo grupal?**
3. **¿Qué combinaciones terminan mal?**

**Bases de Datos Avanzadas — Universidad Anáhuac Mayab**
Proyecto individual · Neo4j AuraDB · driver oficial `neo4j` para Python

---

## Estado

| Componente | Estado |
|---|---|
| Conexión a Neo4j AuraDB con credenciales por entorno y reintento automático | ✅ |
| Modelo del grafo (7 etiquetas, 12 tipos de relación) | ✅ |
| Script de datos sintéticos (`seed.py`) | ✅ 288 nodos · 933 relaciones |
| CRUD sobre dueños, perros y paseadores (menú en terminal) | ✅ |
| Las 5 consultas especializadas | ✅ Probadas contra la nube |
| Interfaz gráfica (Streamlit) que dibuja el grafo consultado en vivo | ✅ |
| API REST con Django | Trabajo futuro |

---

## 1. El dominio

Dejar a tu perro con un desconocido es un acto de confianza. Una plataforma de paseos vive
o muere por dos cosas: **acertar en el emparejamiento** y **poder explicarlo**.

El sistema modela cuatro realidades del negocio: quién es el dueño y dónde vive, cómo es el
perro (tamaño, energía y sobre todo carácter), qué sabe hacer el paseador, y qué pasó en
cada paseo.

### El problema central: los paseos grupales

Un paseo grupal es más barato para el dueño y más rentable para el paseador. Pero no
cualquier grupo funciona, y **la compatibilidad no es transitiva**. En los datos del proyecto:

```
        Toby ──✓── Bruno
          │          │
          ✗          ✓        Toby y Bruno se llevan bien.
          │          │        Bruno y Bacab se llevan bien.
          └─ Bacab ──┘        Toby y Bacab tuvieron un incidente.
```

Armar un grupo no es elegir perros compatibles con el primero: es encontrar un subconjunto
donde **todos los pares** funcionan. En teoría de grafos eso se llama **clique**.

### Lo que declara el dueño y lo que observa el paseador

El grafo separa dos fuentes de información:

| Fuente | Relación | Para qué se usa |
|---|---|---|
| El dueño, al registrar al perro | `(:Dog)-[:HAS_TRAIT]->(:Trait)` | Qué paseador está capacitado (consulta 4) y qué perros se parecen (consulta 1) |
| El paseador, en cada paseo | `(:Dog)-[:JOINED]->(:Walk {rating})`, `[:CONFLICTED_WITH]` | Quién puede salir con quién (consulta 2) |

La compatibilidad entre perros se decide **solo con lo observado en paseos**. Un perro que en
casa no tolera a otro puede llevarse bien con él en la calle; lo que cuenta es lo que pasó
en el paseo.

> **Datos sintéticos.** Todo se genera con `scripts/seed.py`. No hay información de
> personas, perros ni paseadores reales. Las colonias son de Mérida, Yucatán. El seed
> **simula** el historial de paseos, calificaciones e incidentes que produciría la app del
> paseador.

---

## 2. Por qué un grafo y no SQL

### 2.1 Formar grupos es un problema de grafos

Dos perros son compatibles si **ya coincidieron en un paseo bien calificado** y **no existe
un incidente registrado** entre ellos. Para un grupo hay que revisar cada par: 3 perros son
3 pares, 4 son 6 y 5 son 10.

En SQL cada par es un `EXISTS` más un `NOT EXISTS`, y cada perro es otra tabla en el `FROM`:
**la consulta se reescribe cada vez que cambia el tamaño del grupo**. En Cypher la regla
"todos con todos" se escribe una vez y el tamaño es un parámetro:

```cypher
UNWIND apoc.coll.combinations(candidatos, $tamano - 1) AS grupo
WITH base, grupo
WHERE ALL(x IN grupo WHERE ALL(y IN grupo WHERE
        elementId(x) >= elementId(y)
        OR (NOT (x)-[:CONFLICTED_WITH]-(y)
            AND EXISTS { (x)-[:JOINED]->(k:Walk)<-[:JOINED]-(y) WHERE k.rating >= $minimo })))
```

### 2.2 Recorridos de profundidad variable

Para recomendar un paseador, el sistema pregunta a la red de vecinos del dueño. En SQL
**cada salto es un JOIN escrito a mano** y la profundidad queda fija. En Cypher es un número:

```cypher
MATCH (yo)-[:LIVES_IN|REFERRED*1..3]-(vecino:Owner)
```

Con 1 salto llega a quien te refirió; con 2, a quien vive en tu colonia; con 3, a la colonia
de quien te refirió.

### 2.3 El camino es la explicación

Cuando un dueño pregunta *"¿por qué me recomiendas a esta persona?"*, la respuesta es un
camino, obtenido con `shortestPath()` y devuelto tal cual:

```
Raul Kantun --[REFERRED]-- Arturo Kumul --[RATED 5/5]-- Gabriela Sansores
```

*"Arturo, el vecino que te refirió, le puso 5 estrellas."* En un modelo relacional no
existe un tipo de dato "camino": la justificación se reconstruye en código.

### 2.4 Dónde **no** conviene el grafo

| Problema | Dónde pertenece realmente |
|---|---|
| Reservas, pagos, facturación | **Relacional**: importan la integridad y la auditoría |
| Ubicación del perro en tiempo real | **Series de tiempo**: es un flujo de puntos, no una red |
| Fotos y documentos | Almacenamiento de objetos |

Este grafo resuelve **emparejamiento, confianza y análisis**.

---

## 3. Arquitectura

```
┌──────────────────────────┐   ┌──────────────────────────┐
│  scripts/  (terminal)    │   │  cliente/  (gráfico)     │
│  crud.py                 │   │  app.py    Streamlit     │
│  probar_consultas.py     │   │  dibujo.py d3 en iframe  │
│  seed.py                 │   │                          │
└────────────┬─────────────┘   └─────────────┬────────────┘
             └──────────────┬────────────────┘
                            │ llamadas a funciones Python
┌───────────────────────────▼──────────────────┐
│  backend/core/   Python puro                 │
│   conexion.py  driver, credenciales, reintentos
│   crud.py      altas, bajas y cambios        │
│   consultas.py las 5 consultas especializadas│
│   grafo.py     subgrafos para dibujar        │
└──────────────────┬───────────────────────────┘
                   │ driver oficial neo4j · neo4j+s (TLS)
┌──────────────────▼───────────────────────────┐
│        Neo4j AuraDB Free  —  nube            │
└──────────────────────────────────────────────┘
```

**`core/` no sabe que existe una interfaz.** Las dependencias apuntan en una sola dirección
(`scripts → core → neo4j` y `cliente → core → neo4j`). Prueba de ello: hay **dos clientes**
sobre el mismo núcleo, uno de terminal y uno gráfico, y ninguno contiene Cypher propio de
negocio. Una API web o la app móvil se conectarían a `core/` de la misma forma.

### 3.1 Dos clientes

| Cliente | Para qué sirve |
|---|---|
| **Terminal** (`scripts/`) | Operación directa: menú CRUD y ejecución de las 5 consultas con su salida en texto |
| **Gráfico** (`cliente/app.py`) | Visualización: dibuja los nodos y relaciones que devuelve cada consulta |

La interfaz gráfica existe porque un grafo es difícil de comprender sin verlo. Tiene tres
secciones:

1. **Exploración por profundidad:** se elige un nodo y una profundidad (1 a 4 saltos) y se
   dibuja el vecindario, con el número de nodos alcanzados en cada nivel.
2. **Las 5 consultas:** cada resultado se muestra en tabla **y** como el subgrafo de caminos
   que lo justifican (por ejemplo, la cadena de confianza completa o los paseos que comparten
   los perros de un grupo).
3. **CRUD con formularios:** después de crear o modificar un nodo se dibuja cómo quedó
   conectado en la base.

**Cómo se construyó.** `core/grafo.py` ejecuta consultas que devuelven caminos y los convierte
con `Result.graph()` del driver oficial, que reúne todos los nodos y relaciones del resultado
en un solo objeto. `cliente/dibujo.py` dibuja ese subgrafo con d3 (layout de fuerzas) dentro de
un `st.iframe`. El zoom es **semántico**: al acercar, los nodos se separan y el texto, los nodos
y las líneas conservan su tamaño, de modo que acercarse permite leer las zonas densas.

### 3.2 Conexión estable

- `conexion.py` es el **único** módulo que crea un driver. Es un singleton: el driver
  administra su propio pool de conexiones y es caro de crear.
- Todas las consultas pasan por `leer()` y `escribir()`, que usan `driver.execute_query()`.
  Esa función corre la consulta en una **transacción administrada que reintenta sola** hasta
  30 segundos ante `ServiceUnavailable` y `SessionExpired`. Desde algunas redes el saludo TLS
  con Aura se corta a medias (`SSL UNEXPECTED_EOF`); con el reintento, el programa sigue.
- Las credenciales viajan solo por variables de entorno (`.env`, excluido del repositorio).
  El programa falla al arrancar si falta alguna, diciendo cuál.

### 3.3 Estructura

```
dogtrips-graph/
├── README.md
├── pyproject.toml          dependencias (gestionado con uv)
├── uv.lock                 versiones exactas
├── .env.example            molde de las credenciales
├── backend/core/
│   ├── conexion.py         driver, credenciales, leer(), leer_grafo() y escribir()
│   ├── crud.py             CRUD de Owner, Dog y Walker
│   ├── consultas.py        las 5 consultas especializadas
│   └── grafo.py            subgrafos que explican cada consulta, para dibujar
├── cliente/
│   ├── app.py              interfaz gráfica (Streamlit)
│   └── dibujo.py           dibujo del grafo con d3 y zoom semántico
└── scripts/
    ├── seed.py             crea el grafo con datos sintéticos de Mérida
    ├── crud.py             menú interactivo del CRUD
    ├── probar_consultas.py corre las 5 consultas (guion de la demo)
    └── probar_conexion.py  diagnóstico de conectividad
```

---

## 4. Modelo del grafo

```
              ┌──────┐  LIVES_IN   ┌──────┐   SERVES   ┌────────┐
              │ Owner│────────────►│ Zone │◄───────────│ Walker │
              └──┬───┘             └──────┘            └───┬────┘
                 │ OWNS                     RATED {score}  │ HAS_SKILL
                 ▼        ◄────────────────────────────────┤
              ┌─────┐                                      ▼
              │ Dog │                                  ┌───────┐
              └──┬──┘                                  │ Skill │
        HAS_TRAIT│  │ JOINED                           └───┬───┘
                 ▼  ▼                                      │ QUALIFIES_FOR
          ┌───────┐ ┌──────┐   PERFORMED                   │
          │ Trait │ │ Walk │◄─────────────── Walker        │
          └───▲───┘ └──────┘                               │
              └────────────────────────────────────────────┘

      Dog ──CONFLICTED_WITH {reason, date}── Dog   (incidente registrado)
    Owner ──REFERRED──► Owner                      (red de referidos)
   Walker ──MENTORED_BY──► Walker                  (progresión del paseador)
```

### 4.1 Nodos

| Label | Propiedades | Para qué |
|---|---|---|
| `:Owner` | `id`, `name`, `phone` | El dueño |
| `:Dog` | `id`, `name`, `breed`, `sizeCategory`, `weightKg`, `ageMonths`, `energyLevel` | El perro |
| `:Walker` | `id`, `name`, `experienceMonths`, `strengthLevel`, `verified`, `ratingAvg` | El paseador |
| `:Trait` | `name`, `category` | Rasgo del perro: social, temperamento o manejo |
| `:Skill` | `name` | Habilidad acreditada del paseador |
| `:Zone` | `name` | Colonia de Mérida |
| `:Walk` | `id`, `date`, `durationMin`, `distanceKm`, `type`, `rating` | El paseo ocurrido |

Restricciones de unicidad sobre `id` (Owner, Dog, Walker, Walk) y `name` (Zone, Trait, Skill).

### 4.2 Decisiones de modelado

- **`:Walk` es un nodo, no una relación.** Un paseo grupal une a varios perros con un
  paseador, y una relación solo une dos nodos. El nodo es además el punto de encuentro
  del que se infiere la compatibilidad.
- **La compatibilidad se infiere, no se almacena.** No existe `[:COMPATIBLE_WITH]`:
  sería un dato derivado que se desincroniza con cada paseo nuevo.
- **`:CONFLICTED_WITH` sí se almacena**, porque un incidente es un hecho observado.
- **Los rasgos y habilidades son nodos**, para poder recorrerlos: dos perros que comparten
  un rasgo quedan a dos saltos, y `(:Skill)-[:QUALIFIES_FOR]->(:Trait)` traduce entre el
  vocabulario del paseador y el del perro dentro del grafo.
- **`ratingAvg` es nulo, no 0, si nadie ha calificado al paseador.** Un paseador nuevo no
  es un paseador malo.

---

## 5. Catálogo de consultas

Código completo en [`backend/core/consultas.py`](backend/core/consultas.py). Resultados reales
con el perro de la demo, **Toby** (`dog-045`: Juguetón, Reactivo, Fuerte).

| # | Consulta | Qué demuestra | Resultado real |
|---|---|---|---|
| 1 | Recomendación de paseador vía la red de vecinos (`*1..3`) y perros parecidos | Profundidad variable | Gabriela Sansores: 4 perros de vecinos, 3 parecidos a Toby, 4.42★ |
| 2 | **Armado de grupo compatible (clique)** con tamaño como parámetro | El argumento central | De 3: Toby + Bruno + Pancho (y 2 más). De 4: Toby + Bruno + Pancho + Ruco. Bacab descartado por incidente |
| 3 | Camino más corto dueño ↔ paseador | El camino es la explicación | Raul → REFERRED → Arturo → RATED 5/5 → Gabriela |
| 4 | Paseadores acreditados para un perro difícil | Agregación sobre recorridos | Irene Castillo cubre Reactivo y Fuerte, en su zona |
| 5 | Combinaciones de rasgos que producen paseos mal calificados | Análisis sobre todo el grafo | Dominante + Reactivo: 27 de 42 paseos salen mal (lift 1.72) |

La consulta 5 redescubre una regla que `seed.py` sembró a propósito en los datos. Eso
demuestra que la consulta encuentra patrones reales y no ruido.

### CRUD

`backend/core/crud.py` implementa crear, leer, actualizar y borrar para `:Owner`, `:Dog` y
`:Walker`. Crear un perro crea el nodo **y** sus relaciones (`OWNS`, `HAS_TRAIT`) en una sola
consulta. Las listas (rasgos, zonas, habilidades) se validan contra el catálogo **antes** de
escribir. Borrar un dueño borra también a sus perros (`DETACH DELETE`); los paseos se
conservan como historia.

**Trabajo futuro:** API REST con Django · app móvil del paseador que registre paseos, incidentes
y los rasgos que observa en el primer paseo · tarifa dinámica por peso y distancia.

---

## 6. Puesta en marcha

**Requisitos:** Python 3.13+ · [`uv`](https://docs.astral.sh/uv/) · una instancia de Neo4j
AuraDB (la capa gratuita alcanza; incluye APOC, que usa la consulta 2).

```bash
git clone https://github.com/tomas-altamiranot/dogtrips-graph.git
cd dogtrips-graph
uv sync
```

### Credenciales

Las credenciales **no están en el repositorio**. Copia el molde y rellénalo con tu instancia:

```bash
cp .env.example .env
```

```ini
NEO4J_URI=neo4j+s://XXXXXXXX.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=tu_password_de_aura
NEO4J_DATABASE=
```

> `NEO4J_DATABASE` puede quedar **vacío**: en AuraDB la base suele llamarse como el id de la
> instancia; vacío usa la base por omisión del usuario.

### Ejecutar

```bash
uv run python scripts/probar_conexion.py   # 1. verifica la conexión
uv run python scripts/seed.py              # 2. carga los datos (borra y recrea el grafo)
uv run python scripts/probar_consultas.py  # 3. corre las 5 consultas (terminal)
uv run python scripts/crud.py              # 4. menú del CRUD (terminal)
uv run streamlit run cliente/app.py        # 5. interfaz gráfica (abre el navegador)
```

El seed usa una semilla fija: el grafo sale idéntico cada vez y las consultas devuelven
siempre los mismos resultados.

**AuraDB Free suspende las instancias inactivas** tras varios días. Si no alcanza el servidor,
revisa que esté despierta en la consola de Aura.

---

## Autor

**Tomás Altamirano**
Ingeniería · Universidad Anáhuac Mayab

DogTrips es un proyecto propio, iniciado junto a Isaac Padilla y Stephanie Bayona como
ejercicio de ingeniería de requerimientos.
