/* Tree experiments deliberately keep separate state from the support linker. */
'use strict';
const TreeSimulator = (() => {
  let ctx=null, plan=null, result=null, selected=null, group=0, activeSkill=0;
  let query='', filter='near', mode='path', page=0, busy=false, ticket=0;
  const pageSize=36;
  const visible=()=>buildTab==='tree-sim'&&!$('buildWorkspace').hidden;
  const str=v=>esc(v);
  const list=x=>Array.isArray(x)?x:[];
  const number=v=>v==null?'—':typeof v==='boolean'?(v?'Sim':'Não'):typeof v==='number'?v.toLocaleString('pt-BR',{maximumFractionDigits:4}):String(v);
  const signed=v=>v==null?'não comparável':(v>0?'+':'')+number(v);
  const nodeType=n=>n.ascendancy?'Ascendência':({Normal:'Passiva',Notable:'Notable',Keystone:'Keystone',Socket:'Jewel socket',ClassStart:'Início',AscendClassStart:'Início de ascendência'}[n.kind]||n.kind);
  const currentGroup=()=>list(ctx?.groups).find(g=>Number(g.index)===Number(group));
  async function request(route,body={}){
    const ctl=new AbortController(), timer=setTimeout(()=>ctl.abort(),180000);
    try{
      const r=await fetch('/api/tree-sim/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Local-App':'poe2-explorer'},body:JSON.stringify(body),signal:ctl.signal});
      const d=await r.json(); if(!r.ok)throw new Error(d.error||`HTTP ${r.status}`); return d;
    }catch(e){if(e.name==='AbortError')throw new Error('O cálculo excedeu 3 minutos. Confira a janela do programa antes de repetir; o servidor pode ainda estar restaurando a build.');throw e;}
    finally{clearTimeout(timer);}
  }
  function shell(){
    return `<section class="ts-page"><div class="ts-heading"><div><span class="eyebrow">EXPERIMENTO DE ÁRVORE · SEM ALTERAR A BUILD</span><h2>O que este ponto muda?</h2><p>Escolha uma passiva, confira o caminho e compare o efeito na sua build.</p></div><button id="tsReload" class="secondary" ${busy?'disabled':''}>Recarregar árvore</button></div><div id="tsBody"></div></section>`;
  }
  function warning(message){return `<div class="ts-notice" role="status">${str(message)}</div>`;}
  function matched(){
    const q=query.trim().toLowerCase();
    return list(ctx?.nodes).filter(n=>{
      if(filter==='near' && (n.allocated||!n.editable||n.path_distance==null||n.path_distance>1))return false;
      if(filter==='allocated'&&!n.allocated)return false;
      if(filter==='available'&&n.allocated)return false;
      if(filter==='ascendancy'&&!n.ascendancy)return false;
      return !q||[n.name,n.id,...list(n.stats)].join(' ').toLowerCase().includes(q);
    }).sort((a,b)=>Number(!a.editable)-Number(!b.editable)||(a.path_distance??1e9)-(b.path_distance??1e9)||String(a.name).localeCompare(String(b.name))||a.id-b.id);
  }
  function nodeCard(n){
    const distance=n.allocated?'Alocado':n.path_distance==null?'Caminho não informado':`${n.path_distance} ponto(s) no caminho do PoB`;
    return `<button class="ts-node ${selected===n.id?'selected':''}" data-ts-node="${n.id}" ${!n.editable||busy?'disabled':''} title="${str(n.blocked_reason||'Selecionar ponto para teste')}"><span class="ts-node-meta"><span>${str(nodeType(n))}</span><span>#${n.id}</span></span><strong>${str(n.name)}</strong><span class="ts-node-stats">${list(n.stats).map(x=>str(x)).join('<br>')||'Sem texto de efeito exposto.'}</span><span class="ts-node-foot">${str(n.editable?distance:n.blocked_reason)}</span></button>`;
  }
  function nodeList(){
    const all=matched(), maxPage=Math.max(0,Math.ceil(all.length/pageSize)-1);page=Math.min(page,maxPage);
    return `<div class="ts-list-head"><span>${all.length} pontos encontrados</span><span>Ordem: proximidade, não poder</span></div><div class="ts-node-grid">${all.slice(page*pageSize,(page+1)*pageSize).map(nodeCard).join('')||warning('Nenhum ponto corresponde ao filtro. Use Todos ou busque outra palavra.')}</div><div class="ts-pagination"><button id="tsPrev" class="secondary" ${page===0||busy?'disabled':''}>← Anterior</button><span>${page+1} / ${maxPage+1}</span><button id="tsNext" class="secondary" ${page>=maxPage||busy?'disabled':''}>Próxima →</button></div>`;
  }
  function planHtml(){
    if(!plan)return `<div class="ts-empty"><span class="eyebrow">02 · PREPARAR O TESTE</span><h3>Selecione um ponto à esquerda</h3><p>Para começar, use <strong>Próximos</strong> e escolha uma passiva com efeito simples. Isso é um teste controlado, não uma recomendação de build.</p></div>`;
    const add=plan.action==='add', verbs=add?['Alocar','alocados']:['Remover','removidos'];
    return `<span class="eyebrow">02 · PREPARAR O TESTE</span><h3>${verbs[0]} ${str(plan.target.name)}</h3><div class="ts-plan-count"><strong>${signed(plan.total_delta)}</strong><span>pontos no teste</span></div><p class="ts-small">Comuns: ${signed(plan.ordinary_delta)} · ascendência: ${signed(plan.ascendancy_delta)}</p>${plan.isolated_hypothesis?warning('Hipótese isolada: a ligação com a árvore pode ficar inválida. O número calculado não aprova uma alocação no jogo.'):'<div class="ts-path-ok">Caminho/dependências obtidos do PoB.</div>'}<p class="ts-small">Pontos disponíveis e limites de ascendência não foram confirmados. O custo do caminho não significa que você tenha pontos sobrando.</p><details open class="ts-path"><summary>${list(plan.changes).length} ponto(s) ${verbs[1]} nesta simulação</summary><ol>${list(plan.changes).map(n=>`<li><b>${str(n.name)}</b> <small>#${n.id}</small>${list(n.stats).length?`<span>${list(n.stats).map(str).join(' · ')}</span>`:''}</li>`).join('')}</ol></details><button id="tsCompare" class="primary ts-compare" ${busy||!group||!activeSkill?'disabled':''}>Comparar no PoB</button><p class="ts-small">Nenhuma mudança é aplicada à build salva.</p>`;
  }
  function metricTable(rows){
    return `<div class="ts-table-wrap"><table class="ts-metrics"><thead><tr><th>Métrica</th><th>Atual</th><th>Teste</th><th>Diferença</th></tr></thead><tbody>${rows.map(r=>`<tr><th>${str(r.label)}${r.label!==r.key?`<small>${str(r.key)}</small>`:''}</th><td>${str(number(r.before))}</td><td>${str(number(r.after))}</td><td>${r.comparable?str(signed(r.delta)):'não comparável'}${r.pct!=null?`<small>${str(signed(r.pct))}%</small>`:''}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function results(){
    if(!result)return '';
    const changed=list(result.metrics).filter(r=>r.changed), same=list(result.metrics).filter(r=>!r.changed);
    return `<section class="ts-result"><div class="ts-heading"><div><span class="eyebrow">03 · COMPARAÇÃO</span><h3>${str(result.skill?.name||'Skill selecionada')} · ${result.plan.action==='add'?'Alocação':'Remoção'}</h3><p>Mesma build e configurações; somente os pontos do plano são usados como alteração.</p></div><button id="tsReport" class="secondary" ${busy?'disabled':''}>Baixar relatório JSON</button></div>${result.numeric_check_passed?'<div class="ts-path-ok">Controle sem alterações A/A: resultados consistentes.</div>':warning('O controle A/A divergiu. Estes números precisam de revisão; não use esta comparação para decidir uma troca.')} ${result.original_restored?'<p class="ts-restored">Build original recarregada e alocações conferidas.</p>':''}${result.plan.isolated_hypothesis?warning('Resultado de hipótese isolada. Não confirma um caminho válido na árvore.'):''}<h4>Métricas que mudaram</h4>${changed.length?metricTable(changed):warning('Nenhuma diferença nos valores exportados. Isso não prova ausência de efeito: o cálculo deste ponto ou a interação pode exigir revisão no PoB.')}<p class="ts-small">Seta para cima não significa automaticamente melhor. Compare dano, defesa, custo e seu objetivo.</p><details><summary>Valores sem mudança (${same.length})</summary>${same.length?metricTable(same):'<p>Nenhum valor estável exportado.</p>'}</details><details><summary>Fonte e verificações</summary><p class="ts-small">PoB ${str(result.engine_version||'versão não informada')} · árvore ${str(result.tree_version||'não informada')}<br>${str(result.calculator)}<br>Build: ${str(result.build_hash.slice(0,16))}<br>Orçamento de pontos: não validado.</p>${list(result.control_differences).length?`<p>${str(result.control_differences.join(', '))}</p>`:''}</details></section>`;
  }
  function render(){
    if(!visible())return;
    $('buildContent').innerHTML=shell();
    if(!ctx){$('tsBody').innerHTML=warning('Carregando os nós da build no motor PoB…');return;}
    const counts=ctx.counts||{}, effects=list(currentGroup()?.effects);
    $('tsBody').innerHTML=`<div class="ts-context"><span><b>${str(ctx.tree_version||'—')}</b> versão da árvore</span><span><b>${counts.known?str(counts.ordinary):'—'}</b> alocações comuns*</span><span><b>${counts.known?str(counts.ascendancy):'—'}</b> ascendência</span><span><b>${str(ctx.active_weapon_set||'—')}</b> weapon set ativo</span></div><p class="ts-small">*Contagem exposta pelo PoB, não saldo de pontos disponíveis. Este módulo usa os IDs e textos do PoB carregado, sem depender do mapeamento RePoE.</p><div id="tsStatus" class="ts-status" role="status" ${busy?'':'hidden'}>${busy?'PoB trabalhando. Aguarde; a build original será recarregada ao final.':''}</div><div class="ts-toolbar"><label>Skill para medir<select id="tsGroup" ${busy?'disabled':''}>${list(ctx.groups).map(g=>`<option value="${g.index}" ${Number(g.index)===Number(group)?'selected':''} ${!g.enabled?'disabled':''}>${str(g.label||g.effects?.[0]?.name||'Grupo')} · grupo ${g.index}</option>`).join('')}</select></label><label>Efeito ativo<select id="tsEffect" ${busy?'disabled':''}>${effects.map(e=>`<option value="${e.index}" ${Number(e.index)===Number(activeSkill)?'selected':''}>${str(e.name)}</option>`).join('')}</select></label><label>Como testar<select id="tsMode" ${busy?'disabled':''}><option value="path" ${mode==='path'?'selected':''}>Com caminho / dependências</option><option value="isolated" ${mode==='isolated'?'selected':''}>Só este ponto · hipótese</option></select></label></div><div class="ts-layout"><section class="ts-catalog"><span class="eyebrow">01 · ESCOLHER O PONTO</span><div class="ts-search"><label class="sr-only" for="tsQuery">Nome, efeito ou ID do ponto</label><input id="tsQuery" value="${str(query)}" placeholder="Nome, efeito ou ID: Area, Life, Ignite…" ${busy?'disabled':''}><label class="sr-only" for="tsFilter">Filtrar pontos</label><select id="tsFilter" ${busy?'disabled':''}>${[['near','Próximos · até 1 ponto'],['allocated','Já alocados'],['available','Não alocados'],['ascendancy','Ascendências'],['all','Todos']].map(([key,label])=>`<option value="${key}" ${key===filter?'selected':''}>${label}</option>`).join('')}</select></div><div class="ts-chips">${['Area','Ignite','Life','Mana'].map(q=>`<button data-ts-query="${q}" ${busy?'disabled':''}>${q}</button>`).join('')}<button data-ts-query="" ${busy?'disabled':''}>Limpar</button></div><div id="tsNodes">${nodeList()}</div></section><aside class="ts-plan">${planHtml()}</aside></div>${results()}`;
  }
  async function load(){
    const t=++ticket;busy=true;ctx=null;plan=null;result=null;selected=null;$('toast').hidden=true;render();
    try{
      const d=await request('context'); if(t!==ticket)return;
      ctx=d;
      const gs=list(ctx.groups).filter(g=>g.enabled&&list(g.effects).length);
      const g=gs.find(g=>Number(g.index)===Number(ctx.selected_group))||gs[0];
      if(!g)throw new Error('PoB não expôs nenhuma skill ativa para medir. Confira a build importada.');
      group=g.index;activeSkill=g.active_index||g.effects[0].index; page=0;
      if(!g.effects.some(e=>Number(e.index)===Number(activeSkill)))activeSkill=g.effects[0].index;
    }catch(e){if(t===ticket&&visible()){$('tsBody').innerHTML=warning(e.message)+'<button class="secondary" data-build-tab-jump="engine">Abrir Motor PoB</button>';ctx=null;}}
    finally{if(t===ticket){busy=false;if(ctx)render();else if($('tsReload'))$('tsReload').disabled=false;}}
  }
  async function choose(id){
    if(busy||!ctx)return; selected=Number(id);busy=true;plan=null;result=null;$('toast').hidden=true;render();
    try{plan=await request('preview',{node_id:selected,mode,build_hash:ctx.build_hash});}
    catch(e){notify(e.message,true);}
    finally{busy=false;render();}
  }
  async function calculate(){
    if(busy||!plan||!ctx)return;busy=true;result=null;$('toast').hidden=true;render();
    try{
      result=await request('compare',{node_id:selected,mode,build_hash:ctx.build_hash,fingerprint:plan.fingerprint,group_index:Number(group),active_index:Number(activeSkill)});
    }catch(e){notify(e.message,true);}
    finally{busy=false;render();if(visible())document.querySelector('.ts-result')?.scrollIntoView({behavior:'smooth',block:'start'});}
  }
  function report(){
    if(!result)return;
    const blob=new Blob([JSON.stringify(result,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob);
    const a=document.createElement('a');a.href=url;a.download='synergy-tree-'+result.plan.target.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);
  }
  document.addEventListener('click',e=>{
    const b=e.target.closest('button');if(!b||!visible()||busy)return;
    if(b.dataset.tsNode){choose(b.dataset.tsNode);return;}
    if(b.dataset.tsQuery!==undefined){query=b.dataset.tsQuery;page=0;render();return;}
    if(b.id==='tsReload'){load();return;}
    if(b.id==='tsPrev'){page=Math.max(0,page-1);render();return;}
    if(b.id==='tsNext'){page++;render();return;}
    if(b.id==='tsCompare'){calculate();return;}
    if(b.id==='tsReport'){report();return;}
  });
  document.addEventListener('input',e=>{
    if(e.target.id==='tsQuery'&&!busy){query=e.target.value;page=0;if($('tsNodes'))$('tsNodes').innerHTML=nodeList();}
  });
  document.addEventListener('change',e=>{
    if(!visible()||busy)return;
    const el=e.target;
    if(el.id==='tsFilter'){filter=el.value;page=0;render();}
    if(el.id==='tsGroup'){group=Number(el.value);const g=currentGroup();activeSkill=g.active_index||g.effects[0].index;result=null;render();}
    if(el.id==='tsEffect'){activeSkill=Number(el.value);result=null;render();}
    if(el.id==='tsMode'){mode=el.value;result=null;if(selected)choose(selected);else render();}
  });
  return {open:()=>{if(busy){render();return;}load();},report};
})();
function renderTreeSimulator(){TreeSimulator.open();}
