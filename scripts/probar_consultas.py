"""Corre las cinco consultas contra AuraDB y muestra su salida.

Uso:  uv run python scripts/probar_consultas.py

Sirve como prueba de que las consultas funcionan y como guion de la demo.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from core import consultas as q  # noqa: E402
from core.conexion import cerrar, verificar_conexion  # noqa: E402

# Toby: Jugueton, Reactivo, Fuerte. Se eligio porque tiene un incidente
# registrado (la parte de "descartados" no sale vacia) y forma grupos validos.
PERRO = "dog-045"
NOMBRE = "Toby"


def titulo(n: int, texto: str) -> None:
    print(f"\n{'=' * 68}\n  {n}. {texto}\n{'=' * 68}")


def main() -> None:
    print(f"Conectado a {verificar_conexion()}")

    titulo(1, f"Paseadores recomendados para {NOMBRE} (red de vecinos, 1 a 3 saltos)")
    filas = q.recomendar_paseadores(PERRO)
    for f in filas:
        print(f"   {f['paseador']:<22} perros_de_vecinos={f['perrosDeVecinos']:<3} "
              f"parecidos={f['parecidosAlMio']:<3} "
              f"calif_con_vecinos={f['calificacionConVecinos']:<5} "
              f"general={f['promedioGeneral'] if f['promedioGeneral'] is not None else 'sin calif.'}")
    if not filas:
        print("   (vacio)")

    titulo(2, f"Grupos compatibles con {NOMBRE}  [LA ESTRELLA]")
    # La MISMA consulta para grupos de 3 y de 4: el tamano es un parametro.
    for tamano in (3, 4):
        grupos = q.armar_grupo(PERRO, tamano=tamano)
        print(f"\n   Grupos de {tamano}:")
        for g in grupos:
            print(f"   {g['base']} + {' + '.join(g['companeros'])}")
            print(f"        tamanos={g['tamanos']}  energias={g['energias']}")
        if not grupos:
            print("   (ninguno)")

    malos = q.descartados(PERRO)
    if malos:
        print("\n   Descartados por incidente:")
        for m in malos:
            print(f"      {m['perro']:<12} {m['motivo']}  ({m['fecha']})")
    else:
        print(f"\n   {NOMBRE} no tiene incidentes registrados.")

    titulo(3, "Cadena de confianza: dueno -> paseador")
    # Se busca un par real: un dueno cuyo perro fue paseado por alguien a quien
    # el dueno NO ha calificado. Es el caso interesante: "no lo conozco, por que
    # deberia confiar en el".
    par = q.par_para_explicar()
    if par:
        camino = q.cadena_de_confianza(par["dueno"], par["paseador"])
        if camino:
            print(f"   {par['nombreDueno']}  ->  {par['nombrePaseador']}"
                  f"   ({camino['saltos']} saltos)")
            print(f"   {q.explicar_camino(camino)}")
        else:
            print("   (sin camino dentro del limite de saltos)")
    else:
        print("   (no se encontro un par para explicar)")

    titulo(4, f"Paseadores acreditados para {NOMBRE}")
    acr = q.acreditados_para(PERRO)
    for a in acr:
        marca = "en su zona" if a["cubreZona"] else "fuera de zona"
        calif = (f"{a['calificacion']} ({a['numCalificaciones']} calif.)"
                 if a["calificacion"] is not None else "sin calificaciones")
        print(f"   {a['paseador']:<22} cubre {a['cuantosCubre']} rasgo(s): "
              f"{a['rasgosQueCubre']}")
        print(f"        fuerza={a['fuerza']} exp={a['mesesExperiencia']}m "
              f"calif={calif}  [{marca}: {a['zonaDelPerro']}]")
    if not acr:
        print("   (vacio)")

    titulo(5, "Combinaciones de rasgos que salen mal")
    combos = q.combinaciones_problematicas()
    if combos:
        print(f"   (de cada 100 paseos grupales, {combos[0]['promedioGlobal']} "
              f"salen mal en promedio)\n")
    for c in combos:
        print(f"   {c['rasgoA']:<16} + {c['rasgoB']:<16} "
              f"{c['porcentajeMalos']:>5}%  lift={c['lift']:<5} "
              f"({c['malos']} de {c['total']} paseos)")
    if not combos:
        print("   (vacio)")

    cerrar()
    print()


if __name__ == "__main__":
    main()
