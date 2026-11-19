"""Cliente visual de DogTrips Graph.

Uso:  uv run streamlit run cliente/app.py

Tres secciones, todas consultando AuraDB en vivo:
  1. Explorar el grafo: el vecindario de cualquier nodo a 1-4 saltos.
  2. Las 5 consultas: el resultado en tabla Y el dibujo de los caminos que lo explican.
  3. CRUD: dueños, perros y paseadores, con el dibujo de cómo quedó el nodo.

Este archivo solo arma la interfaz. La lógica y el Cypher viven en backend/core/.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from core import consultas as q  # noqa: E402
from core import crud  # noqa: E402
from core import grafo as g  # noqa: E402
from core.conexion import ErrorDeConexion, leer, verificar_conexion  # noqa: E402
from dibujo import html_grafo, resalte_todo  # noqa: E402

st.set_page_config(page_title="DogTrips Graph", page_icon="🐕", layout="wide")


# ─────────────────────────────────────────────────────────────────────────────
# Conexión y catálogos
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def conectar() -> str:
    return verificar_conexion()


try:
    uri = conectar()
except ErrorDeConexion as exc:
    st.error(f"No se pudo conectar a AuraDB: {exc}")
    st.stop()


@st.cache_data(ttl=120)
def opciones() -> dict[str, str]:
    """Etiqueta legible -> id, para los selectores."""
    filas = leer(
        """
        MATCH (n) WHERE n:Owner OR n:Dog OR n:Walker
        RETURN labels(n)[0] AS t, n.id AS id, n.name AS name ORDER BY t, name
        """
    )
    nombre = {"Owner": "Dueño", "Dog": "Perro", "Walker": "Paseador"}
    return {f"{nombre[f['t']]} · {f['name']} ({f['id']})": f["id"] for f in filas}


@st.cache_data(ttl=120)
def perros() -> dict[str, str]:
    return {f"{p['name']} ({p['id']})": p["id"] for p in crud.listar_perros()}


def limpiar_cache() -> None:
    st.cache_data.clear()


def indice(lista: list[str], contiene: str) -> int:
    return next((i for i, x in enumerate(lista) if contiene in x), 0)


def dibujar(sub: dict, alto: int = 560, **kw) -> None:
    if not sub["nodos"]:
        st.info("La consulta no devolvió nodos para dibujar.")
        return
    st.iframe(html_grafo(sub, alto=alto, **kw), height=alto + 10)


# ─────────────────────────────────────────────────────────────────────────────
# Barra lateral
# ─────────────────────────────────────────────────────────────────────────────

st.sidebar.title("🐕 DogTrips Graph")
st.sidebar.caption("Bases de Datos Avanzadas · Tomás Altamirano")
st.sidebar.success(f"Conectado a AuraDB\n\n`…{uri.split('.', 1)[-1]}`")
seccion = st.sidebar.radio("Sección", ["Explorar el grafo", "Las 5 consultas", "CRUD"])
total = leer("MATCH (n) WITH count(n) AS v MATCH ()-[r]->() RETURN v, count(r) AS e")[0]
st.sidebar.metric("Nodos en la nube", total["v"])
st.sidebar.metric("Relaciones", total["e"])


# ═════════════════════════════════════════════════════════════════════════════
# 1. EXPLORAR
# ═════════════════════════════════════════════════════════════════════════════

if seccion == "Explorar el grafo":
    st.header("Exploración del grafo por profundidad")
    st.write(
        "Un **salto** es el recorrido de una relación entre dos nodos, y la **profundidad** de un "
        "recorrido es el número de saltos desde el nodo de partida. Seleccione un nodo y una "
        "profundidad para observar cómo crece el conjunto de nodos alcanzables."
    )
    ops = opciones()
    etiquetas = list(ops)
    c1, c2 = st.columns([2, 1])
    elegido = c1.selectbox("Punto de partida", etiquetas, index=indice(etiquetas, "Jorge Dzul"))
    saltos = c2.slider("Saltos", 1, 4, 2)
    centro = ops[elegido]

    sub = g.vecindario(centro, saltos)
    key_centro = g.clave_de(sub, "id", centro)
    dist = g.distancias(sub, key_centro) if key_centro else {}

    cols = st.columns(saltos)
    for k in range(1, saltos + 1):
        cols[k - 1].metric(f"A {k} salto{'s' if k > 1 else ''}", sum(1 for d in dist.values() if d == k))
    dibujar(sub, centro=key_centro, dist=dist)

    with st.expander("Cypher que se ejecutó"):
        st.code(g.Q_VECINDARIO.strip(), language="cypher")
        st.caption(
            f"`$centro = '{centro}'`, `$saltos = {saltos}`. En SQL cada salto sería un JOIN "
            "escrito a mano; aquí la profundidad es un número."
        )


# ═════════════════════════════════════════════════════════════════════════════
# 2. LAS 5 CONSULTAS
# ═════════════════════════════════════════════════════════════════════════════

elif seccion == "Las 5 consultas":
    st.header("Las 5 consultas, con su dibujo")
    pp = perros()
    etiquetas = list(pp)
    perro_lbl = st.selectbox("Perro", etiquetas, index=indice(etiquetas, "Toby"))
    perro = pp[perro_lbl]
    nombre_perro = perro_lbl.split(" (")[0]

    t1, t2, t3, t4, t5 = st.tabs([
        "1 · Recomendar paseador", "2 · Armar grupo (clique)", "3 · Cadena de confianza",
        "4 · Paseadores acreditados", "5 · Combinaciones que salen mal",
    ])

    with t1:
        st.write(f"**Recomendación basada en la red del dueño.** Se identifican los paseadores que "
                 f"atendieron con buena calificación a perros de la red de vecinos del dueño de "
                 f"{nombre_perro}, priorizando los perros que comparten rasgos con él.")
        filas = q.recomendar_paseadores(perro)
        if filas:
            st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
            quien = st.selectbox("Dibujar el camino hacia", [f["paseador"] for f in filas])
            pid = next(f["id"] for f in filas if f["paseador"] == quien)
            sub = g.explica_recomendacion(perro, pid)
            dibujar(sub, resalte=resalte_todo(sub, "hl"))
        else:
            st.info("Sin recomendaciones: nadie en su red de vecinos tiene paseos bien calificados.")
        with st.expander("Cypher"):
            st.code(q.Q_RECOMENDAR.strip(), language="cypher")

    with t2:
        st.write("Un grupo es válido solo si **todos sus pares** son compatibles, es decir, si forma "
                 "un **clique**. La compatibilidad no se almacena: se infiere de paseos compartidos "
                 "con calificación de 4 o más y sin incidentes registrados.")
        tamano = st.number_input("Tamaño del grupo (incluido el perro)", 2, 6, 3)
        grupos = q.armar_grupo(perro, tamano=int(tamano))
        malos = q.descartados(perro)
        if grupos:
            textos = [f"{g_['base']} + {' + '.join(g_['companeros'])}" for g_ in grupos]
            st.success(f"{len(grupos)} grupo(s) de {tamano}. Misma consulta, solo cambió `$tamano`.")
            sel = st.selectbox("Dibujar el grupo", textos)
            nombres = sel.split(" + ")
            ids = [pp[k] for k in pp if k.split(" (")[0] in nombres]
            sub = g.explica_grupo(ids)
            res = {f"{a['s']}|{a['tipo']}|{a['d']}": ("no" if a["tipo"] == "CONFLICTED_WITH" else "ok")
                   for a in sub["aristas"]}
            dibujar(sub, resalte=res)
            st.caption("Verde: paseos buenos que comparten cada par. Rojo: incidentes (con quién no pueden salir).")
        else:
            st.warning(f"No hay grupos de {tamano} con todos los pares compatibles.")
        if malos:
            st.write("**Descartados por incidente:**")
            st.dataframe(pd.DataFrame(malos), hide_index=True)
        with st.expander("Cypher"):
            st.code(q.Q_GRUPO.strip(), language="cypher")

    with t3:
        st.write("**Cadena de confianza.** El camino más corto entre un dueño y un paseador sin trato "
                 "previo se presenta como la justificación de la recomendación.")
        par = q.par_para_explicar()
        ops = opciones()
        duenos = [k for k in ops if k.startswith("Dueño")]
        paseadores = [k for k in ops if k.startswith("Paseador")]
        c1, c2 = st.columns(2)
        d_lbl = c1.selectbox("Dueño", duenos, index=indice(duenos, par["dueno"]) if par else 0)
        w_lbl = c2.selectbox("Paseador", paseadores, index=indice(paseadores, par["paseador"]) if par else 0)
        camino = q.cadena_de_confianza(ops[d_lbl], ops[w_lbl])
        if camino:
            st.info(f"**{camino['saltos']} saltos:** {q.explicar_camino(camino)}")
            sub = g.explica_camino(ops[d_lbl], ops[w_lbl])
            dibujar(sub, alto=320, resalte=resalte_todo(sub, "ok"))
        else:
            st.warning("No hay un camino entre ellos por relaciones de confianza.")
        with st.expander("Cypher"):
            st.code(q.Q_CAMINO.strip(), language="cypher")

    with t4:
        st.write("Los rasgos describen al perro; las habilidades, al paseador. "
                 "`(:Skill)-[:QUALIFIES_FOR]->(:Trait)` traduce entre los dos dentro del grafo.")
        acr = q.acreditados_para(perro)
        if acr:
            st.dataframe(pd.DataFrame(acr), hide_index=True, width="stretch")
            sub = g.explica_acreditados(perro, [a["paseador"] for a in acr])
            dibujar(sub, alto=460, resalte=resalte_todo(sub, "hl"))
        else:
            st.info("Ningún paseador tiene habilidades para los rasgos de este perro.")
        with st.expander("Cypher"):
            st.code(q.Q_ACREDITADOS.strip(), language="cypher")

    with t5:
        st.write("Análisis sobre el grafo completo: pares de rasgos asociados a paseos grupales mal "
                 "calificados, comparados contra el promedio general mediante el indicador *lift*.")
        combos = q.combinaciones_problematicas()
        if combos:
            st.metric("Paseos grupales que salen mal, en promedio", f"{combos[0]['promedioGlobal']} %")
            df = pd.DataFrame(combos)
            df["combinación"] = df["rasgoA"] + " + " + df["rasgoB"]
            st.bar_chart(df.set_index("combinación")["lift"], horizontal=True)
            st.dataframe(df[["combinación", "malos", "total", "porcentajeMalos", "lift"]],
                         hide_index=True, width="stretch")
        with st.expander("Cypher"):
            st.code(q.Q_COMBINACIONES.strip(), language="cypher")


# ═════════════════════════════════════════════════════════════════════════════
# 3. CRUD
# ═════════════════════════════════════════════════════════════════════════════

else:
    st.header("CRUD: dueños, perros y paseadores")
    cat = crud.catalogos()
    td, tp, tw = st.tabs(["Dueños", "Perros", "Paseadores"])

    def resultado(accion, *args, **kwargs):
        """Ejecuta una operación del CRUD, muestra el error si lo hay y refresca."""
        try:
            r = accion(*args, **kwargs)
            limpiar_cache()
            return r
        except crud.ErrorDeDatos as exc:
            st.error(str(exc))
            return None

    def mostrar_en_grafo(id_: str) -> None:
        st.caption("Así quedó en el grafo (1 salto):")
        sub = g.vecindario(id_, 1)
        dibujar(sub, alto=300, centro=g.clave_de(sub, "id", id_))

    with td:
        st.dataframe(pd.DataFrame(crud.listar_duenos()), hide_index=True, width="stretch")
        c1, c2, c3 = st.columns(3)
        with c1.form("crear_dueno", clear_on_submit=True):
            st.subheader("Crear")
            n = st.text_input("Nombre")
            t = st.text_input("Teléfono")
            z = st.selectbox("Colonia", cat["zonas"])
            if st.form_submit_button("Crear dueño") and n and t:
                r = resultado(crud.crear_dueno, n, t, z)
                if r:
                    st.session_state["ultimo"] = r["id"]
                    st.success(f"Creado {r['id']}")
        with c2.form("act_dueno"):
            st.subheader("Actualizar")
            i = st.text_input("id", placeholder="own-041")
            n = st.text_input("Nuevo nombre (opcional)")
            t = st.text_input("Nuevo teléfono (opcional)")
            z = st.selectbox("Nueva colonia", ["(igual)"] + cat["zonas"])
            if st.form_submit_button("Actualizar") and i:
                if resultado(crud.actualizar_dueno, i, name=n or None, phone=t or None,
                             zona=None if z == "(igual)" else z):
                    st.session_state["ultimo"] = i
                    st.success("Actualizado")
        with c3.form("borrar_dueno"):
            st.subheader("Borrar")
            i = st.text_input("id ", placeholder="own-041")
            ok = st.checkbox("Entiendo que también se borran sus perros")
            if st.form_submit_button("Borrar") and i and ok:
                r = resultado(crud.borrar_dueno, i)
                if r:
                    st.success(f"Borrado {r['nombre']} y {r['perrosBorrados']} perro(s)")

    with tp:
        st.dataframe(pd.DataFrame(crud.listar_perros()), hide_index=True, width="stretch")
        c1, c2 = st.columns(2)
        with c1.form("crear_perro", clear_on_submit=True):
            st.subheader("Crear")
            o = st.text_input("id del dueño", placeholder="own-001")
            n = st.text_input("Nombre")
            b = st.text_input("Raza")
            s = st.selectbox("Tamaño", crud.TAMANOS)
            w = st.number_input("Peso (kg)", 1, 90, 15)
            a = st.number_input("Edad (meses)", 1, 240, 24)
            e = st.selectbox("Energía", crud.NIVELES)
            r_ = st.multiselect("Rasgos", cat["rasgos"])
            if st.form_submit_button("Crear perro") and o and n and b:
                r = resultado(crud.crear_perro, o, n, b, s, int(w), int(a), e, r_)
                if r:
                    st.session_state["ultimo"] = r["id"]
                    st.success(f"Creado {r['id']}")
        with c2.form("act_perro"):
            st.subheader("Actualizar o borrar")
            i = st.text_input("id", placeholder="dog-056")
            w = st.number_input("Nuevo peso (0 = igual)", 0, 90, 0)
            e = st.selectbox("Nueva energía", ["(igual)", *crud.NIVELES])
            r_ = st.multiselect("Nuevos rasgos (reemplazan)", cat["rasgos"])
            accion = st.radio("Acción", ["Actualizar", "Borrar"], horizontal=True)
            if st.form_submit_button("Aplicar") and i:
                if accion == "Borrar":
                    r = resultado(crud.borrar_perro, i)
                    if r:
                        st.success(f"Borrado {r['nombre']}")
                elif resultado(crud.actualizar_perro, i, rasgos=r_ or None,
                               weightKg=int(w) or None,
                               energyLevel=None if e == "(igual)" else e):
                    st.session_state["ultimo"] = i
                    st.success("Actualizado")

    with tw:
        st.dataframe(pd.DataFrame(crud.listar_paseadores()), hide_index=True, width="stretch")
        c1, c2 = st.columns(2)
        with c1.form("crear_paseador", clear_on_submit=True):
            st.subheader("Crear")
            n = st.text_input("Nombre")
            x = st.number_input("Meses de experiencia", 0, 600, 6)
            f = st.selectbox("Fuerza", crud.FUERZAS)
            z = st.multiselect("Colonias que cubre", cat["zonas"])
            h = st.multiselect("Habilidades", cat["habilidades"])
            if st.form_submit_button("Crear paseador") and n:
                r = resultado(crud.crear_paseador, n, int(x), f, z, h)
                if r:
                    st.session_state["ultimo"] = r["id"]
                    st.success(f"Creado {r['id']}")
        with c2.form("act_paseador"):
            st.subheader("Actualizar o borrar")
            i = st.text_input("id", placeholder="wlk-016")
            v = st.selectbox("Verificado", ["(igual)", "sí", "no"])
            h = st.multiselect("Nuevas habilidades (reemplazan)", cat["habilidades"])
            accion = st.radio("Acción ", ["Actualizar", "Borrar"], horizontal=True)
            if st.form_submit_button("Aplicar") and i:
                if accion == "Borrar":
                    r = resultado(crud.borrar_paseador, i)
                    if r:
                        st.success(f"Borrado {r['nombre']}")
                elif resultado(crud.actualizar_paseador, i, habilidades=h or None,
                               verified=None if v == "(igual)" else v == "sí"):
                    st.session_state["ultimo"] = i
                    st.success("Actualizado")

    ultimo = st.session_state.get("ultimo")
    if ultimo:
        st.divider()
        st.subheader(f"Último nodo creado o modificado: {ultimo}")
        mostrar_en_grafo(ultimo)
