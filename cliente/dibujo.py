"""Convierte un subgrafo ({"nodos", "aristas"}) en una pagina HTML interactiva.

Se dibuja con d3 (layout de fuerzas) dentro de un iframe de Streamlit.

ZOOM SEMANTICO: al acercar, NO se agranda el dibujo; se separan los nodos.
Letras, circulos y lineas conservan su tamano en pantalla, asi que acercarse
sirve para leer una zona amontonada en vez de solo ver todo mas grande.
Tecnicamente: en cada evento de zoom se recalculan las coordenadas con
transform.applyX/applyY en lugar de escalar el grupo SVG completo.
"""

from __future__ import annotations

import json

COLORES = {
    "Owner": "#2F6FB3", "Dog": "#D9792B", "Walker": "#2B8A57", "Walk": "#8A96A3",
    "Trait": "#8A55B5", "Skill": "#1E8C8C", "Zone": "#C9A227",
}
NOMBRES = {
    "Owner": "Dueño", "Dog": "Perro", "Walker": "Paseador", "Walk": "Paseo",
    "Trait": "Rasgo", "Skill": "Habilidad", "Zone": "Colonia",
}

_PLANTILLA = r"""
<!doctype html><html><head><meta charset="utf-8">
<style>
  body{margin:0;font-family:"Source Sans Pro",system-ui,sans-serif;background:#fff}
  #lienzo{width:100%;height:__ALTO__px;display:block;cursor:grab;background:#FAFBFC;border-radius:8px}
  .ley{position:absolute;top:8px;left:10px;display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:#445}
  .ley i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:-1px}
  .ayuda{position:absolute;top:8px;right:12px;font-size:11px;color:#778}
  #ficha{position:absolute;left:10px;bottom:10px;max-width:330px;max-height:45%;overflow:auto;background:#fff;
    border:1px solid #D6DDE4;border-radius:8px;padding:8px 12px;font-size:12.5px;box-shadow:0 2px 8px rgba(0,0,0,.08)}
  #ficha:empty{display:none}
  #ficha b.t{font-size:10.5px;letter-spacing:.08em;text-transform:uppercase}
  .lk{stroke:#C3CCD5;stroke-width:1.3}
  .lk.hl{stroke:#15607F;stroke-width:3}
  .lk.ok{stroke:#2B7A47;stroke-width:3}
  .lk.no{stroke:#B0382F;stroke-width:3;stroke-dasharray:6 4}
  .lbl{font-size:11px;fill:#1A222B;pointer-events:none;paint-order:stroke;stroke:#FAFBFC;stroke-width:3px}
  .rt{font-size:9px;fill:#8893A0;pointer-events:none}
  .nd{stroke:#fff;stroke-width:1.5;cursor:pointer}
  .nd.centro{stroke:#111;stroke-width:3}
  .dim{opacity:.15}
</style></head><body>
<svg id="lienzo"></svg>
<div class="ley" id="ley"></div>
<div class="ayuda">rueda = zoom · arrastra el fondo = mover · toca un nodo = detalles</div>
<div id="ficha"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script>
const D = __DATOS__;
const COL = __COLORES__, NOM = __NOMBRES__;
const R = {Owner:9,Dog:9,Walker:10,Walk:5,Trait:7,Skill:7,Zone:14};
const svg = d3.select('#lienzo'), W = svg.node().clientWidth || 900, H = __ALTO__;
const nodos = D.nodos.map(n => ({...n})), idx = new Map(nodos.map(n=>[n.key,n]));
const aristas = D.aristas.filter(a=>idx.has(a.s)&&idx.has(a.d)).map(a=>({...a, source:a.s, target:a.d}));
const tipos = [...new Set(nodos.map(n=>n.tipo))];
document.getElementById('ley').innerHTML = tipos.map(t=>`<span><i style="background:${COL[t]||'#999'}"></i>${NOM[t]||t}</span>`).join('');

const sim = d3.forceSimulation(nodos)
  .force('link', d3.forceLink(aristas).id(d=>d.key).distance(a=>a.tipo==='JOINED'||a.tipo==='PERFORMED'?36:56).strength(.5))
  .force('charge', d3.forceManyBody().strength(nodos.length>150?-55:-160))
  .force('collide', d3.forceCollide(d=>(R[d.tipo]||8)+4))
  .force('x', d3.forceX(W/2).strength(.05)).force('y', d3.forceY(H/2).strength(.07)).stop();
for (let i=0;i<350;i++) sim.tick();

const RES = D.resalte || {}, DIST = D.dist || null, CENTRO = D.centro || null;
const enfocado = Object.keys(RES).length > 0;
const claveA = a => a.s+'|'+a.tipo+'|'+a.d;
const g = svg.append('g');
const lk = g.append('g').selectAll('line').data(aristas).join('line')
  .attr('class', a => { const c = RES[claveA(a)]; return 'lk ' + (c || (enfocado ? 'dim' : '')); });
const rt = g.append('g').selectAll('text').data(aristas.filter(a=>RES[claveA(a)])).join('text').attr('class','rt')
  .attr('text-anchor','middle').text(a=>a.tipo + (a.props.score!==undefined?` ${a.props.score}/5`:''));
const nd = g.append('g').selectAll('g').data(nodos).join('g').style('cursor','pointer').on('click',(e,d)=>ficha(d));
nd.each(function(d){
  const s = d3.select(this), r = R[d.tipo]||8, col = COL[d.tipo]||'#999';
  if (d.tipo==='Walk') s.append('rect').attr('x',-r).attr('y',-r).attr('width',2*r).attr('height',2*r).attr('rx',2).attr('fill',col).attr('class','nd');
  else s.append('circle').attr('r',r).attr('fill',col).attr('class','nd'+(d.key===CENTRO?' centro':''));
});
if (DIST) nd.classed('dim', d => DIST[d.key] === undefined);
const lb = g.append('g').selectAll('text').data(nodos.filter(n => n.tipo!=='Walk' || nodos.length<60)).join('text')
  .attr('class','lbl').text(d=>d.nombre);

// Zoom semantico: se mueven las coordenadas, no se escala el dibujo.
let T = d3.zoomIdentity;
function pintar(){
  const X = d => T.applyX(d.x), Y = d => T.applyY(d.y);
  lk.attr('x1',a=>X(a.source)).attr('y1',a=>Y(a.source)).attr('x2',a=>X(a.target)).attr('y2',a=>Y(a.target));
  rt.attr('x',a=>(X(a.source)+X(a.target))/2).attr('y',a=>(Y(a.source)+Y(a.target))/2-4);
  nd.attr('transform', d=>`translate(${X(d)},${Y(d)})`);
  lb.attr('x', d=>X(d)+(R[d.tipo]||8)+3).attr('y', d=>Y(d)+4);
}
svg.call(d3.zoom().scaleExtent([0.2, 20]).on('zoom', e => { T = e.transform; pintar(); }));
pintar();

function ficha(d){
  const props = Object.entries(d.props).map(([k,v])=>`<div><span style="color:#778">${k}</span>: ${v===null?'—':v}</div>`).join('');
  const rel = aristas.filter(a=>a.source.key===d.key||a.target.key===d.key).slice(0,25).map(a=>{
    const sale = a.source.key===d.key, otro = sale ? a.target : a.source;
    return `<div>${sale?'→':'←'} <code>${a.tipo}</code> ${otro.nombre}</div>`; }).join('');
  document.getElementById('ficha').innerHTML =
    `<b class="t" style="color:${COL[d.tipo]}">${NOM[d.tipo]||d.tipo}</b><div style="font-weight:600;font-size:14px">${d.nombre}</div>${props}<hr style="border:0;border-top:1px solid #eee">${rel}`;
}
</script></body></html>
"""


def html_grafo(sub: dict, *, alto: int = 560, centro: str | None = None,
               dist: dict | None = None, resalte: dict | None = None) -> str:
    """Pagina HTML del subgrafo.

    centro:  key del nodo a marcar con borde negro.
    dist:    {key: saltos}; los nodos fuera del dict se atenuan.
    resalte: {"s|TIPO|d": "hl" | "ok" | "no"}; colorea esas aristas y atenua el resto.
    """
    datos = {**sub, "centro": centro, "dist": dist, "resalte": resalte or {}}
    # "</" dentro de un <script> cerraria la etiqueta antes de tiempo.
    js = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    return (_PLANTILLA.replace("__DATOS__", js)
            .replace("__COLORES__", json.dumps(COLORES))
            .replace("__NOMBRES__", json.dumps(NOMBRES, ensure_ascii=False))
            .replace("__ALTO__", str(alto)))


def resalte_todo(sub: dict, clase: str = "hl") -> dict:
    """Marca todas las aristas del subgrafo con una clase."""
    return {f"{a['s']}|{a['tipo']}|{a['d']}": clase for a in sub["aristas"]}
