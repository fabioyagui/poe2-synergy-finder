/* v0.17: local tree map and detailed PoB Calcs. No external scripts or telemetry. */
'use strict';
const Workbench = (() => {
  const el = id => document.getElementById(id);
  const h = x => esc(x);
  const arr = x => Array.isArray(x) ? x : [];
  const plain = x => String(x ?? '').replace(/\^x[0-9a-fA-F]{6}|\^[0-9]/g, '');
  const norm = x => plain(x).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const number = v => v == null ? '—' : typeof v === 'number' ? v.toLocaleString('pt-BR',{maximumFractionDigits:4}) : String(v);
  const signed = v => v == null ? 'não comparável' : (v > 0 ? '+' : '') + number(v);
  const failure = text => `<div class="wb-notice error" role="alert">${h(text)}</div>`;
  const titles = {Normal:'Passiva', Notable:'Notable', Keystone:'Keystone', Socket:'Jewel socket', ClassStart:'Início de classe', AscendClassStart:'Início de ascendência', OnlyImage:'Decoração'};
  let generation = 0, mapTicket = 0, calcTicket = 0, raf = 0, resizeObserver = null;
  const map = {data:null,byId:new Map(),zone:'base',query:'',filter:'all',side:'point',selected:null,hover:null,plan:null,error:'',result:null,
    suggestions:null,metric:'Life',budget:2,suggestQuery:'',busy:false,group:null,effect:null,marks:[],scale:0.08,tx:0,ty:0,w:800,height:600,page:0};
  const cal = {data:null,busy:false,error:'',query:'',detail:null,pinned:null,group:null,effect:null,actor:'player',buff:'EFFECTIVE'};
  const inMap = () => buildTab === 'tree-map' && !el('buildWorkspace').hidden;
  const inCalcs = () => buildTab === 'calcs' && !el('buildWorkspace').hidden;
  async function request(path, body={}) {
    const controller = new AbortController(), timer=setTimeout(()=>controller.abort(),235000);
    try {
      const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Local-App':'poe2-explorer'},body:JSON.stringify(body),signal:controller.signal});
      const data=await r.json();if(!r.ok)throw new Error(data.error || `HTTP ${r.status}`);return data;
    }catch(e){if(e.name==='AbortError')throw new Error('O motor não respondeu no prazo. Aguarde a janela do programa antes de iniciar outro cálculo.');throw e;}
    finally{clearTimeout(timer);}
  }
  function invalidate(){generation++;mapTicket++;calcTicket++;map.data=null;map.byId=new Map();map.plan=null;map.result=null;map.suggestions=null;map.selected=null;map.busy=false;cal.data=null;cal.pinned=null;cal.busy=false;cal.detail=null;resizeObserver?.disconnect();}
  function onlyCurrent(ticket,kind,g){return g===generation && ticket===(kind==='map'?mapTicket:calcTicket);}
  function groupOptions(groups,value){return arr(groups).filter(x=>x.enabled).map(g=>`<option value="${g.index}" ${Number(g.index)===Number(value)?'selected':''}>${h(g.label || g.effects?.[0]?.name || 'Grupo '+g.index)}</option>`).join('');}
  function effectsFor(groups,group){return arr(arr(groups).find(g=>Number(g.index)===Number(group))?.effects);}
  function effectOptions(groups,group,active){return effectsFor(groups,group).map(e=>`<option value="${e.index}" ${Number(e.index)===Number(active)?'selected':''}>${h(e.name)}</option>`).join('');}
  function firstGroup(groups,selected){return arr(groups).find(g=>g.enabled&&Number(g.index)===Number(selected)) || arr(groups).find(g=>g.enabled&&arr(g.effects).length);}
  function pickMapSkill(){const g=firstGroup(map.data.groups,map.group || map.data.selected_group);map.group=g?.index;map.effect=effectsFor(map.data.groups,map.group).find(e=>Number(e.index)===Number(map.effect))?.index || g?.active_index || g?.effects?.[0]?.index;}
  function readMarks(){try{map.marks=arr(JSON.parse(localStorage.getItem('sf-marks-'+map.data.build_hash)||'[]')).filter(id=>map.byId.has(id)).slice(0,12);}catch{map.marks=[];}}
  function markNode(){if(map.selected==null)return;const i=map.marks.indexOf(map.selected);if(i>=0)map.marks.splice(i,1);else if(map.marks.length<12)map.marks.push(map.selected);else{notify('Máximo de 12 marcadores por build.',true);return;}
    try{localStorage.setItem('sf-marks-'+map.data.build_hash,JSON.stringify(map.marks));}catch{}renderSide();drawSoon();}
  function nodeMatches(n){
    const filter=map.filter;
    if(filter==='allocated'&&!n.allocated)return false;
    if(filter==='near'&&(n.allocated||n.path_distance==null||n.path_distance>2))return false;
    if(filter==='notable'&&n.kind!=='Notable'&&n.kind!=='Keystone')return false;
    if(filter==='marked'&&!map.marks.includes(n.id))return false;
    const q=norm(map.query).trim();if(!q)return true;
    const alias={vida:'life',area:'area',forca:'strength',destreza:'dexterity',inteligencia:'intelligence',duracao:'duration',armadura:'armour',resistencia:'resist',incendiar:'ignite'};
    const term=alias[q]||q;return norm([n.name,n.id,...arr(n.stats)].join(' ')).includes(term);
  }
  function visibleNode(n){if(!Number.isFinite(n.x)||!Number.isFinite(n.y))return false;
    if(map.zone==='base')return !n.ascendancy;
    if(map.zone==='asc')return Boolean(n.ascendancy) && (n.ascendancy===map.data.ascendancy_name || !map.data.ascendancy_name);
    return true;
  }
  function shownNodes(){return arr(map.data?.nodes).filter(visibleNode);}
  function matches(){return shownNodes().filter(nodeMatches).filter(n=>n.kind!=='OnlyImage').sort((a,b)=>(a.path_distance??9999)-(b.path_distance??9999)||a.id-b.id);}
  function fit(nodes){if(!map.data)return;const ns=arr(nodes).filter(n=>Number.isFinite(n.x)&&Number.isFinite(n.y));if(!ns.length)return;
    const xs=ns.map(n=>n.x),ys=ns.map(n=>n.y),minx=Math.min(...xs)-150,maxx=Math.max(...xs)+150,miny=Math.min(...ys)-150,maxy=Math.max(...ys)+150;
    map.scale=Math.max(.006,Math.min(1.8,Math.min(map.w/(maxx-minx),map.height/(maxy-miny))*.87));map.tx=map.w/2-(minx+maxx)/2*map.scale;map.ty=map.height/2-(miny+maxy)/2*map.scale;drawSoon();}
  function focusNode(n){if(!n)return;if(n.ascendancy && map.zone==='base')map.zone=n.ascendancy===map.data.ascendancy_name?'asc':'all';if(!n.ascendancy&&map.zone==='asc')map.zone='base';
    if(el('wbZone'))el('wbZone').value=map.zone;map.scale=Math.max(map.scale,.6);map.tx=map.w/2-n.x*map.scale;map.ty=map.height/2-n.y*map.scale;drawSoon();}
  function zoom(factor,px=map.w/2,py=map.height/2){const s=Math.max(.006,Math.min(5,map.scale*factor));const k=s/map.scale;map.tx=px-(px-map.tx)*k;map.ty=py-(py-map.ty)*k;map.scale=s;drawSoon();}
  function canvasSize(){const c=el('wbTreeCanvas');if(!c)return;const box=c.getBoundingClientRect(),dpr=Math.min(window.devicePixelRatio||1,2);
    const oldW=map.w,oldH=map.height;map.w=Math.max(1,box.width);map.height=Math.max(1,box.height);
    if(oldW!==map.w||oldH!==map.height){map.tx+=(map.w-oldW)/2;map.ty+=(map.height-oldH)/2;}
    c.width=Math.round(map.w*dpr);c.height=Math.round(map.height*dpr);drawSoon();}
  function worldPoint(event){const rect=el('wbTreeCanvas').getBoundingClientRect();return {px:event.clientX-rect.left,py:event.clientY-rect.top};}
  function closest(px,py){let found=null,best=Infinity;for(const n of shownNodes()){if(n.kind==='OnlyImage')continue;
    const x=n.x*map.scale+map.tx,y=n.y*map.scale+map.ty,d=(px-x)**2+(py-y)**2;const r=Math.max(7,Math.min(45,nodeRadius(n)*map.scale+3));if(d<r*r&&d<best){found=n;best=d;}}
    return found;
  }
  const nodeRadius=n=>({Keystone:42,Notable:29,Socket:32,ClassStart:42,AscendClassStart:38}[n.kind]||18);
  function drawSoon(){if(!raf)raf=requestAnimationFrame(()=>{raf=0;if(inMap())draw();});}
  function draw(){
    const canvas=el('wbTreeCanvas');if(!canvas||!map.data)return;const ctx=canvas.getContext('2d'),dpr=Math.min(window.devicePixelRatio||1,2);
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,map.w,map.height);
    // Subtle rings keep the radial layout legible; no fictitious nodes/connections.
    ctx.fillStyle='#0c121a';ctx.fillRect(0,0,map.w,map.height);
    const adding=new Set(arr(map.plan?.add_ids)),removing=new Set(arr(map.plan?.remove_ids)),planned=new Set([...adding,...removing]);
    const results=new Set((map.query||map.filter!=='all')?matches().map(n=>n.id):[]);
    const left=-map.tx/map.scale,right=(map.w-map.tx)/map.scale,top=-map.ty/map.scale,bottom=(map.height-map.ty)/map.scale;
    const onScreen=n=>n.x>left-500&&n.x<right+500&&n.y>top-500&&n.y<bottom+500;
    ctx.save();ctx.translate(map.tx,map.ty);ctx.scale(map.scale,map.scale);ctx.lineCap='round';
    const ns=shownNodes();
    for(const e of arr(map.data.edges)){
      const a=map.byId.get(e.a),b=map.byId.get(e.b);if(!a||!b||!visibleNode(a)||!visibleNode(b))continue;
      if(!onScreen(a)&&!onScreen(b)&&!e.radius && ((a.x<left&&b.x<left)||(a.x>right&&b.x>right)||(a.y<top&&b.y<top)||(a.y>bottom&&b.y>bottom)))continue;
      const inPlan=(planned.has(a.id)&&(planned.has(b.id)||b.allocated))||(planned.has(b.id)&&a.allocated);
      const active=a.allocated&&b.allocated;
      ctx.strokeStyle=inPlan?(map.plan.action==='remove'?'#ed8c82':'#65d6ce'):active?'#bc9755':'#303c48';
      ctx.lineWidth=(inPlan?2.4:active?1.9:1)/map.scale;
      ctx.setLineDash(inPlan?[6/map.scale,3/map.scale]:[]);ctx.beginPath();
      if(Number.isFinite(e.cx)&&e.radius>0){const a1=Math.atan2(a.y-e.cy,a.x-e.cx),a2=Math.atan2(b.y-e.cy,b.x-e.cx);let diff=(a2-a1+Math.PI*3)%(Math.PI*2)-Math.PI;ctx.arc(e.cx,e.cy,e.radius,a1,a1+diff,diff<0);}
      else{ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);}ctx.stroke();
    }ctx.setLineDash([]);
    for(const n of ns){if(!onScreen(n)||n.kind==='OnlyImage')continue;
      const selected=map.selected===n.id,hover=map.hover===n.id,match=results.has(n.id),mark=map.marks.indexOf(n.id),pending=planned.has(n.id);
      const r=Math.max(nodeRadius(n), (n.allocated||match||pending?2.8:1.7)/map.scale);
      if(match||selected||hover||pending){ctx.beginPath();ctx.arc(n.x,n.y,r+4/map.scale,0,Math.PI*2);ctx.strokeStyle=selected?'#f2e6bd':pending?(map.plan.action==='remove'?'#ed8c82':'#65d6ce'):'#9e9deb';ctx.lineWidth=(selected?2:1.6)/map.scale;ctx.stroke();}
      ctx.beginPath();ctx.arc(n.x,n.y,r,0,Math.PI*2);ctx.fillStyle=n.allocated?'#675333':'#121d29';ctx.fill();
      ctx.strokeStyle=pending?(map.plan.action==='remove'?'#ed8c82':'#65d6ce'):n.allocation_mode===1&&n.allocated?'#6aa6ef':n.allocation_mode===2&&n.allocated?'#d17ee1':n.allocated?'#e7bd72':n.kind==='Keystone'?'#8e79ac':n.kind==='Notable'?'#8b7857':'#50616c';ctx.lineWidth=(n.allocated||selected?2:1)/map.scale;ctx.stroke();
      if(r*map.scale>6){ctx.fillStyle=n.allocated?'#f6deab':'#9cadbc';ctx.textAlign='center';ctx.textBaseline='middle';ctx.font=`${Math.max(8,Math.min(18,r*map.scale*.65))/map.scale}px system-ui`;
        ctx.fillText(n.kind==='Keystone'?'K':n.kind==='Notable'?'◆':n.kind==='Socket'?'◇':n.kind.includes('Start')?'✦':'·',n.x,n.y);}
      if(mark>=0){ctx.fillStyle='#78c4dc';ctx.textAlign='center';ctx.font=`bold ${11/map.scale}px system-ui`;ctx.fillText(String(mark+1),n.x+(r+7/map.scale),n.y-r-5/map.scale);}
      if(selected||((n.kind==='Notable'||n.kind==='Keystone')&&map.scale>.28)){
        ctx.font=`${selected?'600 ':''}${12/map.scale}px system-ui`;ctx.textAlign='center';ctx.textBaseline='top';ctx.lineWidth=4/map.scale;ctx.strokeStyle='#0c121a';ctx.strokeText(plain(n.name),n.x,n.y+r+6/map.scale);ctx.fillStyle=selected?'#f1dfb6':'#c2c7c9';ctx.fillText(plain(n.name),n.x,n.y+r+6/map.scale);
      }
    }ctx.restore();
    if(el('wbZoom'))el('wbZoom').textContent=Math.round(map.scale*100)+'%';
    if(el('wbMatchCount'))el('wbMatchCount').textContent=(map.query||map.filter!=='all')?matches().length+' encontrados':ns.filter(n=>n.kind!=='OnlyImage').length+' nós visíveis';
    drawMini(ns);
  }
  function drawMini(ns){const c=el('wbMinimap');if(!c||!ns.length)return;const ctx=c.getContext('2d'),w=c.width=190,hh=c.height=120;
    const xs=ns.map(n=>n.x),ys=ns.map(n=>n.y),minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys);
    const s=Math.min((w-12)/(maxx-minx||1),(hh-12)/(maxy-miny||1)),ox=(w-(maxx-minx)*s)/2,oy=(hh-(maxy-miny)*s)/2;
    c._world={s,ox,oy,minx,miny};ctx.fillStyle='#0b131d';ctx.fillRect(0,0,w,hh);
    for(const n of ns){ctx.fillStyle=n.allocated?'#d3af69':'#3e4c58';ctx.fillRect(ox+(n.x-minx)*s,oy+(n.y-miny)*s,n.allocated?2:1,n.allocated?2:1);}
    ctx.strokeStyle='#67c4c6';ctx.lineWidth=1;ctx.strokeRect(ox+(-map.tx/map.scale-minx)*s,oy+(-map.ty/map.scale-miny)*s,map.w/map.scale*s,map.height/map.scale*s);
  }
  function tooltip(n,px,py){const tip=el('wbHover');if(!tip)return;tip.hidden=!n;if(!n)return;
    tip.innerHTML=`<strong>${h(plain(n.name))}</strong><small>${h(titles[n.kind]||n.kind)} · #${n.id}${n.allocated?' · alocado':''}</small>${arr(n.stats).slice(0,6).map(t=>`<p>${h(plain(t))}</p>`).join('')}${n.unparsed?'<small>Há texto não interpretado pelo PoB.</small>':''}`;
    tip.style.left=Math.min(px+20,Math.max(0,map.w-280))+'px';tip.style.top=Math.max(8,Math.min(py+15,map.height-tip.offsetHeight-12))+'px';
  }
  function bindCanvas(){const c=el('wbTreeCanvas');if(!c)return;let drag=null;
    c.addEventListener('pointerdown',e=>{if(e.button!==0)return;const p=worldPoint(e);drag={...p,tx:map.tx,ty:map.ty,id:e.pointerId,moved:false};c.setPointerCapture(e.pointerId);c.focus();});
    c.addEventListener('pointermove',e=>{const p=worldPoint(e);if(drag){const dx=p.px-drag.px,dy=p.py-drag.py;if(dx*dx+dy*dy>16)drag.moved=true;if(drag.moved){map.tx=drag.tx+dx;map.ty=drag.ty+dy;map.hover=null;tooltip(null);drawSoon();}return;}
      const n=closest(p.px,p.py);if(map.hover!==n?.id){map.hover=n?.id;drawSoon();}tooltip(n,p.px,p.py);});
    c.addEventListener('pointerup',e=>{if(!drag)return;const d=drag;drag=null;if(c.hasPointerCapture(e.pointerId))c.releasePointerCapture(e.pointerId);if(!d.moved){const p=worldPoint(e),n=closest(p.px,p.py);if(n)choose(n.id);}});
    c.addEventListener('pointercancel',()=>drag=null);c.addEventListener('pointerleave',()=>{if(!drag){map.hover=null;tooltip(null);drawSoon();}});
    c.addEventListener('wheel',e=>{e.preventDefault();const p=worldPoint(e);zoom(Math.exp(-e.deltaY*.0016),p.px,p.py);},{passive:false});
    c.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='='){e.preventDefault();zoom(1.25);}if(e.key==='-'){e.preventDefault();zoom(.8);}if(e.key==='Escape'){map.hover=null;tooltip(null);}if(e.key==='/'){e.preventDefault();el('wbSearch').focus();}
      const dirs={ArrowLeft:[70,0],ArrowRight:[-70,0],ArrowUp:[0,70],ArrowDown:[0,-70]};if(dirs[e.key]){e.preventDefault();map.tx+=dirs[e.key][0];map.ty+=dirs[e.key][1];drawSoon();}});
    el('wbMinimap').addEventListener('click',e=>{const v=e.currentTarget._world;if(!v)return;const r=e.currentTarget.getBoundingClientRect();const x=(e.clientX-r.left)*190/r.width,y=(e.clientY-r.top)*120/r.height;
      map.tx=map.w/2-(v.minx+(x-v.ox)/v.s)*map.scale;map.ty=map.height/2-(v.miny+(y-v.oy)/v.s)*map.scale;drawSoon();});
    resizeObserver?.disconnect();resizeObserver=new ResizeObserver(canvasSize);resizeObserver.observe(c);canvasSize();
  }
  function mapShell(){const d=map.data;
    el('buildContent').innerHTML=`<section class="wb-page wb-map-page" id="wbMapPage"><div class="wb-heading"><div><span class="eyebrow">ÁRVORE DO POB · PRÉVIA, SEM GASTAR PONTOS</span><h2>Explore o próximo ponto.</h2><p>Layout real da árvore carregada. Clique para inspecionar; compare antes de decidir.</p></div><div class="wb-heading-actions"><button class="secondary" data-build-tab-jump="tree">Lista de pontos</button><button class="secondary" id="wbMapReload">Recarregar árvore</button></div></div>
      <div id="wbMapStatus" class="wb-notice" role="status">${d?`PoB ${h(d.engine_version||'—')} · árvore ${h(d.tree_version)} · ${number(d.counts?.ordinary)} pontos comuns · ${number(d.counts?.ascendancy)} de ascendência`:'Lendo coordenadas e conexões do PoB…'}</div>
      <div class="wb-map-controls"><label class="wb-search-label"><span class="sr-only">Localizar passiva</span><input id="wbSearch" placeholder="Localizar: nome, ID, vida, Area, Ignite…" value="${h(map.query)}"></label><select id="wbFindFilter" aria-label="Filtro de pontos"><option value="all">Todos os pontos</option><option value="allocated">Alocados</option><option value="near">Próximos · até 2 pontos</option><option value="notable">Notables e Keystones</option><option value="marked">Meus marcadores</option></select><select id="wbZone" aria-label="Região da árvore"><option value="base">Árvore base</option><option value="asc">Minha ascendência</option><option value="all">Tudo</option></select><button id="wbFitBuild" class="secondary">Centralizar build</button><button id="wbFitAll" class="secondary">Visão geral</button></div>
      <div class="wb-map-layout"><div class="wb-canvas-wrap"><canvas id="wbTreeCanvas" tabindex="0" aria-label="Árvore passiva interativa. Arraste para mover, roda para ampliar. Use a busca e a lista para selecionar pontos por teclado."></canvas><div class="wb-map-hud"><button id="wbMinus" aria-label="Diminuir zoom">−</button><span id="wbZoom">—</span><button id="wbPlus" aria-label="Aumentar zoom">+</button><button id="wbFullscreen">Tela cheia</button></div><div class="wb-map-legend"><span class="allocated">Alocado</span><span class="proposal">Prévia</span><span class="match">Busca</span><span class="set1">Set 1</span><span class="set2">Set 2</span></div><div class="wb-map-bottom"><span id="wbMatchCount"></span><span>Arraste · roda = zoom · / = buscar</span></div><canvas id="wbMinimap" aria-label="Minimapa: clique para mover a visualização"></canvas><div id="wbHover" class="wb-tooltip" hidden></div></div><aside class="wb-map-side"><div class="wb-side-tabs"><button data-wb-side="point">Ponto</button><button data-wb-side="locate">Localizar</button><button data-wb-side="suggest">Sugestões</button></div><div id="wbSideBody"></div></aside></div><div id="wbMapResult"></div><p class="wb-footnote">Representação vetorial com posições e conexões do PoB; não inclui as texturas/artes do jogo. A prévia não modifica a build salva. Orçamento de pontos não confirmado.</p></section>`;
    el('wbFindFilter').value=map.filter;el('wbZone').value=map.zone;bindCanvas();renderSide();renderMapResult();
  }
  function planHtml(){const n=map.byId.get(map.selected);if(!n)return `<div class="wb-side-empty"><span class="wb-node-glyph">◇</span><h3>Um ponto, seu efeito e o caminho.</h3><p>Clique em qualquer passiva da árvore ou use Localizar. O mapa destaca o que entraria ou sairia no teste.</p>${marksHtml()}</div>`;
    const p=map.plan;return `<div class="wb-node-title"><span class="eyebrow">${h(titles[n.kind]||n.kind)} · #${n.id}</span><h3>${h(plain(n.name))}</h3><span class="wb-pill">${n.allocated?'Alocado':'Não alocado'}${n.allocation_mode?' · weapon set '+n.allocation_mode:''}</span></div><div class="wb-node-stats">${arr(n.stats).map(s=>`<p>${h(plain(s))}</p>`).join('')}</div><div class="wb-side-buttons"><button class="secondary" id="wbMark">${map.marks.includes(n.id)?'Remover marcador':'Marcar local'}</button><button class="secondary" id="wbFocus">Centralizar</button></div>${n.unparsed?failure('O PoB não interpreta totalmente o texto deste ponto.'):''}${map.error?failure(map.error):''}${!n.editable?`<div class="wb-notice">Somente consulta: ${h(n.blocked_reason||'Tipo especial ainda não editável.')}</div>`:''}${map.busy?'<div class="wb-notice" role="status">Motor PoB trabalhando…</div>':''}
      ${p?`<div class="wb-plan"><span class="eyebrow">PRÉVIA ${p.action==='add'?'DE ALOCAÇÃO':'DE REMOÇÃO'}</span><h4>${signed(p.total_delta)} ponto(s)</h4><p>${p.action==='add'?'O caminho inclui':'Também sairiam'} ${arr(p.changes).length} nós. Nenhum ponto foi gasto.</p><ol>${arr(p.changes).map(x=>`<li><button data-wb-focus="${x.id}">${h(plain(x.name))}</button></li>`).join('')}</ol><div class="wb-notice">Pontos disponíveis e limites de ascendência não verificados.</div><label>Skill para medir<select id="wbMapGroup" ${map.busy?'disabled':''}>${groupOptions(map.data.groups,map.group)}</select></label><label>Efeito<select id="wbMapEffect" ${map.busy?'disabled':''}>${effectOptions(map.data.groups,map.group,map.effect)}</select></label><button id="wbCompare" class="primary wb-full" ${map.busy||!map.group?'disabled':''}>Comparar alteração no PoB</button></div>`:''}${marksHtml()}`;
  }
  function marksHtml(){return map.marks.length?`<div class="wb-bookmarks"><span class="eyebrow">MEUS MARCADORES · ESTA BUILD</span>${map.marks.map((id,i)=>`<button data-wb-select="${id}">${i+1}. ${h(plain(map.byId.get(id)?.name||id))}</button>`).join('')}</div>`:'';}
  function locateHtml(){const rows=matches(),per=35;map.page=Math.min(map.page,Math.max(0,Math.ceil(rows.length/per)-1));return `<div class="wb-locator"><h3>${rows.length} pontos encontrados</h3><div class="wb-chips">${[['Life','Vida'],['Area','Área'],['Ignite','Ignite'],['Mana','Mana'],['Cooldown','Cooldown']].map(([q,t])=>`<button data-wb-query="${q}">${t}</button>`).join('')}<button data-wb-query="">Limpar</button></div><p>A busca destaca os nós no mapa. Clique num resultado para chegar até ele.</p><div class="wb-find-list">${rows.slice(map.page*per,(map.page+1)*per).map(n=>`<button data-wb-select="${n.id}"><strong>${h(plain(n.name))}</strong><small>${h(titles[n.kind]||n.kind)} · #${n.id} · ${n.allocated?'alocado':n.path_distance!=null?n.path_distance+' ponto(s) de distância':'sem caminho informado'}</small><span>${h(plain(arr(n.stats)[0]||''))}</span></button>`).join('')||'<p>Nenhum ponto nesta região. Tente “Tudo” no seletor da árvore.</p>'}</div><div class="wb-page-controls"><button id="wbFindPrev" ${map.page===0?'disabled':''}>←</button><span>${map.page+1} / ${Math.max(1,Math.ceil(rows.length/per))}</span><button id="wbFindNext" ${(map.page+1)*per>=rows.length?'disabled':''}>→</button></div>${marksHtml()}</div>`;}
  function suggestionHtml(){const d=map.suggestions;return `<div class="wb-suggestions"><span class="eyebrow">AVALIAÇÃO POR OBJETIVO</span><h3>Onde vale investigar?</h3><p>Compara até 12 caminhos próximos usando o PoB. Não é um ranking da árvore inteira.</p><label>Objetivo<select id="wbObjective" ${map.busy?'disabled':''}>${[['Life','Mais vida'],['EnergyShield','Mais ES'],['CombinedDPS','Mais DPS combinado'],['IgniteDPS','Mais DPS de Ignite'],['AreaOfEffectMod','Mais área'],['Duration','Mais duração'],['Cooldown','Menor cooldown'],['ManaCost','Menor custo de mana'],['ManaRegen','Mais regeneração de mana'],['Armour','Mais armadura']].map(([v,t])=>`<option value="${v}" ${map.metric===v?'selected':''}>${t}</option>`).join('')}</select></label><label>Até quantos pontos por caminho?<select id="wbBudget" ${map.busy?'disabled':''}>${[1,2,3,4,5].map(n=>`<option ${Number(map.budget)===n?'selected':''}>${n}</option>`).join('')}</select></label><label>Restringir por texto do nó<input id="wbSuggestQuery" placeholder="Opcional: Area, Ignite, Life…" maxlength="100" value="${h(map.suggestQuery)}" ${map.busy?'disabled':''}></label><label>Skill<select id="wbMapGroup" ${map.busy?'disabled':''}>${groupOptions(map.data.groups,map.group)}</select></label><label>Efeito<select id="wbMapEffect" ${map.busy?'disabled':''}>${effectOptions(map.data.groups,map.group,map.effect)}</select></label><button id="wbEvaluate" class="primary wb-full" ${map.busy?'disabled':''}>${map.busy?'PoB avaliando caminhos…':'Avaliar caminhos próximos'}</button>${map.error?failure(map.error):''}
      ${d?`<div class="wb-suggest-results"><h4>${d.evaluated} de ${d.eligible} caminhos elegíveis avaliados</h4><p>Ordem: menor custo, depois ID. Ganho por ponto classifica apenas este conjunto; não garante a melhor build.</p>${arr(d.rows).slice(0,12).map((r,i)=>`<button data-wb-suggestion="${i}" class="wb-suggest-card"><strong>${h(plain(r.plan?.target?.name||r.node_id))}</strong><span>${number(r.before)} → ${number(r.after)} <b>${signed(r.delta)}</b></span><small>${r.plan.total_delta} ponto(s) · ${signed(r.per_point)} por ponto</small></button>`).join('')||'<p>Nenhum resultado calculável com estes filtros.</p>'}<p>${arr(d.errors).length} caminho(s) sem cálculo. Controle A/A consistente; orçamento não confirmado.</p></div>`:''}</div>`;}
  function renderSide(){if(!inMap()||!el('wbSideBody')||!map.data)return;document.querySelectorAll('[data-wb-side]').forEach(b=>b.classList.toggle('active',b.dataset.wbSide===map.side));el('wbSideBody').innerHTML=map.side==='point'?planHtml():map.side==='locate'?locateHtml():suggestionHtml();}
  function metricsTable(rows){return `<div class="wb-table-scroll"><table class="wb-table"><thead><tr><th>Métrica</th><th>Atual</th><th>Prévia</th><th>Diferença</th></tr></thead><tbody>${rows.map(r=>`<tr><th>${h(r.label||r.key)}<small>${h(r.key)}</small></th><td>${h(number(r.before))}</td><td>${h(number(r.after))}</td><td>${h(signed(r.delta))}${r.pct!=null?`<small>${h(signed(r.pct))}%</small>`:''}</td></tr>`).join('')}</tbody></table></div>`;}
  function renderMapResult(){const box=el('wbMapResult');if(!box)return;const r=map.result;if(!r){box.innerHTML='';return;}const changed=arr(r.metrics).filter(x=>x.changed),same=arr(r.metrics).filter(x=>!x.changed);
    box.innerHTML=`<section class="wb-comparison"><div class="wb-heading"><div><span class="eyebrow">PRÉVIA NO POB · NÃO APLICADA</span><h3>${h(plain(r.plan?.target?.name||''))}</h3><p>${h(r.skill?.name||'Skill selecionada')} · ${signed(r.plan?.total_delta)} ponto(s)</p></div><button id="wbTreeReport" class="secondary">Baixar relatório JSON</button></div><div class="wb-notice ${r.numeric_check_passed?'ok':'error'}">${r.numeric_check_passed?'Controle sem alterações A/A consistente.':'O controle sem alterações divergiu: não use os números para decidir.'} ${r.original_restored?'Build original restaurada.':''}</div>${changed.length?metricsTable(changed):'<p>Nenhum valor exportado mudou. Isso não confirma ausência de efeito no jogo.</p>'}<details><summary>Métricas sem mudança (${same.length})</summary>${metricsTable(same)}</details><p class="wb-footnote">Uma variação positiva não é automaticamente melhor. O teste não valida pontos disponíveis, preço de respec ou todas as mecânicas do jogo.</p></section>`;
  }
  async function openMap(focusId){
    const ticket=++mapTicket,g=generation;map.busy=true;map.error='';map.plan=null;map.result=null;
    if(inMap())el('buildContent').innerHTML='<div class="wb-notice">Lendo a árvore do seu PoB… sem baixar outra cópia.</div>';
    try{const d=await request('/api/workbench/visual');if(!onlyCurrent(ticket,'map',g))return;map.data=d;map.byId=new Map(arr(d.nodes).map(n=>[Number(n.id),n]));pickMapSkill();readMarks();map.busy=false;
      if(inMap()){mapShell();const allocated=shownNodes().filter(n=>n.allocated);fit(allocated.length?allocated:shownNodes());if(focusId){focusNode(map.byId.get(Number(focusId)));choose(Number(focusId));}}
    }catch(e){if(onlyCurrent(ticket,'map',g)&&inMap())el('buildContent').innerHTML=failure(e.message)+'<button class="secondary" data-build-tab-jump="engine">Abrir Motor PoB</button>';}
    finally{if(onlyCurrent(ticket,'map',g))map.busy=false;}
  }
  async function choose(id){if(!map.data||map.busy)return;const n=map.byId.get(Number(id));if(!n)return;
    map.selected=n.id;map.side='point';map.error='';map.plan=null;map.result=null;map.busy=!!n.editable;renderSide();renderMapResult();drawSoon();if(!n.editable)return;
    const ticket=++mapTicket,g=generation;
    try{const d=await request('/api/tree-sim/preview',{node_id:n.id,mode:'path',build_hash:map.data.build_hash});if(onlyCurrent(ticket,'map',g))map.plan=d;}
    catch(e){if(onlyCurrent(ticket,'map',g))map.error=e.message;}
    finally{if(onlyCurrent(ticket,'map',g)){map.busy=false;renderSide();drawSoon();}}
  }
  async function compareNode(){if(map.busy||!map.plan)return;const ticket=++mapTicket,g=generation;map.busy=true;map.error='';renderSide();
    try{const d=await request('/api/tree-sim/compare',{node_id:map.selected,mode:'path',build_hash:map.data.build_hash,fingerprint:map.plan.fingerprint,group_index:Number(map.group),active_index:Number(map.effect)});if(onlyCurrent(ticket,'map',g))map.result=d;}
    catch(e){if(onlyCurrent(ticket,'map',g))map.error=e.message;}
    finally{if(onlyCurrent(ticket,'map',g)){map.busy=false;renderSide();renderMapResult();}}
  }
  async function evaluate(){if(map.busy||!map.data)return;const ticket=++mapTicket,g=generation;map.busy=true;map.error='';map.suggestions=null;renderSide();
    try{const d=await request('/api/workbench/suggestions',{build_hash:map.data.build_hash,fingerprint:map.data.fingerprint,group_index:Number(map.group),active_index:Number(map.effect),metric:map.metric,max_points:Number(map.budget),limit:12,query:map.suggestQuery});if(onlyCurrent(ticket,'map',g))map.suggestions=d;}
    catch(e){if(onlyCurrent(ticket,'map',g))map.error=e.message;}
    finally{if(onlyCurrent(ticket,'map',g)){map.busy=false;renderSide();}}
  }
  function showSuggestion(index){const r=map.suggestions?.rows?.[index];if(!r)return;map.selected=r.node_id;map.plan=r.plan;map.side='point';map.error='';map.result={...r,skill:map.suggestions.skill,original_restored:true,numeric_check_passed:map.suggestions.numeric_check_passed,build_hash:map.suggestions.build_hash};focusNode(map.byId.get(r.node_id));renderSide();renderMapResult();drawSoon();}
  // Detailed calculations: numbers, breakdowns and config from this PoB instance.
  function calcSignature(d){return JSON.stringify([d.build_hash,d.skill?.group_index,d.skill?.active_index,d.selection?.actor,d.selection?.buff_mode]);}
  function canComparePinned(){return cal.pinned && cal.data && calcSignature(cal.pinned)===calcSignature(cal.data);}
  function pinnedDifference(key,value){if(!canComparePinned())return '';const old=cal.pinned.output[key];if(typeof old!=='number'||typeof value!=='number')return '';
    return `<small class="wb-delta">referência ${number(old)} · Δ ${signed(value-old)}</small>`;
  }
  function calcToolbar(){const d=cal.data;return `<div class="wb-calc-controls"><label>Skill<select id="wbCalcGroup" ${cal.busy?'disabled':''}>${groupOptions(d.groups,cal.group)}</select></label><label>Efeito ativo<select id="wbCalcEffect" ${cal.busy?'disabled':''}>${effectOptions(d.groups,cal.group,cal.effect)}</select></label><label>Condições do cálculo<select id="wbCalcBuff" ${cal.busy?'disabled':''}>${[['UNBUFFED','Sem buffs'],['BUFFED','Com buffs'],['COMBAT','Em combate'],['EFFECTIVE','DPS efetivo']].map(([v,t])=>`<option value="${v}" ${cal.buff===v?'selected':''}>${t}</option>`).join('')}</select></label><label>Ator<select id="wbCalcActor" ${cal.busy?'disabled':''}><option value="player" ${cal.actor==='player'?'selected':''}>Personagem</option><option value="minion" ${cal.actor==='minion'?'selected':''} ${!d.selection?.minion_available?'disabled':''}>Minion</option></select></label></div>`;}
  function renderCalcCards(){const target=el('wbCalcCards');if(!target||!cal.data)return;const rows=arr(cal.data.metrics).filter(r=>!cal.query||norm([r.key,r.label,r.category].join(' ')).includes(norm(cal.query))),groups=new Map();
    for(const r of rows){if(!groups.has(r.category))groups.set(r.category,[]);groups.get(r.category).push(r);}
    target.innerHTML=Array.from(groups,([category,items])=>{const content=items.map(r=>`<button class="wb-stat-row ${cal.detail===r.key?'selected':''}" data-wb-metric="${h(r.key)}"><span>${h(r.label)}<small>${h(r.key)}</small></span><strong>${h(number(r.value))}${r.unit?`<em>${h(r.unit)}</em>`:''}${pinnedDifference(r.key,r.value)}</strong><i aria-hidden="true">${r.breakdown_available||r.modifiers_available?'↗':'·'}</i></button>`).join('');return category==='Outros outputs do PoB'?`<details class="wb-calc-category advanced" ${cal.query?'open':''}><summary>${h(category)} · ${items.length}</summary>${content}</details>`:`<section class="wb-calc-category"><h3>${h(category)}</h3>${content}</section>`;}).join('')||'<div class="wb-notice">Nenhuma métrica corresponde à busca.</div>';
    if(el('wbCalcCount'))el('wbCalcCount').textContent=rows.length+' / '+cal.data.metrics.length+' valores';
  }
  function anyEntries(v){if(!v||typeof v!=='object')return [];return Object.entries(v);}
  function arrayLike(v){if(Array.isArray(v))return v;if(v&&typeof v==='object')return Object.keys(v).filter(k=>/^\d+$/.test(k)).sort((a,b)=>a-b).map(k=>v[k]);return [];}
  function simpleValue(v){if(v==null)return '—';if(typeof v==='object')return JSON.stringify(v);return plain(number(v));}
  function sourceHtml(source){const text=plain(source||'');const id=text.match(/(?:^|\b)Tree:?(\d+)/i)?.[1];return id?`<button class="wb-source-link" data-wb-tree-source="${id}">${h(text)} ↗</button>`:h(text);}
  function breakdownHtml(bd){
    if(bd==null)return '<p>O PoB não publicou um detalhamento com esta chave. Isso não significa valor zero.</p>';
    if(typeof bd!=='object')return `<p>${h(plain(bd))}</p>`;
    const lines=arrayLike(bd).filter(v=>typeof v==='string'||typeof v==='number');let out=lines.length?`<div class="wb-formula">${lines.map(l=>`<p>${h(plain(l))}</p>`).join('')}</div>`:'';
    const rows=arrayLike(bd.rowList),cols=arrayLike(bd.colList);
    if(rows.length&&cols.length){out+=`<div class="wb-table-scroll"><table class="wb-table"><thead><tr>${cols.map(c=>`<th>${h(plain(c.label||c.key))}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${cols.map(c=>`<td>${c.key==='source'?sourceHtml(r[c.key]):h(simpleValue(r[c.key]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
    const other=anyEntries(bd).filter(([k,v])=>!/^\d+$/.test(k)&&!['rowList','colList'].includes(k)&&v!=null);
    if(other.length)out+=`<div class="wb-breakdown-fields">${other.map(([k,v])=>typeof v==='object'?`<details><summary>${h(k)}</summary><pre>${h(JSON.stringify(v,null,2))}</pre></details>`:`<p><b>${h(k)}</b> ${h(simpleValue(v))}</p>`).join('')}</div>`;
    return out || '<p>O PoB retornou um detalhamento vazio para este campo.</p>';
  }
  function renderCalcDetail(){const box=el('wbCalcDetail');if(!box||!cal.data)return;const key=cal.detail;if(!key){box.innerHTML='<div class="wb-side-empty"><span class="eyebrow">COMO CHEGOU A ESTE VALOR?</span><h3>Abra uma métrica.</h3><p>Clique em qualquer valor para ver o detalhamento que o PoB disponibilizou e as fontes de modificadores consultadas.</p><p>Fontes Tree:ID levam você diretamente ao ponto na árvore visual.</p></div>';return;}
    const d=cal.data,row=d.metrics.find(r=>r.key===key),bd=d.breakdowns?.[key],sources=arr(d.modifier_sources?.[key]);
    box.innerHTML=`<div class="wb-detail-title"><span class="eyebrow">DETALHAMENTO DO POB</span><h3>${h(row?.label||key)}</h3><code>${h(key)}</code><strong>${h(number(row?.value))} ${h(row?.unit||'')}</strong></div>${breakdownHtml(bd)}
      <h4>Fontes de modificadores</h4>${sources.length?`<div class="wb-table-scroll"><table class="wb-table"><thead><tr><th>Tipo / stat</th><th>Valor</th><th>Fonte</th></tr></thead><tbody>${sources.map(s=>`<tr><td>${h(s.type)}<small>${h(s.name)}</small></td><td>${h(number(s.value))}</td><td>${sourceHtml(s.source)}</td></tr>`).join('')}</tbody></table></div><p class="wb-footnote">Modificadores consultados no contexto atual. Não são, isoladamente, uma fórmula completa do resultado.</p>`:`<p>${d.modifier_sources_available?.[key]?'Nenhuma contribuição retornada para essa consulta.':'Esta métrica não possui consulta de fontes nesta interface.'}</p>`}
      <label>Outros detalhamentos do PoB<select id="wbBreakdownChoice"><option value="">Selecione uma chave…</option>${arr(d.breakdown_keys).map(k=>`<option value="${h(k)}" ${key===k?'selected':''}>${h(k)}</option>`).join('')}</select></label><details><summary>Dados brutos deste detalhamento</summary><pre>${h(JSON.stringify(bd??{},null,2))}</pre></details>`;
  }
  function renderCalcs(){if(!inCalcs())return;const d=cal.data;
    if(!d){el('buildContent').innerHTML=cal.error?failure(cal.error)+'<button class="secondary" data-build-tab-jump="engine">Abrir Motor PoB</button>':'<div class="wb-notice">PoB calculando a build atual…</div>';return;}
    el('buildContent').innerHTML=`<section class="wb-page wb-calcs-page"><div class="wb-heading"><div><span class="eyebrow">CÁLCULOS · BUILD IMPORTADA, NÃO A PRÉVIA DA ÁRVORE</span><h2>${h(plain(d.skill?.name||'Cálculos da build'))}</h2><p>Valores calculados agora pelo seu PoB, com o efeito e as condições abaixo.</p></div><div class="wb-heading-actions"><button class="secondary" id="wbPinCalc" ${cal.busy?'disabled':''}>Fixar referência</button><button class="primary" id="wbRefreshCalc" ${cal.busy?'disabled':''}>${cal.busy?'Recalculando…':'Recalcular'}</button><button class="secondary" id="wbCalcReport">Relatório JSON</button></div></div>
      <div class="wb-notice ${cal.error?'error':''}" role="status">${cal.error?h(cal.error):cal.busy?'PoB recalculando. Os valores anteriores permanecem visíveis até concluir.':`PoB ${h(d.engine_version||'versão não informada')} · árvore ${h(d.tree_version)} · ${h(d.source)} · original restaurada`}</div>
      ${calcToolbar()}<div class="wb-calc-search"><input id="wbCalcSearch" placeholder="Filtrar cálculos: vida, mana, dano, área, cooldown…" value="${h(cal.query)}" aria-label="Buscar métrica"><span id="wbCalcCount"></span></div>${cal.pinned?`<div class="wb-notice">${canComparePinned()?'Referência fixada para a mesma build, skill, ator e modo. Δ é uma comparação, não uma recomendação.':'A referência é de outra seleção. Fixe uma nova referência para comparar valores nas mesmas condições.'}</div>`:''}
      <div class="wb-calcs-layout"><div id="wbCalcCards" class="wb-calcs-grid"></div><aside id="wbCalcDetail" class="wb-calc-detail"></aside></div>
      <details class="wb-config"><summary>Condições e limitações desta leitura</summary><p>${h(d.accuracy_note)}</p><p>Supports presentes no efeito: ${arr(d.supports).map(x=>h(x)).join(', ')||'nenhum informado'}.</p><p>Dados de configuração importados; valores condicionais não são confirmação de uptime no jogo.</p><pre>${h(JSON.stringify(d.configuration||{},null,2))}</pre>${d.detail_truncated?failure('Parte do detalhamento foi limitada para evitar uma resposta excessivamente grande.'):''}</details></section>`;
    renderCalcCards();renderCalcDetail();
  }
  async function loadCalcs(first=false){if(cal.busy)return;const ticket=++calcTicket,g=generation;cal.busy=true;cal.error='';renderCalcs();
    const body=first?{}:{group_index:Number(cal.group),active_index:Number(cal.effect),actor:cal.actor,buff_mode:cal.buff,build_hash:cal.data?.build_hash};
    try{const d=await request('/api/workbench/calcs',body);if(!onlyCurrent(ticket,'calc',g))return;cal.data=d;cal.group=d.skill.group_index;cal.effect=d.skill.active_index;cal.actor=d.selection.actor;cal.buff=d.selection.buff_mode;}
    catch(e){if(onlyCurrent(ticket,'calc',g))cal.error=e.message;}
    finally{if(onlyCurrent(ticket,'calc',g)){cal.busy=false;renderCalcs();}}
  }
  async function openCalcs(){if(cal.data){renderCalcs();return;}await loadCalcs(true);}
  function download(data,name){if(!data)return;const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);}
  document.addEventListener('click',async e=>{
    const b=e.target.closest('button');if(!b)return;
    if(b.dataset.wbTreeSource){buildTab='tree-map';setAppMode('build');renderCurrentBuild(); // render uses current cached map if present
      const id=Number(b.dataset.wbTreeSource);if(map.data){focusNode(map.byId.get(id));choose(id);}else{pendingFocus=id;}return;}
    if(inCalcs()){
      if(b.id==='wbRefreshCalc'){loadCalcs();return;}
      if(b.id==='wbPinCalc'){if(cal.data&&!cal.busy){cal.pinned=JSON.parse(JSON.stringify(cal.data));renderCalcs();}return;}
      if(b.id==='wbCalcReport'){download(cal.data,'synergy-calcs.json');return;}
      if(b.dataset.wbMetric){cal.detail=b.dataset.wbMetric;renderCalcCards();renderCalcDetail();return;}
    }
    if(!inMap())return;
    if(b.dataset.wbSide){map.side=b.dataset.wbSide;renderSide();return;}
    if(b.dataset.wbFocus){focusNode(map.byId.get(Number(b.dataset.wbFocus)));return;}
    if(b.dataset.wbSelect){if(map.busy)return;const n=map.byId.get(Number(b.dataset.wbSelect));focusNode(n);choose(n?.id);return;}
    if(b.dataset.wbSuggestion!==undefined){if(!map.busy)showSuggestion(Number(b.dataset.wbSuggestion));return;}
    if(b.dataset.wbQuery!==undefined){map.query=b.dataset.wbQuery;el('wbSearch').value=map.query;map.side='locate';map.page=0;renderSide();drawSoon();return;}
    if(b.id==='wbPlus'){zoom(1.35);return;}if(b.id==='wbMinus'){zoom(1/1.35);return;}
    if(b.id==='wbFitBuild'){const allocated=shownNodes().filter(n=>n.allocated);fit(allocated.length?allocated:shownNodes());return;}
    if(b.id==='wbFitAll'){fit(shownNodes());return;}
    if(b.id==='wbMark'){markNode();return;}if(b.id==='wbFocus'){focusNode(map.byId.get(map.selected));return;}
    if(b.id==='wbFindPrev'){map.page=Math.max(0,map.page-1);renderSide();return;}if(b.id==='wbFindNext'){map.page++;renderSide();return;}
    if(b.id==='wbMapReload'){if(!map.busy){pendingFocus=null;openMap();}return;}
    if(b.id==='wbCompare'){compareNode();return;}if(b.id==='wbEvaluate'){evaluate();return;}
    if(b.id==='wbTreeReport'){download(map.result,'synergy-tree-visual.json');return;}
    if(b.id==='wbFullscreen'){try{if(document.fullscreenElement)await document.exitFullscreen();else await el('wbMapPage').requestFullscreen();}catch{notify('O navegador não permitiu tela cheia. O zoom da árvore continua disponível.',true);}return;}
  });
  document.addEventListener('input',e=>{
    if(e.target.id==='wbSearch'){map.query=e.target.value;map.side='locate';map.page=0;renderSide();drawSoon();}
    if(e.target.id==='wbSuggestQuery')map.suggestQuery=e.target.value;
    if(e.target.id==='wbCalcSearch'){cal.query=e.target.value;renderCalcCards();}
  });
  document.addEventListener('change',e=>{
    const id=e.target.id,value=e.target.value;
    if(id==='wbZone'){map.zone=value;fit(shownNodes());renderSide();return;}
    if(id==='wbFindFilter'){map.filter=value;map.page=0;map.side='locate';renderSide();drawSoon();return;}
    if(id==='wbObjective'){map.metric=value;map.suggestions=null;return;}if(id==='wbBudget'){map.budget=Number(value);map.suggestions=null;return;}
    if(id==='wbMapGroup'){map.group=Number(value);map.effect=effectsFor(map.data.groups,map.group)[0]?.index;map.result=null;renderSide();renderMapResult();return;}
    if(id==='wbMapEffect'){map.effect=Number(value);map.result=null;renderMapResult();return;}
    if(id==='wbBreakdownChoice'&&value){cal.detail=value;renderCalcDetail();return;}
    if(cal.busy)return;
    if(id==='wbCalcGroup'){cal.group=Number(value);cal.effect=effectsFor(cal.data.groups,cal.group)[0]?.index;cal.actor='player';loadCalcs();return;}
    if(id==='wbCalcEffect'){cal.effect=Number(value);loadCalcs();return;}
    if(id==='wbCalcBuff'){cal.buff=value;loadCalcs();return;}
    if(id==='wbCalcActor'){cal.actor=value;loadCalcs();return;}
  });
  let pendingFocus=null;
  async function mapOpen(){
    if(map.data){mapShell();drawSoon();return;}
    await openMap();if(pendingFocus!=null&&map.data&&inMap()){const id=pendingFocus;pendingFocus=null;focusNode(map.byId.get(id));choose(id);}
  }
  return {openMap:mapOpen,openCalcs,invalidate};
})();
function renderVisualTree(){Workbench.openMap();}
function renderDetailedCalcs(){Workbench.openCalcs();}
