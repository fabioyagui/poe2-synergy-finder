'use strict';
const $=id=>document.getElementById(id);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>Number(x||0).toLocaleString('pt-BR');
const bytes=x=>x==null?'tamanho não informado':x>1048576?(x/1048576).toFixed(1)+' MB':Math.ceil(x/1024)+' KB';
const kind=x=>({SUPPORT:'Support',SKILL:'Skill',META:'Meta skill',PASSIVE:'Passiva',NOTABLE:'Notable',KEYSTONE:'Keystone',ASCENDANCY_NODE:'Nó de ascendência',ASCENDANCY:'Ascendência',TREE_START:'Início da árvore',TREE_DECORATION:'Decorativo',JEWEL_SOCKET:'Jewel socket'}[x]||x);
const rel=x=>({PRODUCES:'Produz',ENABLES:'Habilita aplicação',AMPLIFIES:'Amplifica',REDUCES:'Reduz',MODIFIES:'Modifica',REQUIRES:'Exige condição',PREVENTS:'Impede aplicação',BELONGS_TO:'Pertence a',GRANTS_SKILL:'Concede skill',CONSUMES:'Consome',GENERATES:'Gera',CREATES:'Cria',PREVENTS_CONSUMPTION:'Impede consumo de',MENTIONS:'Menciona',HAS_TAG:'Tag',HAS_TYPE:'Tipo',ADDS_TYPE:'Adiciona tipo',ADDS_MINION_TYPE:'Adiciona tipo ao minion',ALLOWS_TYPE_OPERAND:'Operando de exigência',EXCLUDES_TYPE_OPERAND:'Operando de exclusão'}[x]||x);
let state={view:'catalog',skill:null,component:'',scope:'supports',color:'',tag:'',offset:0,limit:36};
let status=null,searchTicket=0,skillTicket=0,anchorTicket=0,detailTicket=0,jobTimer=null,polling=false,lastFinished=null;
let entity=null,detailTab='text',skillTimer=null,queryTimer=null;
let currentPobBuild=null,buildTab='overview';
let treeView={analysis:null,q:'',kind:'all'};
let buildLibrary={rows:[],facets:{},timer:null};
let linker={context:null,groupIndex:null,selected:[],query:'',result:null,compat:null,compatLoading:false};
let buildVisuals={key:'',assets:{},ready:false,loading:false,error:''};
let gearTrade={slot:'',model:null,loading:false,error:'',result:null};
// Never leave the browser's broken-image icon inside the in-game style UI.
// If a build-provided icon fails, retry the RePoE-resolved art once; otherwise
// replace it with the same neutral placeholder used for unresolved artwork.
document.addEventListener('error',event=>{
  const img=event.target;
  if(!(img instanceof HTMLImageElement)||!img.classList.contains('gear-art')&&!img.classList.contains('overview-gear-art')&&!img.classList.contains('tooltip-art')&&!img.classList.contains('gem-art'))return;
  const fallback=img.dataset.fallbackSrc||'';
  if(fallback){img.dataset.fallbackSrc='';img.src=fallback;return;}
  const span=document.createElement('span');span.className=img.className+' art-fallback';span.setAttribute('aria-hidden','true');span.textContent='◇';img.replaceWith(span);
},true);
function notify(text,error=false){$('toast').hidden=false;$('toast').textContent=text;$('toast').classList.toggle('error',error);}
async function api(path,body){
  const opts=body?{method:'POST',headers:{'Content-Type':'application/json','X-Local-App':'poe2-explorer'},body:JSON.stringify(body)}:{};
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),30000);
  try{const r=await fetch(path,{...opts,signal:controller.signal});const j=await r.json();if(!r.ok)throw new Error(j.error||`HTTP ${r.status}`);return j;}
  catch(e){if(e.name==='AbortError')throw new Error('O servidor local não respondeu em 30 segundos. Confira a janela do programa.');throw e;}
  finally{clearTimeout(timer);}
}

function pobValue(v){
  if(v===null||v===undefined||v==='')return '—';
  if(typeof v==='number')return Number.isInteger(v)?v.toLocaleString('pt-BR'):v.toLocaleString('pt-BR',{maximumFractionDigits:2});
  return String(v);
}
function renderPobSummary(d){
  if(!d||d.imported===false){
    $('pobSummary').innerHTML='<p class="muted">Nenhuma build PoB importada ainda.</p>';return;
  }
  const stats=Object.entries(d.player_stats||{});
  const skills=(d.skills||[]).map((g,i)=>`<div class="pob-skill"><strong>${esc(g.label||g.main_gem||('Grupo '+(i+1)))}</strong><small> · main: ${esc(g.main_gem||'não identificado')}</small><div class="pob-gems">${(g.gems||[]).map((x,j)=>`<span class="pob-gem ${j===g.main_index?'main':''}">${esc(x.name)}${x.level?' '+esc(x.level):''}${x.quality?'/'+esc(x.quality):''}</span>`).join('')}</div></div>`).join('');
  $('pobSummary').innerHTML=`<div class="pob-hero"><span class="eyebrow">BASELINE DO EXPORT</span><h3>${esc(d.class_name||'Classe não identificada')} · ${esc(d.ascendancy||'sem ascendência identificada')}</h3><p>Nível ${esc(d.level||'?')} · ${fmt(d.skill_group_count)} grupos de skills · ${fmt(d.tree?.allocated_nodes)} nós alocados · ${fmt(d.items?.count)} itens · ${fmt(d.player_stat_count)} PlayerStats</p></div>
  ${stats.length?`<div class="pob-metrics">${stats.slice(0,12).map(([k,v])=>`<div class="pob-metric"><strong>${esc(pobValue(v))}</strong><span>${esc(k)}</span></div>`).join('')}</div>`:'<p class="muted">O XML não trouxe PlayerStats reconhecidos.</p>'}
  <h3>Skills / links do PoB</h3>${skills||'<p class="muted">Nenhum grupo encontrado.</p>'}
  <details class="pob-rawdetails"><summary>Ver todos os PlayerStats do export</summary><table class="pob-stat-table">${Object.entries(d.all_player_stats||{}).sort((a,b)=>a[0].localeCompare(b[0])).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${esc(pobValue(v))}</td></tr>`).join('')}</table></details>`;
}
async function loadCurrentPob(){
  try{renderPobSummary(await api('/api/pob/current'));}catch(e){$('pobSummary').innerHTML=`<p class="data-error">${esc(e.message)}</p>`;}
}
async function openPob(){
  $('pobDialog').showModal();
  await loadCurrentPob();
}
function activateCurrentBuild(d){
  currentPobBuild=d;
  if(typeof Workbench!=='undefined')Workbench.invalidate();
  linker={context:null,groupIndex:null,selected:[],query:'',result:null,compat:null,compatLoading:false};
  treeView={analysis:null,q:'',kind:'all'};
  buildVisuals={key:'',assets:{},ready:false,loading:false,error:''};
  gearTrade={slot:'',model:null,loading:false,error:'',result:null};
  $('openCurrentBuild').hidden=false;
  $('openCurrentBuild').textContent=`Build atual · Lv${d.level||'?'} ${d.ascendancy||d.class_name||''}`;
  if($('pobDialog').open)$('pobDialog').close();
  buildTab='overview';setAppMode('build');renderCurrentBuild();
}
async function importPob(){
  const source=$('pobSource').value.trim();if(!source){notify('Informe o link pobb.in ou código PoB.',true);return;}
  $('importPob').disabled=true;$('importPob').textContent='Carregando…';
  try{const d=await api('/api/pob/import',{source});activateCurrentBuild(d);notify('Build carregada. Árvore visual e Cálculos estão nas abas acima.');}
  catch(e){notify(e.message,true);}
  finally{$('importPob').disabled=false;$('importPob').textContent='Carregar build';}
}



function setAppMode(mode){
  const buildMode=mode==='build',libraryMode=mode==='library';
  $('buildWorkspace').hidden=!buildMode;
  $('buildLibraryWorkspace').hidden=!libraryMode;
  if(buildMode||libraryMode){
    $('welcome').hidden=true;$('workspace').hidden=true;
  }else{
    $('welcome').hidden=!!status?.entities;$('workspace').hidden=!status?.entities;
  }
}

function libraryStat(row,key){return row?.player_stats?.[key];}
function buildCardHtml(row){
  const skills=(row.skills_preview||[]).slice(0,3);
  const life=libraryStat(row,'Life'),es=libraryStat(row,'EnergyShield'),dps=libraryStat(row,'CombinedDPS')??libraryStat(row,'TotalDPS');
  return `<article class="library-build-card">
    <div class="library-card-top"><div><span class="eyebrow">${esc(row.source_kind||'BUILD')}</span><h3>${esc(row.character_name||row.main_skill||row.title||'Build')}</h3><p>${esc(row.ascendancy||row.class_name||'Classe')} · Lv${esc(row.level||'?')}${row.league?' · '+esc(row.league):''}</p></div><span class="library-level">${esc(row.level||'?')}</span></div>
    <div class="library-mini-stats">${life!==undefined?`<span><b>${esc(pobValue(life))}</b> Life</span>`:''}${es!==undefined?`<span><b>${esc(pobValue(es))}</b> ES</span>`:''}${dps!==undefined?`<span><b>${esc(pobValue(dps))}</b> DPS*</span>`:''}<span><b>${fmt(row.tree_nodes)}</b> passivas</span></div>
    <div class="library-skills">${skills.map(g=>`<div><strong>${esc(g.main_gem||g.label)}</strong><small>${esc((g.gems||[]).slice(1,5).join(' · '))}</small></div>`).join('')}</div>
    <p class="build-source">${esc(row.source||'Biblioteca local')}</p>
    <div class="library-card-actions"><button class="primary" data-library-use="${esc(row.id)}">Usar no Finder</button><button class="secondary" data-library-delete="${esc(row.id)}">Remover</button></div>
  </article>`;
}
function sourceStatusHtml(rows){return `<div class="source-adapter-grid">${(rows||[]).map(s=>`<article class="source-adapter ${esc(s.status)}"><div><strong>${esc(s.name)}</strong><span>${s.status==='ready'?'ATIVO':s.status==='blocked-registration'?'GGG BLOQUEOU NOVOS APPS':s.status==='planned'?'PRÓXIMO':'LIMITADO'}</span></div><p>${esc(s.detail)}</p>${s.id==='poeninja'?'<a href="https://poe.ninja/poe2/builds" target="_blank" rel="noreferrer">Abrir poe.ninja Builds ↗</a>':''}</article>`).join('')}</div>`;}
function populateLibraryFilters(f){
  const spec=[['libraryClass',f?.classes||[],'Todas as classes'],['libraryAsc',f?.ascendancies||[],'Todas as ascendências'],['librarySkill',f?.main_skills||[],'Todas as main skills']];
  for(const [id,vals,label] of spec){const el=$(id),prev=el.value;el.innerHTML=`<option value="">${label}</option>`+vals.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');if(vals.includes(prev))el.value=prev;}
}
function setLibraryTab(tab){
  buildLibrary.tab=tab;
  document.querySelectorAll('[data-library-tab]').forEach(b=>b.classList.toggle('active',b.dataset.libraryTab===tab));
  $('libraryLocalPanel').hidden=tab!=='local';
  $('libraryGggPanel').hidden=tab!=='ggg';
  $('libraryLadderPanel').hidden=tab!=='ladder';
  if(tab==='ggg')renderGggAccount();
  if(tab==='ladder')renderLadderInfo();
}
function gggCharacterCard(c){return `<article class="ggg-character-card">
  <div><span class="eyebrow">${esc(c.league||'PoE2')}</span><h3>${esc(c.name||'?')}</h3><p>${esc(c.class||'Classe')} · Lv${esc(c.level||'?')}</p></div>
  <button class="primary" data-ggg-import="${esc(c.name||'')}">Usar no Finder</button>
</article>`;}
async function renderGggAccount(){
  $('libraryGggPanel').innerHTML='<div class="build-panel"><strong>Lendo configuração da GGG…</strong></div>';
  try{
    const st=await api('/api/ggg/status');
    let chars='';
    if(st.authenticated){
      try{const d=await api('/api/ggg/characters');chars=`<div class="ggg-character-list">${(d.characters||[]).map(gggCharacterCard).join('')||'<p class="muted">A conta autorizada não retornou personagens PoE2.</p>'}</div>`;}
      catch(e){chars=`<div class="build-warning">${esc(e.message)}</div>`;}
    }
    $('libraryGggPanel').innerHTML=`<div class="ggg-account-layout">
      <div class="build-panel">
        <span class="eyebrow">FONTE OFICIAL · GGG</span><h2>Minha conta Path of Exile</h2>
        <p>O Finder já implementa OAuth 2.1 + PKCE e os endpoints oficiais <code>/character/poe2</code>. Senha nunca passa pelo Finder.</p>
        <div class="build-warning"><strong>Limitação atual da GGG</strong><br>${esc(st.registration_note||'')}<br><small>Não reutilizamos o client_id do Path of Building ou do poe.ninja.</small></div>
        <label>Client ID do seu Public Client<input id="gggClientId" value="${esc(st.client_id||'')}" placeholder="seu-client-id-registrado"></label>
        <label>Contato para User-Agent<input id="gggContact" value="${esc(st.contact||'')}" placeholder="email ou contato registrado"></label>
        <div class="ggg-redirect"><span>Redirect URI que deve estar registrado no Public Client</span><code>${esc(st.redirect_uri||'http://127.0.0.1:8777/oauth/callback')}</code></div>
        <div class="ggg-actions"><button id="gggSaveConfig" class="secondary">Salvar configuração</button>
          ${st.authenticated?'<button id="gggLogout" class="secondary">Desconectar GGG</button>':`<button id="gggAuthorize" class="primary" ${st.configured?'':'disabled'}>Autorizar com Path of Exile</button>`}</div>
        <p class="muted">Token local: ${esc(st.token_storage||'')} · scopes: ${esc((st.scopes||[]).join(', '))}</p>
      </div>
      <div class="build-panel"><h3>Personagens da conta</h3>${st.authenticated?chars:'<p class="muted">Depois da autorização, seus personagens PoE2 aparecem aqui e podem virar a Build atual com um clique.</p>'}</div>
      <div class="build-panel ggg-json-fallback"><h3>Snapshot JSON oficial</h3><p class="muted">Fallback para desenvolvimento: cole uma resposta oficial do endpoint Get Character. O Finder converte equipamento, skills e passivas diretamente, sem XML PoB.</p><textarea id="gggSnapshotJson" rows="7" placeholder='{"character": {...}}'></textarea><button id="gggImportSnapshot" class="secondary">Importar snapshot JSON</button></div>
    </div>`;
  }catch(e){$('libraryGggPanel').innerHTML=`<div class="build-warning">${esc(e.message)}</div>`;}
}
function renderLadderInfo(){
  $('libraryLadderPanel').innerHTML=`<div class="build-panel"><span class="eyebrow">GGG LADDER</span><h2>Ladder PoE2</h2><p>A API oficial documenta <code>realm=poe2</code> e até 1000 entradas por ladder.</p><div class="build-warning"><strong>Ainda não ativada neste app local.</strong><br>O endpoint exige <code>service:leagues:ladder</code>, um service scope. Um aplicativo desktop Public Client não deve embutir credenciais confidenciais. Esta aba está preparada para um backend/cliente autorizado futuro.</div></div>`;
}
async function gggSaveConfig(){try{await api('/api/ggg/config',{client_id:$('gggClientId').value.trim(),contact:$('gggContact').value.trim()});await renderGggAccount();notify('Configuração GGG salva.');}catch(e){notify(e.message,true);}}
async function gggAuthorize(){try{const d=await api('/api/ggg/oauth/start',{});const w=window.open(d.authorize_url,'ggg-oauth','width=900,height=760');if(!w)notify('O navegador bloqueou a janela OAuth. Permita pop-ups para 127.0.0.1.',true);clearInterval(buildLibrary.gggPoll);let ticks=0;buildLibrary.gggPoll=setInterval(async()=>{ticks++;try{const st=await api('/api/ggg/status');if(st.authenticated){clearInterval(buildLibrary.gggPoll);buildLibrary.gggPoll=null;await renderGggAccount();notify('Conta GGG conectada.');}else if(ticks>120){clearInterval(buildLibrary.gggPoll);buildLibrary.gggPoll=null;}}catch(_e){}},1000);}catch(e){notify(e.message,true);}}
async function gggLogout(){try{await api('/api/ggg/logout',{});await renderGggAccount();notify('Conta GGG desconectada.');}catch(e){notify(e.message,true);}}
async function gggImportCharacter(name){try{const d=await api('/api/ggg/import-character',{name});activateCurrentBuild(d);notify('Snapshot oficial GGG carregado diretamente no Finder.');}catch(e){notify(e.message,true);}}
async function gggImportSnapshot(){try{const raw=$('gggSnapshotJson').value.trim();if(!raw)throw new Error('Cole o JSON primeiro.');const d=await api('/api/ggg/import-snapshot',{snapshot:raw});activateCurrentBuild(d);notify('Snapshot GGG importado.');}catch(e){notify(e.message,true);}}

async function loadBuildLibrary(sync=true){
  $('buildLibraryCards').innerHTML='<div class="build-panel"><strong>Carregando biblioteca…</strong></div>';
  const params=new URLSearchParams({q:$('libraryQuery').value.trim(),class_name:$('libraryClass').value,ascendancy:$('libraryAsc').value,main_skill:$('librarySkill').value,sync:sync?'1':'0'});
  try{const d=await api('/api/builds?'+params);buildLibrary.rows=d.results||[];buildLibrary.facets=d.facets||{};populateLibraryFilters(d.facets||{});$('buildSourceStatus').innerHTML=sourceStatusHtml(d.sources);$('libraryCount').textContent=`${d.total||0} build(s) · ${d.library_total||0} na biblioteca`;$('buildLibraryCards').innerHTML=buildLibrary.rows.map(buildCardHtml).join('')||'<div class="empty-results"><strong>Nenhuma build encontrada.</strong><br>Use “Adicionar build” para guardar um PoB/XML. As builds das versões anteriores são reaproveitadas automaticamente.</div>';if(d.sync?.imported)notify(`${d.sync.imported} build(s) anterior(es) adicionada(s) à biblioteca.`);}
  catch(e){$('buildLibraryCards').innerHTML=`<div class="build-warning">${esc(e.message)}</div>`;}
}
async function openBuildLibrary(){setAppMode('library');await loadBuildLibrary(true);}
async function useLibraryBuild(id){try{const d=await api('/api/builds/use',{id});activateCurrentBuild(d);notify('Build carregada diretamente da biblioteca.');}catch(e){notify(e.message,true);}}
async function deleteLibraryBuild(id){if(!confirm('Remover esta build da biblioteca local?'))return;try{const d=await api('/api/builds/delete',{id});if(d.was_current){currentPobBuild=null;if(typeof Workbench!=='undefined')Workbench.invalidate();$('openCurrentBuild').hidden=true;setAppMode('library');notify('Build ativa removida. O Motor PoB foi limpo para não manter cálculos antigos.');}else{notify('Build removida da biblioteca.');}await loadBuildLibrary(false);}catch(e){notify(e.message,true);}}

function gearName(item){
  return item?.name||item?.base_type||'Item sem nome';
}
function visualNames(d){
  const names=[];
  for(const s of d?.items?.slots||[]){const n=s?.item?.base_type||s?.item?.name;if(n)names.push(n);}
  for(const g of d?.skills||[])for(const gem of g?.gems||[])if(gem?.name)names.push(gem.name);
  return [...new Set(names)].slice(0,180);
}
function visualKey(d){return [d?.library_id||'',d?.source||'',...visualNames(d)].join('|');}
function visualAsset(name){return buildVisuals.assets?.[name]||null;}
function imageFor(name,remote='',cls='item-art'){
  const asset=visualAsset(name),primary=remote||asset?.url||'',fallback=remote&&asset?.url&&remote!==asset.url?asset.url:'';
  if(!primary)return `<span class="${cls} art-fallback" aria-hidden="true">◇</span>`;
  return `<img class="${cls}" src="${esc(primary)}" ${fallback?`data-fallback-src="${esc(fallback)}"`:''} alt="" loading="lazy" referrerpolicy="no-referrer">`;
}
async function ensureBuildVisuals(d){
  const names=visualNames(d),key=visualKey(d);
  if(!names.length||buildVisuals.loading||(buildVisuals.key===key&&buildVisuals.ready))return;
  buildVisuals={key,assets:{},ready:false,loading:true,error:''};
  try{
    const result=await api('/api/assets/resolve',{names});
    if(buildVisuals.key!==key)return;
    buildVisuals.assets=result.assets||{};buildVisuals.error=result.warning||'';buildVisuals.ready=true;
  }catch(e){if(buildVisuals.key===key){buildVisuals.error=e.message;buildVisuals.ready=true;}}
  finally{
    if(buildVisuals.key===key){buildVisuals.loading=false;if(currentPobBuild===d&&['overview','skills','gear'].includes(buildTab))renderCurrentBuild();}
  }
}
function rarityClass(r){
  const v=String(r||'').toLowerCase();return v.includes('unique')?'unique':v.includes('rare')?'rare':v.includes('magic')?'magic':'normal';
}
function gemVisual(gem,isMain=false){
  const name=gem?.name||'Gem';
  return `<div class="gem-socket ${isMain?'main':''}" title="${esc(name)}">${imageFor(name,'','gem-art')}<span>${esc(name)}</span><small>${gem?.level?`Lv ${esc(gem.level)}`:''}${gem?.quality?` · Q${esc(gem.quality)}`:''}</small></div>`;
}
function canonicalSlot(slot){
  const s=String(slot||'').toLowerCase().replace(/[^a-z0-9]+/g,' ');
  if(s.includes('weapon')&&(/\b2\b/.test(s)||s.includes('off')))return 'weapon2';
  if(s.includes('weapon'))return 'weapon1';
  if(s.includes('helmet')||s.includes('helm'))return 'helmet';
  if(s.includes('body')||s.includes('chest'))return 'body';
  if(s.includes('glove'))return 'gloves';
  if(s.includes('boot'))return 'boots';
  if(s.includes('belt'))return 'belt';
  if(s.includes('amulet'))return 'amulet';
  if(s.includes('ring')&&(/\b2\b/.test(s)||s.includes('right')))return 'ring2';
  if(s.includes('ring'))return 'ring1';
  if(s.includes('flask')||s.includes('charm'))return 'utility';
  return 'other';
}
function loadoutSlots(d){
  const desired=['weapon1','helmet','amulet','weapon2','gloves','body','ring1','ring2','belt','boots'];
  const mapped=new Map(),other=[];
  for(const s of d?.items?.slots||[]){const k=canonicalSlot(s.slot);if(k==='other'||mapped.has(k))other.push(s);else mapped.set(k,s);}
  return {desired,mapped,other};
}
function gearTile(slot,key){
  if(!slot)return `<div class="loadout-slot ${key} empty"><span class="slot-empty-label">${esc(key.replace(/\d/g,''))}</span></div>`;
  const item=slot.item||{},name=gearName(item),assetName=item.base_type||name,selected=gearTrade.slot===slot.slot;
  return `<button class="loadout-slot ${key} rarity-${rarityClass(item.rarity)} ${selected?'selected':''}" data-gear-slot="${esc(slot.slot)}" title="${esc(name)}">
    <span class="slot-caption">${esc(slot.slot)}</span>${imageFor(assetName,item.icon||'','gear-art')}<span class="slot-item-name">${esc(name)}</span>
  </button>`;
}
function itemTooltipHtml(slot){
  const item=slot?.item||{},name=gearName(item),assetName=item.base_type||name,preview=item.preview||[];
  return `<section class="poe-item-tooltip rarity-${rarityClass(item.rarity)}">
    <div class="poe-item-title"><div>${imageFor(assetName,item.icon||'','tooltip-art')}</div><div><small>${esc(item.rarity||'Item')}</small><h3>${esc(name)}</h3>${item.base_type&&item.base_type!==name?`<p>${esc(item.base_type)}</p>`:''}</div></div>
    ${item.ilvl?`<div class="tooltip-property"><span>Item Level</span><b>${esc(item.ilvl)}</b></div>`:''}
    <div class="tooltip-lines">${preview.slice(3).filter(x=>!/^[- ]+$/.test(String(x))).map(x=>`<p>${esc(x)}</p>`).join('')||'<p class="muted">O export não trouxe linhas adicionais para este item.</p>'}</div>
  </section>`;
}
function tradeFilterRows(model){
  const rows=model?.mods||[];
  if(!rows.length)return '<p class="muted">Nenhuma linha de modifier foi encontrada neste item.</p>';
  return rows.map((m,i)=>{const ranges=(m.roll_ranges||[]).map(r=>`${r.min}–${r.max}`).join(' / '),hint=ranges?`roll ${ranges} · `:'';return m.matched?`<div class="trade-filter-row" data-trade-filter="${i}" data-stat-id="${esc(m.id)}">
      <label class="trade-check"><input type="checkbox" checked> <span><b>${esc(m.text)}</b><small>${esc(hint)}${esc(m.group)} · ${esc(m.trade_text)}</small></span></label>
      <input class="trade-min" inputmode="decimal" placeholder="min" value="${m.min??''}"><input class="trade-max" inputmode="decimal" placeholder="max" value="${m.max??''}">
    </div>`:`<div class="trade-filter-row unmatched"><span class="trade-unmatched">○</span><span><b>${esc(m.text)}</b><small>${ranges?`${esc(hint)}`:''}Não mapeado automaticamente no catálogo do trade2</small></span><input disabled placeholder="min"><input disabled placeholder="max"></div>`}).join('');
}
function tradePanelHtml(d,slots){
  const selected=slots.find(x=>x.slot===gearTrade.slot);
  if(!selected)return `<aside class="gear-trade-panel"><div class="trade-empty"><span class="eyebrow">TRADE SEARCH</span><h2>Selecione um equipamento</h2><p>Clique em uma peça do loadout para ver o item e montar a busca do market.</p></div></aside>`;
  if(gearTrade.loading)return `<aside class="gear-trade-panel">${itemTooltipHtml(selected)}<div class="trade-loading"><strong>Lendo os filtros atuais do trade2…</strong><p>Isso acontece localmente e não cria uma busca até você clicar em Buscar.</p></div></aside>`;
  if(gearTrade.error)return `<aside class="gear-trade-panel">${itemTooltipHtml(selected)}<div class="build-warning"><strong>Não consegui preparar os filtros.</strong><br>${esc(gearTrade.error)}<div class="trade-actions"><button class="secondary" data-trade-retry>Repetir</button></div></div></aside>`;
  const m=gearTrade.model;
  if(!m)return `<aside class="gear-trade-panel">${itemTooltipHtml(selected)}<div class="trade-actions"><button class="primary" data-trade-prepare>Carregar filtros do Trade</button></div></aside>`;
  return `<aside class="gear-trade-panel">${itemTooltipHtml(selected)}
    <section class="trade-builder"><div class="trade-builder-head"><div><span class="eyebrow">MARKET · POE2 TRADE</span><h2>Filtros do item</h2></div><span class="trade-match-count">${m.matched}/${(m.mods||[]).length} detectados</span></div>
    <div class="trade-top-controls"><label>Liga<input id="tradeLeague" value="${esc(m.league||d.league||'Standard')}" placeholder="Standard"></label><label>Status<select id="tradeStatus"><option value="online">Online</option><option value="any">Qualquer</option></select></label></div>
    <div class="trade-base-row"><span>Base</span><b>${esc(m.item?.base_type||m.item?.name||'—')}</b>${rarityClass(m.item?.rarity)==='unique'?`<em>Unique · nome exato: ${esc(m.item?.name||'')}</em>`:''}</div>
    <div class="trade-filter-head"><span>Modifier</span><span>Min</span><span>Max</span></div>${tradeFilterRows(m)}
    <p class="trade-note">${esc(m.note||'')}</p>
    <div class="trade-actions"><button class="secondary" data-trade-search-base>Buscar somente a base</button><button class="primary" data-trade-search>Buscar no Trade</button></div>
    <div id="tradeResult" class="trade-result">${gearTrade.result?`<a href="${esc(gearTrade.result.url)}" target="_blank" rel="noreferrer">Abrir busca no market ↗</a><span>${gearTrade.result.total==null?'':fmt(gearTrade.result.total)+' resultados'}</span>`:'A busca só é enviada ao trade2 quando você clicar no botão.'}</div></section></aside>`;
}
async function prepareGearTrade(slot){
  if(!slot)return;gearTrade={slot,model:null,loading:true,error:'',result:null};renderBuildGear(currentPobBuild);
  try{const m=await api('/api/trade/prepare',{slot});if(gearTrade.slot!==slot)return;gearTrade.model=m;gearTrade.loading=false;renderBuildGear(currentPobBuild);}
  catch(e){if(gearTrade.slot!==slot)return;gearTrade.loading=false;gearTrade.error=e.message;renderBuildGear(currentPobBuild);}
}
function selectGearSlot(slot){if(gearTrade.slot===slot&&gearTrade.model)return;gearTrade={slot,model:null,loading:false,error:'',result:null};renderBuildGear(currentPobBuild);prepareGearTrade(slot);}
function currentTradeFilters(){
  return [...document.querySelectorAll('[data-trade-filter]')].map(row=>({id:row.dataset.statId,enabled:!!row.querySelector('input[type="checkbox"]')?.checked,min:row.querySelector('.trade-min')?.value||'',max:row.querySelector('.trade-max')?.value||''}));
}
async function runTradeSearch(baseOnly=false){
  if(!gearTrade.slot)return;
  const box=$('tradeResult');if(box)box.innerHTML='<span>Enviando busca ao trade2…</span>';
  const buttons=[...document.querySelectorAll('[data-trade-search],[data-trade-search-base]')];buttons.forEach(x=>x.disabled=true);
  try{
    const result=await api('/api/trade/search',{slot:gearTrade.slot,league:$('tradeLeague')?.value||'Standard',online:$('tradeStatus')?.value!=='any',base_only:baseOnly,filters:currentTradeFilters()});
    gearTrade.result=result;
    if(box)box.innerHTML=`<a href="${esc(result.url)}" target="_blank" rel="noreferrer">Abrir busca no market ↗</a><span>${result.total==null?'':fmt(result.total)+' resultados'}</span>`;
    window.open(result.url,'_blank','noopener');
  }catch(e){if(box)box.innerHTML=`<span class="data-error">${esc(e.message)}</span>`;notify(e.message,true);}
  finally{buttons.forEach(x=>x.disabled=false);}
}

function renderBuildHero(d){
  const isGgg=d.source_type==='ggg-character';
  $('buildTitle').textContent=isGgg?`${d.character_name||'Personagem'} · ${d.ascendancy||d.class_name||'Classe'}`:`${d.class_name||'Classe não identificada'} · ${d.ascendancy||'sem ascendência identificada'}`;
  $('buildSubtitle').textContent=`Nível ${d.level||'?'}${d.league?' · '+d.league:''} · ${d.skill_group_count||0} grupos de skills · ${d.tree?.allocated_nodes||0} nós alocados · fonte: ${d.source||'—'}`;
  $('buildHero').innerHTML=`<div class="pob-hero ${isGgg?'ggg-hero':''}">
      <span class="eyebrow">${isGgg?'SNAPSHOT OFICIAL GGG':'BASELINE DO EXPORT POB'}</span>
      <h3>${esc(isGgg?(d.character_name||d.main_skill||'Personagem'):(d.main_skill||'Build importada'))}</h3>
      <p>${isGgg?`${fmt(d.items?.count)} equipamentos · ${fmt(d.skill_group_count)} skills · ${fmt(d.tree?.allocated_nodes)} passivas`: `${fmt(d.player_stat_count)} PlayerStats exportados · ${fmt(d.items?.count)} itens equipados · ${fmt(d.items?.defined_count)} itens definidos no PoB`}</p>
      ${isGgg&&d.main_skill_inferred?'<small class="muted">A GGG não marca uma main skill; o card usa a skill com mais links apenas como preview.</small>':''}
    </div>`;
}

function renderBuildOverview(d){
  const stats=Object.entries(d.player_stats||{});
  const equipped=(d.items?.slots||[]).slice(0,8);
  const skills=(d.skills||[]).slice(0,5);
  $('buildContent').innerHTML=`
    ${d.items?.unresolved_slots?.length?`<div class="build-warning">${d.items.unresolved_slots.length} slot(s) do PoB referenciam item que o parser não resolveu. Os IDs continuam preservados para diagnóstico.</div>`:''}
    <div class="build-section-title"><h2>${d.source_type==='ggg-character'?'Snapshot da build':'Métricas gravadas no export'}</h2><span class="muted">${d.source_type==='ggg-character'?'A API da GGG fornece gear, skills e passivas; não fornece PlayerStats calculados.':'Baseline; ainda não é recálculo headless.'}</span></div>
    ${d.source_type==='ggg-character'?`<div class="build-stat-grid"><div class="build-stat"><strong>${esc(d.level||'?')}</strong><span>Level</span></div><div class="build-stat"><strong>${fmt(d.items?.count)}</strong><span>Equipamentos</span></div><div class="build-stat"><strong>${fmt(d.skill_group_count)}</strong><span>Skills</span></div><div class="build-stat"><strong>${fmt(d.tree?.allocated_nodes)}</strong><span>Passivas</span></div></div>`:`<div class="build-stat-grid">${stats.slice(0,15).map(([k,v])=>`<div class="build-stat"><strong>${esc(pobValue(v))}</strong><span>${esc(k)}</span></div>`).join('')||'<p class="muted">Sem PlayerStats reconhecidos.</p>'}</div>`}
    <div class="build-grid build-overview-grid" style="margin-top:18px">
      <div class="build-panel overview-skills"><div class="panel-game-head"><span>SKILL GEMS</span><button class="text-button" data-build-tab-jump="skills">Abrir sockets →</button></div>
        ${skills.map((g,i)=>`<div class="overview-gem-row"><strong>${esc(g.label||g.main_gem||('Grupo '+(i+1)))}</strong><div class="mini-gem-chain">${(g.gems||[]).slice(0,6).map((x,j)=>gemVisual(x,j===g.main_index)).join('')}</div></div>`).join('')||'<p class="muted">Nenhum grupo encontrado.</p>'}
      </div>
      <div class="build-panel overview-gear"><div class="panel-game-head"><span>EQUIPMENT</span><button class="text-button" data-build-tab-jump="gear">Abrir loadout + market →</button></div>
        <div class="overview-gear-strip">${equipped.map(s=>`<button data-build-tab-jump="gear" class="overview-item rarity-${rarityClass(s.item?.rarity)}">${imageFor(s.item?.base_type||gearName(s.item),s.item?.icon||'','overview-gear-art')}<span>${esc(s.slot)}</span><b>${esc(gearName(s.item))}</b></button>`).join('')||'<p class="muted">Nenhum slot ativo foi resolvido.</p>'}</div>
      </div>
      <div class="build-panel"><div class="panel-game-head"><span>PASSIVE TREE</span><button class="text-button" data-build-tab-jump="tree">Detalhes →</button></div>
        <div class="tree-overview-number">${fmt(d.tree?.allocated_nodes)}</div><p class="muted">pontos alocados</p>
        <p>Ascendência interna: <code>${esc(d.tree?.ascendancy_internal_id||'não identificada')}</code></p><p>Config entries: <b>${fmt(d.config?.count)}</b></p>
      </div>
    </div>`;
}

function renderBuildSkills(d){
  $('buildContent').innerHTML=`
    <div class="build-section-title"><div><span class="eyebrow">SOCKET GROUPS · BUILD IMPORTADA</span><h2>Skills & Support Gems</h2><p class="muted">Arte resolvida pela base do jogo quando disponível; os grupos e níveis continuam vindo da build importada.</p></div></div>
    ${buildVisuals.error?`<div class="build-warning">Ícones não puderam ser carregados agora: ${esc(buildVisuals.error)}. A build continua funcional.</div>`:''}
    <div class="game-skill-list">${(d.skills||[]).map((g,i)=>`
      <article class="game-skill-card">
        <div class="game-skill-head"><div><span class="eyebrow">GRUPO ${i+1}${g.slot?' · '+esc(g.slot):''}</span><h3>${esc(g.label||g.main_gem||('Grupo '+(i+1)))}</h3></div><button class="secondary" data-open-skill-from-pob="${esc(g.main_gem||'')}">Abrir no Finder</button></div>
        <div class="game-socket-chain">${(g.gems||[]).map((x,j)=>gemVisual(x,j===g.main_index)).join('<span class="socket-link" aria-hidden="true"></span>')}</div>
      </article>`).join('')||'<p class="muted">Nenhum grupo de skill encontrado.</p>'}</div>`;
}

function renderBuildGear(d){
  const slots=d.items?.slots||[],unresolved=d.items?.unresolved_slots||[];
  const layout=loadoutSlots(d);
  if(gearTrade.slot&&!slots.some(x=>x.slot===gearTrade.slot))gearTrade={slot:'',model:null,loading:false,error:'',result:null};
  $('buildContent').innerHTML=`
    <div class="build-section-title"><div><span class="eyebrow">IN-GAME INSPIRED LOADOUT</span><h2>Equipment & Market</h2><p class="muted">Clique em uma peça para inspecionar os mods e gerar a busca oficial do PoE2 Trade.</p></div><span class="muted">${fmt(slots.length)} equipados · ${fmt(d.items?.defined_count)} definidos</span></div>
    ${unresolved.length?`<div class="build-warning">${unresolved.map(x=>`${esc(x.slot)} → itemId ${esc(x.item_id)}`).join('<br>')}</div>`:''}
    ${buildVisuals.error?`<div class="build-warning">Algumas artes não puderam ser resolvidas: ${esc(buildVisuals.error)}. Os filtros de market continuam disponíveis.</div>`:''}
    <div class="gear-market-layout">
      <section class="poe-loadout-wrap"><div class="poe-loadout">
        ${layout.desired.map(k=>gearTile(layout.mapped.get(k),k)).join('')}
      </div>${layout.other.length?`<div class="other-equipment"><span class="eyebrow">OUTROS SLOTS</span>${layout.other.map(s=>gearTile(s,'other')).join('')}</div>`:''}
      <div class="loadout-help"><b>Market integrado</b><span>O Finder não copia o nome aleatório de itens Rare. Ele usa a base + modifiers detectados. Para Unique, o nome exato é preservado.</span></div></section>
      ${tradePanelHtml(d,slots)}
    </div>
    <details class="gear-diagnostics"><summary>Diagnóstico bruto dos itens</summary><pre class="raw-text">${esc(JSON.stringify(d.items||{},null,2))}</pre></details>`;
}


function treeKindLabel(k){
  return ({
    PASSIVE:'Passiva',NOTABLE:'Notable',KEYSTONE:'Keystone',
    JEWEL_SOCKET:'Jewel Socket',ASCENDANCY_NODE:'Ascendência',
    TREE_START:'Início',TREE_DECORATION:'Decorativo',UNRESOLVED:'Não resolvido'
  })[k]||k||'Nó';
}
function treeNodeMatches(n){
  const q=(treeView.q||'').trim().toLowerCase();
  const kind=treeView.kind||'all';
  if(kind!=='all'){
    if(kind==='specialisation'&&n.pool!=='specialisation')return false;
    else if(kind==='unresolved'&&n.resolved)return false;
    else if(!['specialisation','unresolved'].includes(kind)&&n.kind!==kind)return false;
  }
  if(!q)return true;
  const blob=[n.name,n.kind,n.ref,n.ascendancy,n.specialisation,n.summary,...(n.stats_preview||[])].join(' ').toLowerCase();
  return blob.includes(q);
}
function treeMechanicsHtml(a){
  const rows=(a?.mechanics||[]).slice(0,24);
  if(!rows.length)return '<p class="muted">Nenhuma mecânica semântica foi extraída dos pontos resolvidos.</p>';
  return `<div class="tree-mechanics">${rows.map(m=>`
    <button data-tree-topic="${esc(m.label)}" title="${esc((m.nodes||[]).join(', '))}">
      <strong>${esc(m.label)}</strong><span>${fmt(m.count)} relações</span>
    </button>`).join('')}</div>`;
}
function treeNodeCard(n){
  const cost=n.point_cost==null?'?':pobValue(n.point_cost);
  const pool=n.pool==='specialisation'?(n.specialisation?`Especialização ${n.specialisation}`:'Especialização'):'Árvore base';
  if(!n.resolved){
    return `<article class="tree-node unresolved">
      <div class="tree-node-head"><strong>${esc(n.name)}</strong><span>não resolvido</span></div>
      <p><code>${esc(n.ref)}</code></p><small>${esc(pool)}</small>
    </article>`;
  }
  return `<article class="tree-node kind-${esc(String(n.kind).toLowerCase())}">
    <div class="tree-node-head">
      <button data-inspect="${esc(n.entity_id)}">${esc(n.name)}</button>
      <span>${esc(treeKindLabel(n.kind))}</span>
    </div>
    <div class="tree-node-meta">
      <span>${esc(pool)}</span>
      <span>${esc(cost)} ponto${Number(cost)===1?'':'s'}${n.point_cost_explicit?' · custo explícito':''}</span>
      ${n.ascendancy?`<span>${esc(n.ascendancy)}</span>`:''}
    </div>
    ${(n.stats_preview||[]).length?`<ul>${n.stats_preview.slice(0,4).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:`<p class="muted">${esc(n.summary||'Sem texto traduzido disponível.')}</p>`}
    <small class="tree-ref">hash/id ${esc(n.ref)}</small>
  </article>`;
}
function renderTreeAllocatedList(){
  const box=$('treeAllocatedList');if(!box||!treeView.analysis)return;
  const rows=(treeView.analysis.nodes||[]).filter(treeNodeMatches);
  $('treeNodeResultCount').textContent=`${fmt(rows.length)} de ${fmt(treeView.analysis.nodes?.length||0)} alocações`;
  box.innerHTML=rows.map(treeNodeCard).join('')||'<div class="build-warning">Nenhum ponto corresponde a este filtro.</div>';
}
function renderTreeAnalysis(d,a){
  treeView.analysis=a;
  const b=a.breakdown||{};
  const coverage=a.references_total?`${pobValue(a.coverage_pct)}%`:'—';
  $('buildContent').innerHTML=`
    <div class="tree-build-page">
      <div class="build-section-title"><div>
        <span class="eyebrow">ÁRVORE REAL DA BUILD</span>
        <h2>Árvore & pontos</h2><button class="secondary" data-build-tab-jump="tree-sim">Testar alocação ou remoção no PoB →</button>
        <p class="muted">Hashes/IDs alocados na build são resolvidos contra a árvore RePoE. Nada é inferido pelo nome.</p>
      </div></div>

      <div class="tree-point-grid">
        <div class="tree-point-stat"><strong>${fmt(a.allocated_nodes_reported)}</strong><span>Nós reportados</span></div>
        <div class="tree-point-stat"><strong>${fmt(a.detected_point_units)}</strong><span>Pontos resolvidos</span></div>
        <div class="tree-point-stat"><strong>${fmt(a.specialisation_references)}</strong><span>Especialização</span></div>
        <div class="tree-point-stat"><strong>${fmt(b.ascendancy||0)}</strong><span>Nós de ascendência</span></div>
        <div class="tree-point-stat"><strong>${coverage}</strong><span>Cobertura RePoE</span></div>
      </div>

      <div class="build-grid tree-summary-grid">
        <div class="build-panel">
          <h3>Distribuição dos pontos resolvidos</h3>
          <div class="tree-breakdown">
            <span><b>${fmt(b.passive||0)}</b> passivas</span>
            <span><b>${fmt(b.notable||0)}</b> notables</span>
            <span><b>${fmt(b.keystone||0)}</b> keystones</span>
            <span><b>${fmt(b.jewel_socket||0)}</b> jewel sockets</span>
            <span><b>${fmt(b.ascendancy||0)}</b> ascendência</span>
          </div>
          <p class="muted">${fmt(a.resolved)} resolvidos · ${fmt(a.unresolved)} não resolvidos · tree ${esc(a.tree_version||'—')} · RePoE ${esc(a.catalog_tree_version||'—')}</p>
        </div>
        <div class="build-panel">
          <h3>Mecânicas reforçadas pelos pontos</h3>
          ${treeMechanicsHtml(a)}
        </div>
        <div class="build-panel">
          <h3>Quest / origem</h3>
          <p><b>${fmt(a.base_references)}</b> referências da árvore base</p>
          <p><b>${fmt(a.specialisation_references)}</b> referências de especialização</p>
          <p><b>${fmt((a.quest_stats||[]).length)}</b> registros de quest stats preservados</p>
          <p class="muted">O Finder não calcula pontos restantes sem uma fonte explícita para evitar inventar total disponível.</p>
        </div>
      </div>

      <section class="tree-allocated-section">
        <div class="tree-allocated-head">
          <div><span class="eyebrow">PONTOS ALOCADOS</span><h3>Passivas da build</h3><span id="treeNodeResultCount" class="muted"></span></div>
          <div class="tree-allocated-controls">
            <input id="treeAllocatedSearch" value="${esc(treeView.q)}" placeholder="Buscar nos pontos alocados…">
            <select id="treeAllocatedKind">
              <option value="all" ${treeView.kind==='all'?'selected':''}>Todos</option>
              <option value="PASSIVE" ${treeView.kind==='PASSIVE'?'selected':''}>Passivas</option>
              <option value="NOTABLE" ${treeView.kind==='NOTABLE'?'selected':''}>Notables</option>
              <option value="KEYSTONE" ${treeView.kind==='KEYSTONE'?'selected':''}>Keystones</option>
              <option value="JEWEL_SOCKET" ${treeView.kind==='JEWEL_SOCKET'?'selected':''}>Jewel sockets</option>
              <option value="ASCENDANCY_NODE" ${treeView.kind==='ASCENDANCY_NODE'?'selected':''}>Ascendência</option>
              <option value="specialisation" ${treeView.kind==='specialisation'?'selected':''}>Especialização</option>
              <option value="unresolved" ${treeView.kind==='unresolved'?'selected':''}>Não resolvidos</option>
            </select>
          </div>
        </div>
        <div id="treeAllocatedList" class="tree-node-list"></div>
      </section>

      <details class="tree-notes">
        <summary>Como os pontos são contados</summary>
        ${(a.notes||[]).map(x=>`<p>${esc(x)}</p>`).join('')}
        ${a.explicit_multi_point_units?`<p>Metadados da árvore declararam ${esc(pobValue(a.explicit_multi_point_units))} unidades de custo explicitamente.</p>`:''}
      </details>
    </div>`;
  renderTreeAllocatedList();
}
async function renderBuildTree(d){
  $('buildContent').innerHTML='<div class="build-panel"><strong>Resolvendo a árvore da build…</strong><p class="muted">Cruzando hashes/IDs alocados com a base RePoE.</p></div>';
  try{
    const a=await api('/api/build/tree-analysis');
    renderTreeAnalysis(d,a);
  }catch(e){
    $('buildContent').innerHTML=`<div class="build-warning"><strong>Não foi possível resolver a árvore.</strong><br>${esc(e.message)}</div>`;
  }
}


function checkCard(key,label,entry){
  const ok=!!entry?.ok;
  return `<div class="engine-check ${ok?'ok':'bad'}">
    <div class="engine-check-head"><span>${ok?'✓':'!'}</span><strong>${esc(label)}</strong></div>
    <div class="engine-check-path">${esc(entry?.path||'não encontrado')}</div>
    <div class="muted">${esc(entry?.detail||'')}</div>
  </div>`;
}

function renderEngineSetup(setup, runtimeStatus){
  const c=setup?.checks||{};
  $('engineSetupChecks').innerHTML=
    checkCard('luajit','LuaJIT 2.1',c.luajit)+
    checkCard('pob_src','Arquivos do PoB2',c.pob_src)+
    checkCard('pob_syntax','Compatibilidade LuaJIT',c.pob_syntax)+
    checkCard('runtime','Runtime / DLLs',c.runtime)+
    checkCard('bridge','Bridge stdio',c.bridge);

  $('engineLuaPath').value=setup?.config?.luajit_path||'';
  $('enginePobPath').value=setup?.config?.pob_src_path||'';
  $('engineRuntimePath').value=setup?.config?.runtime_dll_path||'';
  $('engineBridgePath').value=setup?.config?.bridge_path||'';

  const running=!!runtimeStatus?.running;
  $('engineState').className='engine-state '+(running?'running':setup?.ready?'ready':'not-ready');
  const repaired=(setup?.repaired_paths||[]).map(x=>({pob_src_path:'PoB2 / programa',runtime_dll_path:'runtime',bridge_path:'bridge'}[x]||x));
  const repairNote=repaired.length?`<div class="engine-repair-note">✓ Caminhos reparados automaticamente após mover a pasta: ${esc(repaired.join(', '))}.</div>`:'';
  $('engineState').innerHTML=(running
    ? `<strong>Motor PoB ativo ✓</strong><div class="muted">PID ${esc(runtimeStatus.pid||'')} · pronto para recalcular a build.</div>`
    : setup?.ready
      ? `<strong>Ambiente pronto</strong><div class="muted">Todos os componentes necessários foram encontrados. Clique em Iniciar motor.</div>`
      : `<strong>Configuração incompleta</strong><div class="muted">Use “Detectar / reparar caminhos”. Se o checkout antigo não existir mais, “Baixar PoB2 headless estável” reinstala o motor em uma pasta que não depende da localização deste projeto.</div>`)+repairNote;

  $('engineStart').disabled=running||!setup?.ready;
  $('engineStop').disabled=!running;
  $('engineLoadCurrent').disabled=!running||!currentPobBuild;
}

async function refreshEngineSetup(){
  const [setup,status]=await Promise.all([
    api('/api/pob/engine/setup'),
    api('/api/pob/engine/status')
  ]);
  renderEngineSetup(setup,status);
  return {setup,status};
}


function supportAttrClass(g){
  const a=g?.attributes||[];
  if(g?.attribute==='STR'||(a.length===1&&a[0]==='STR'))return 'attr-str';
  if(g?.attribute==='DEX'||(a.length===1&&a[0]==='DEX'))return 'attr-dex';
  if(g?.attribute==='INT'||(a.length===1&&a[0]==='INT'))return 'attr-int';
  if(g?.attribute==='HYBRID'||a.length>1)return 'attr-hybrid';
  return 'attr-none';
}
function engineGroupLabel(g){
  const m=(g?.gems||[]).find(x=>x.isSupport!==true);
  return g?.label||m?.name||`Grupo ${g?.index||'?'}`;
}
function selectedGroup(){
  return linker.context?.skills?.groups?.find(g=>Number(g.index)===Number(linker.groupIndex))||null;
}
function currentGroupSupports(g){return (g?.gems||[]).filter(x=>x.isSupport===true).map(x=>x.name);}
function supportInfo(name){return linker.context?.supports?.find(x=>x.name===name)||{name,attribute:'NONE',attributes:[]};}
function linkerMetricLabel(k){return ({
  TotalDPS:'DPS total',FullDPS:'Full DPS',CombinedDPS:'DPS combinado',SkillDPS:'Skill DPS',
  AverageDamage:'Dano médio',WithDotDPS:'DPS com DoT',TotalDotDPS:'DoT DPS',IgniteDPS:'Ignite DPS',
  Speed:'Velocidade',HitSpeed:'Hits/s',CastSpeed:'Cast speed',CastTime:'Tempo de cast',
  Cooldown:'Cooldown',CooldownTime:'Cooldown',SkillCooldown:'Cooldown da skill',
  Duration:'Duração',DurationSecondary:'Duração secundária',DurationTertiary:'Duração terciária',SkillDuration:'Duração da skill',
  AreaOfEffectMod:'Mod de área',AreaOfEffectModSecondary:'Mod de área secundária',AreaOfEffectModTertiary:'Mod de área terciária',
  AreaOfEffectRadiusMetres:'Raio AoE (m)',AreaOfEffectRadiusSecondaryMetres:'Raio secundário (m)',
  AreaOfEffectRadiusTertiaryMetres:'Raio terciário (m)',ProjectileCount:'Projéteis',ProjectileSpeedMod:'Velocidade de projétil',BounceCount:'Bounces',
  ManaCost:'Custo de mana',LifeCost:'Custo de vida',
  CritChance:'Crítico',HitChance:'Chance de acerto',IgniteChance:'Chance de Ignite',
  IgniteDuration:'Duração do Ignite',Life:'Vida',EnergyShield:'ES',Mana:'Mana',Spirit:'Spirit',
  Armour:'Armour',Evasion:'Evasion'
})[k]||k;}
function metricScopeLabel(r){
  if(r?.scope==='native')return 'POB · CALCULATOR';
  return r?.scope==='skill'?'SKILL · CALCS':'PERSONAGEM · MAIN';
}
function metricClass(r){
  if(!r.changed)return 'same';
  const low=/Cooldown|CastTime|ManaCost|LifeCost|RageCost/.test(r.key);
  return (low?r.delta<0:r.delta>0)?'better':'worse';
}
function deltaText(r){
  if(!r.changed)return 'sem mudança';
  const raw=(r.delta>0?'+':'')+pobValue(r.delta);
  if(r.pct===null||r.pct===undefined)return raw;
  return `${raw} (${r.pct>0?'+':''}${Number(r.pct).toLocaleString('pt-BR',{maximumFractionDigits:1})}%)`;
}
function selectedSlotsHtml(){
  const slots=[...linker.selected];while(slots.length<5)slots.push(null);
  return `<div class="linker-slots">${slots.map((n,i)=>n?`<div class="linker-slot filled ${supportAttrClass(supportInfo(n))}">
    <span class="slot-number">${i+1}</span><strong>${esc(n)}</strong><button data-linker-remove="${i}">×</button>
  </div>`:`<div class="linker-slot empty"><span class="slot-number">${i+1}</span><span>slot vazio</span></div>`).join('')}</div>`;
}
function filteredSupports(){
  const q=linker.query.trim().toLowerCase(),sel=new Set(linker.selected);
  return (linker.context?.supports||[]).filter(s=>!sel.has(s.name))
    .filter(s=>!q||s.name.toLowerCase().includes(q)||String(s.tags||'').toLowerCase().includes(q)||(s.tagKeys||[]).some(t=>String(t).toLowerCase().includes(q)))
    .slice(0,120);
}
function supportBrowserHtml(){return `<div class="linker-browser">
  <input id="linkerSearch" value="${esc(linker.query)}" placeholder="Buscar entre os supports que o PoB aceita para esta skill…">
  <div class="linker-support-list">${filteredSupports().map(s=>`<button class="linker-support ${supportAttrClass(s)}" data-linker-add="${esc(s.name)}" ${linker.selected.length>=5?'disabled':''}>
    <strong>${esc(s.name)}</strong><small>${esc((s.tagKeys||[]).slice(0,5).join(' · ')||s.tags||'support')}</small></button>`).join('')||'<p class="muted">Nenhum support encontrado.</p>'}</div>
</div>`;}

function pipelineRows(detail){
  const sets=detail?.statSets||[];
  const constants=sets.flatMap(s=>(s.constantStats||[]).map(x=>({...x,set:s.index,label:s.label})));
  const built=sets.flatMap(s=>(s.builtStats||[]).map(x=>({...x,set:s.index,label:s.label})));
  const mapKeys=[...new Set(sets.flatMap(s=>s.statMapKeys||[]))].sort();
  const mods=detail?.mergedMods||[];
  return {constants,built,mapKeys,mods};
}
function aoePipeline(detail){
  const p=pipelineRows(detail);
  const key='base_skill_area_of_effect_+%';
  const raw=p.constants.find(x=>x.key===key);
  const built=p.built.find(x=>x.key===key);
  const mapped=p.mapKeys.includes(key);
  const merged=p.mods.find(x=>x.name==='AreaOfEffect');
  return {raw,built,mapped,merged};
}
function pipelineBadge(label,ok,value=''){
  return `<span class="pipeline-badge ${ok?'ok':'miss'}"><b>${esc(label)}</b>${value!==''?` ${esc(String(value))}`:''}</span>`;
}
function supportPipelineCard(detail,highlight=false){
  const p=pipelineRows(detail),aoe=aoePipeline(detail);
  const hasAoe=Boolean(aoe.raw||aoe.built||aoe.mapped||aoe.merged);
  const importantConstants=p.constants.filter(x=>/area|duration|cooldown|damage|projectile|speed/i.test(x.key));
  const importantBuilt=p.built.filter(x=>/area|duration|cooldown|damage|projectile|speed/i.test(x.key));
  const importantMods=p.mods.filter(x=>/area|duration|cooldown|damage|projectile|speed/i.test(x.name||''));
  return `<article class="pipeline-card ${highlight?'highlight':''}">
    <div class="pipeline-title"><strong>${esc(detail?.name||'?')}</strong><code>${esc(detail?.id||'sem grantedEffect id')}</code></div>
    <p class="muted">level ${esc(String(detail?.level??'—'))} · quality ${esc(String(detail?.quality??'—'))} · ${esc(detail?.gemId||'')}</p>
    ${hasAoe?`<div class="pipeline-stages">
      ${pipelineBadge('RAW',Boolean(aoe.raw),aoe.raw?.value??'—')}
      ${pipelineBadge('BUILT',Boolean(aoe.built),aoe.built?.value??'—')}
      ${pipelineBadge('MAP',aoe.mapped,aoe.mapped?'presente':'ausente')}
      ${pipelineBadge('MERGED',Boolean(aoe.merged),aoe.merged?`${aoe.merged.type||''} ${aoe.merged.value??''}`:'ausente')}
    </div>`:''}
    <div class="pipeline-columns">
      <div><span>constantStats</span><pre>${esc(JSON.stringify(importantConstants.length?importantConstants:p.constants,null,2))}</pre></div>
      <div><span>buildSkillInstanceStats</span><pre>${esc(JSON.stringify(importantBuilt.length?importantBuilt:p.built,null,2))}</pre></div>
      <div><span>mergeSkillInstanceMods</span><pre>${esc(JSON.stringify(importantMods.length?importantMods:p.mods,null,2))}</pre></div>
    </div>
    <details><summary>statMap keys e JSON completo</summary><pre class="raw-text">${esc(JSON.stringify({statMapKeys:p.mapKeys,detail},null,2))}</pre></details>
  </article>`;
}
function supportPipelineHtml(r){
  const details=r?.variant_skill_probe?.supportDetails||[];
  if(!details.length)return '<p class="muted">O CALCULATOR não retornou detalhes dos supports.</p>';
  const added=new Set((r.added_supports||[]).map(x=>String(x).toLowerCase()));
  const sorted=[...details].sort((a,b)=>{
    const ah=added.has(String(a.name||'').toLowerCase())?0:1;
    const bh=added.has(String(b.name||'').toLowerCase())?0:1;
    return ah-bh||String(a.name||'').localeCompare(String(b.name||''));
  });
  return `<div class="support-pipeline">${sorted.map(d=>supportPipelineCard(d,added.has(String(d.name||'').toLowerCase()))).join('')}</div>`;
}

function resultHtml(){
  const r=linker.result;if(!r)return '';
  const ch=(r.metrics||[]).filter(x=>x.changed),stable=(r.metrics||[]).filter(x=>!x.changed);
  const rejectedSet=new Set((r.rejected_supports||[]).map(x=>String(x).toLowerCase()));
  const sem=(r.semantics||[]).map(s=>`<article class="interaction-card ${rejectedSet.has(String(s.name).toLowerCase())||s.compatibility?.status==='incompatible'?'conflict':''}">
    <div class="interaction-head"><strong>${esc(s.name)}</strong><span>${rejectedSet.has(String(s.name).toLowerCase())?'PoB rejeitou':esc(s.compatibility?.label||'')}</span></div>
    ${s.summary?`<p>${esc(s.summary)}</p>`:''}<p class="muted">${esc(s.compatibility?.reason||'')}</p>
    ${(s.links||[]).length?`<div class="interaction-links">${s.links.slice(0,12).map(l=>`<span class="interaction-pill">${esc(rel(l.relation))} · ${esc(l.label||l.concept||'')}</span>`).join('')}</div>`:'<p class="muted">Sem relação semântica específica extraída na base atual.</p>'}
  </article>`).join('');
  const rejected=r.rejected_supports||[];
  const validity=rejected.length
    ? `<div class="build-warning invalid-variant"><strong>PoB rejeitou ${esc(rejected.join(', '))} para ${esc(r.main_skill||'esta skill')}.</strong><br>As métricas abaixo representam somente os supports realmente aplicados. Esta combinação não é um setup válido.</div>`
    : `<div class="build-ok"><strong>Variante válida e calculada pelo PoB ✓</strong><br><span class="muted">Todos os supports selecionados foram aceitos pelo motor. O XML original foi restaurado depois do teste.</span></div>`;
  return `<section class="linker-result">${validity}
    <div class="linker-diff-summary"><div><span>Removidos</span><strong>${esc((r.removed_supports||[]).join(', ')||'nenhum')}</strong></div><div><span>Adicionados</span><strong>${esc((r.added_supports||[]).join(', ')||'nenhum')}</strong></div></div>
    <h3>Métricas que mudaram</h3><div class="metric-compare-grid">${ch.map(x=>`<div class="metric-compare ${metricClass(x)}"><span>${esc(linkerMetricLabel(x.key))}</span><em class="metric-scope">${esc(metricScopeLabel(x))}</em><div><b>${esc(pobValue(x.before))}</b><i>→</i><b>${esc(pobValue(x.after))}</b></div><small>${esc(deltaText(x))}</small></div>`).join('')||'<div class="build-warning">O PoB aceitou a variante, mas nenhum valor escalar mudou no CALCULATOR nativo. Abra o diagnóstico abaixo para conferir modifiers e effectList.</div>'}</div>
    ${stable.length?`<details><summary>Métricas de referência sem mudança (${stable.length})</summary></details>`:''}
    ${r.output_diagnostics?`<details class="output-diagnostics"><summary>Diagnóstico do cálculo nativo do PoB</summary>
      <p class="muted">CALCULATOR: ${r.output_diagnostics.baseline_native_scalars} → ${r.output_diagnostics.variant_native_scalars} valores escalares · support effects: ${r.output_diagnostics.baseline_support_effects} → ${r.output_diagnostics.variant_support_effects}</p>
      <div class="native-probe-grid">
        <div><span>Área INC</span><b>${esc(pobValue(r.baseline_skill_probe?.areaInc))} → ${esc(pobValue(r.variant_skill_probe?.areaInc))}</b></div>
        <div><span>Área primária INC</span><b>${esc(pobValue(r.baseline_skill_probe?.areaPrimaryInc))} → ${esc(pobValue(r.variant_skill_probe?.areaPrimaryInc))}</b></div>
        <div><span>Área secundária INC</span><b>${esc(pobValue(r.baseline_skill_probe?.areaSecondaryInc))} → ${esc(pobValue(r.variant_skill_probe?.areaSecondaryInc))}</b></div>
        <div><span>Área terciária INC</span><b>${esc(pobValue(r.baseline_skill_probe?.areaTertiaryInc))} → ${esc(pobValue(r.variant_skill_probe?.areaTertiaryInc))}</b></div>
        <div><span>Duration INC</span><b>${esc(pobValue(r.baseline_skill_probe?.durationInc))} → ${esc(pobValue(r.variant_skill_probe?.durationInc))}</b></div>
        <div><span>Cooldown Recovery INC</span><b>${esc(pobValue(r.baseline_skill_probe?.cooldownRecoveryInc))} → ${esc(pobValue(r.variant_skill_probe?.cooldownRecoveryInc))}</b></div>
      </div>
      <p class="muted">Supports aplicados pelo effectList: ${esc((r.applied_supports||[]).join(', ')||'nenhum')}</p>
      <details class="mod-source-details"><summary>Fontes dos modifiers de Area of Effect</summary>
        <pre class="raw-text">${esc(JSON.stringify({antes:r.baseline_skill_probe?.areaMods||[],depois:r.variant_skill_probe?.areaMods||[]},null,2))}</pre>
      </details>
      <details class="support-pipeline-details" open><summary>Pipeline interno dos supports · RAW → BUILT → MAP → MERGED</summary>
        <p class="muted">RAW = constantStats do grantedEffect · BUILT = buildSkillInstanceStats · MAP = statMap do statSet · MERGED = mods produzidos por mergeSkillInstanceMods.</p>
        ${supportPipelineHtml(r)}
      </details>
      <p class="muted">${esc(r.native_calculator||'')}</p>
    </details>`:''}
    <h3>Interações e condições detectadas</h3><div class="interaction-grid">${sem||'<p class="muted">Sem contexto semântico local.</p>'}</div>
  </section>`;
}
async function refreshCompatibleSupports(){
  linker.compatLoading=true;
  try{
    const res=await api('/api/pob/engine/compatible-supports',{
      groupIndex:Number(linker.groupIndex)
    });
    linker.compat=res;
    linker.context.supports=res.supports||[];
  }finally{
    linker.compatLoading=false;
  }
}
async function loadVirtualContext(force=false){
  if(!linker.context||force){
    linker.context=await api('/api/pob/engine/virtual');
  }
  const groups=linker.context?.skills?.groups||[];
  if(!groups.length)throw new Error('PoB não retornou grupos de skills.');
  if(!linker.groupIndex||!groups.some(g=>Number(g.index)===Number(linker.groupIndex))){
    linker.groupIndex=(groups.find(g=>(g.gems||[]).some(x=>x.isSupport!==true&&x.name==='Oil Grenade'))||groups[0]).index;
  }
  linker.selected=currentGroupSupports(selectedGroup()).slice(0,5);
  linker.result=null;
  await refreshCompatibleSupports();
}
function renderVirtualBody(){
  const groups=linker.context?.skills?.groups||[],g=selectedGroup(),active=(g?.gems||[]).find(x=>x.isSupport!==true);
  $('buildContent').innerHTML=`<div class="linker-page"><div class="build-section-title"><div><span class="eyebrow">POB VIRTUAL EXPERIMENT</span><h2>Virtual Linker · até 5 supports</h2><p class="muted">A lista vem do próprio PoB. Cada teste é feito em memória e o baseline é restaurado.</p></div></div>
    <div class="linker-top"><label>Skill / grupo real do PoB<select id="linkerGroup">${groups.map(x=>`<option value="${x.index}" ${Number(x.index)===Number(linker.groupIndex)?'selected':''}>${esc(engineGroupLabel(x))} · grupo ${x.index}</option>`).join('')}</select></label><button id="linkerReset" class="secondary">Supports atuais</button></div>
    <div class="linker-current"><span class="eyebrow">ACTIVE SKILL</span><h3>${esc(active?.name||engineGroupLabel(g))}</h3>
      <p class="muted">Atual: ${esc(currentGroupSupports(g).join(', ')||'nenhum')}</p>
      <div class="pob-compat-badge">✓ Lista filtrada pelo motor real do PoB · ${linker.context?.supports?.length||0} supports compatíveis</div>
    </div>
    ${selectedSlotsHtml()}${supportBrowserHtml()}
    <div class="linker-actions"><button id="linkerAnalyze" class="primary">Analisar variante no PoB</button><span class="muted">${linker.selected.length}/5 supports</span></div>
    <div id="linkerResult">${resultHtml()}</div></div>`;
}
async function renderVirtualLinker(){
  $('buildContent').innerHTML='<div class="build-panel"><strong>Preparando Virtual Linker…</strong></div>';
  try{
    const st=await api('/api/pob/engine/status');
    if(!st.running){$('buildContent').innerHTML='<div class="build-warning"><strong>Motor PoB não está ativo.</strong><br>Inicie o motor e volte para esta aba.<br><button class="secondary" data-build-tab-jump="engine">Ir para Motor PoB</button></div>';return;}
    await loadVirtualContext();renderVirtualBody();
  }catch(e){$('buildContent').innerHTML=`<div class="build-warning">${esc(e.message)}</div>`;}
}
async function linkerAnalyze(){
  const b=$('linkerAnalyze');if(b){b.disabled=true;b.textContent='PoB recalculando…';}
  try{linker.result=await api('/api/pob/engine/compare-supports',{groupIndex:Number(linker.groupIndex),supports:linker.selected});renderVirtualBody();$('linkerResult')?.scrollIntoView({behavior:'smooth'});}
  catch(e){notify(e.message,true);}
}

function renderBuildEngine(){
  $('buildContent').innerHTML=`
    <div class="engine-page">
      <div class="build-section-title">
        <div>
          <span class="eyebrow">POB2 HEADLESS · STDIO JSON</span>
          <h2>Motor real do Path of Building</h2>
          <p class="muted">O Synergy Finder inicia o PoB headless como processo local e conversa diretamente com ele. Não existe servidor HTTP externo.</p>
        </div>
      </div>

      <div id="engineState" class="engine-state"><strong>Verificando…</strong></div>

      <h3>Diagnóstico</h3>
      <div id="engineSetupChecks" class="engine-check-grid"></div>

      <div class="engine-actions">
        <button id="engineDetect" class="secondary">Detectar / reparar caminhos</button>
        <button id="engineInstallPob" class="secondary">Baixar PoB2 headless estável</button>
        <button id="engineInstallBridge" class="secondary">Baixar bridge stdio</button>
        <button id="engineStart" class="primary">Iniciar motor PoB</button>
        <button id="engineStop" class="secondary">Parar motor</button>
      </div>

      <details class="engine-config-detail">
        <summary>Configuração manual de caminhos</summary>
        <div class="engine-path-form">
          <label>LuaJIT.exe<input id="engineLuaPath" placeholder="C:\\...\\luajit.exe"></label>
          <label>PoB2 / programa ou src<input id="enginePobPath" placeholder="%APPDATA%\\Path of Building Community (PoE2) ou ...\\PathOfBuilding-PoE2\\src"></label>
          <label>Runtime / DLLs<input id="engineRuntimePath" placeholder="C:\\...\\runtime ou %APPDATA%\\Path of Building Community (PoE2)"></label>
          <label>Bridge<input id="engineBridgePath" placeholder="...\\engine\\pob-api"></label>
          <button id="engineSavePaths" class="secondary">Salvar caminhos</button>
        </div>
      </details>

      <div class="divider"></div>
      <h3>Build atual</h3>
      <p class="muted">Quando o motor estiver ativo, este botão carrega o XML da build importada e pede ao próprio PoB os stats, skills, itens, árvore e configuração calculados.</p>
      <button id="engineLoadCurrent" class="primary">Carregar build e recalcular</button>
      <div id="engineCalcResult" class="engine-calc-result"></div>
    </div>`;
  refreshEngineSetup().catch(e=>notify(e.message,true));
}

async function engineDetect(){
  try{
    const setup=await api('/api/pob/engine/detect',{});
    const status=await api('/api/pob/engine/status');
    renderEngineSetup(setup,status);
    notify(setup.ready?'Ambiente PoB detectado e pronto.':'Detecção concluída; ainda há componentes faltando. Se Runtime estiver verde e Arquivos do PoB2 vermelho, a instalação pode estar incompleta; use Baixar PoB2 headless estável.',!setup.ready);
  }catch(e){notify(e.message,true);}
}
async function engineInstallPob(){
  $('engineInstallPob').disabled=true;
  $('engineInstallPob').textContent='Baixando PoB2 estável…';
  try{
    const setup=await api('/api/pob/engine/install-pob',{});
    const status=await api('/api/pob/engine/status');
    renderEngineSetup(setup,status);
    notify('Checkout oficial estável do PoB2 baixado. Git não foi necessário.');
  }catch(e){
    notify(e.message,true);
  }finally{
    if($('engineInstallPob')){
      $('engineInstallPob').disabled=false;
      $('engineInstallPob').textContent='Baixar PoB2 headless estável';
    }
  }
}
async function engineInstallBridge(){
  $('engineInstallBridge').disabled=true;$('engineInstallBridge').textContent='Baixando…';
  try{
    const setup=await api('/api/pob/engine/install-bridge',{});
    const status=await api('/api/pob/engine/status');
    renderEngineSetup(setup,status);
    notify('Bridge stdio baixado das fontes upstream.');
  }catch(e){notify(e.message,true);}
  finally{$('engineInstallBridge').disabled=false;$('engineInstallBridge').textContent='Baixar bridge stdio';}
}
async function engineSavePaths(){
  try{
    const setup=await api('/api/pob/engine/config',{
      luajit_path:$('engineLuaPath').value,
      pob_src_path:$('enginePobPath').value,
      runtime_dll_path:$('engineRuntimePath').value,
      bridge_path:$('engineBridgePath').value
    });
    const status=await api('/api/pob/engine/status');
    renderEngineSetup(setup,status);
    notify('Caminhos salvos.');
  }catch(e){notify(e.message,true);}
}
async function engineStart(){
  $('engineStart').disabled=true;$('engineStart').textContent='Iniciando…';
  try{
    const status=await api('/api/pob/engine/start',{});
    renderEngineSetup(status.setup,status);
    notify('Motor PoB headless iniciado.');
  }catch(e){
    notify(e.message,true);
    await refreshEngineSetup().catch(()=>{});
  }finally{
    if($('engineStart'))$('engineStart').textContent='Iniciar motor PoB';
  }
}
async function engineStop(){
  try{
    await api('/api/pob/engine/stop',{});
    await refreshEngineSetup();
    notify('Motor PoB parado.');
  }catch(e){notify(e.message,true);}
}
function renderEngineSnapshot(d){
  const stats=Object.entries(d?.stats||{}).filter(([k])=>k!=='_meta');
  $('engineCalcResult').innerHTML=`
    <div class="build-ok"><strong>Recalculado pelo motor real do PoB ✓</strong><br><span class="muted">Estes números vieram do mainOutput do PoB, não de fórmulas do Synergy Finder.</span></div>
    <div class="build-stat-grid">${stats.map(([k,v])=>`<div class="build-stat"><strong>${esc(pobValue(v))}</strong><span>${esc(k)}</span></div>`).join('')}</div>
    <details style="margin-top:12px"><summary>Resposta completa do engine</summary><pre class="raw-text">${esc(JSON.stringify(d,null,2))}</pre></details>`;
}
async function engineLoadCurrent(){
  $('engineLoadCurrent').disabled=true;$('engineLoadCurrent').textContent='Recalculando…';
  try{
    const d=await api('/api/pob/engine/load',{});
    renderEngineSnapshot(d);
    notify('Build recalculada pelo PoB headless.');
  }catch(e){
    $('engineCalcResult').innerHTML=`<div class="build-warning"><strong>Falha no recálculo</strong><br>${esc(e.message)}</div>`;
    notify(e.message,true);
  }finally{
    $('engineLoadCurrent').disabled=false;$('engineLoadCurrent').textContent='Carregar build e recalcular';
  }
}


function renderCurrentBuild(){
  const d=currentPobBuild;
  if(!d||d.imported===false){
    $('buildContent').innerHTML='<div class="build-warning">Nenhuma build PoB importada.</div>';
    return;
  }
  renderBuildHero(d);
  const visualMode=buildTab==='tree-map'||buildTab==='calcs';
  $('buildWorkspace').classList.toggle('wb-active',visualMode);
  $('buildHero').hidden=visualMode;
  document.querySelectorAll('[data-build-tab]').forEach(
    b=>b.classList.toggle('active',b.dataset.buildTab===buildTab)
  );
  if(buildTab==='overview')renderBuildOverview(d);
  else if(buildTab==='skills')renderBuildSkills(d);
  else if(buildTab==='gear')renderBuildGear(d);
  else if(buildTab==='tree')renderBuildTree(d);
  else if(buildTab==='tree-map'||buildTab==='calcs'){
    if(d.has_pob_xml===false)$('buildContent').innerHTML='<div class="build-warning">Esta seção usa o motor PoB e precisa de um XML PoB. A lista da árvore e os equipamentos do snapshot GGG continuam disponíveis.</div>';
    else if(buildTab==='tree-map')renderVisualTree();else renderDetailedCalcs();
  }
  else if(buildTab==='tree-sim')renderTreeSimulator();
  else if(buildTab==='virtual'){
    if(d.has_pob_xml===false)$('buildContent').innerHTML='<div class="build-warning"><strong>Virtual Linker numérico ainda requer XML PoB.</strong><br>Esta build GGG já pode ser explorada em Skills, Gear, Árvore e Finder. A conversão GGG → modelo calculável do PoB fica separada para não inventarmos dados.</div>';
    else renderVirtualLinker();
  }else{
    if(d.has_pob_xml===false)$('buildContent').innerHTML='<div class="build-warning"><strong>Snapshot GGG carregado sem XML PoB.</strong><br>O motor headless não será alimentado com uma conversão aproximada. Equipamentos, skills e passivas continuam disponíveis diretamente no Finder.</div>';
    else renderBuildEngine(d);
  }
  if(['overview','skills','gear'].includes(buildTab))ensureBuildVisuals(d);
}

async function refreshCurrentPob(){
  try{
    const d=await api('/api/pob/current');
    currentPobBuild=d?.imported===false?null:d;
    $('openCurrentBuild').hidden=!currentPobBuild;
    if(currentPobBuild){
      $('openCurrentBuild').textContent=
        `Build atual · Lv${currentPobBuild.level||'?'} ${currentPobBuild.ascendancy||currentPobBuild.class_name||''}`;
    }
    return currentPobBuild;
  }catch(e){
    currentPobBuild=null;
    $('openCurrentBuild').hidden=true;
    return null;
  }
}

async function openCurrentBuild(){
  if(!currentPobBuild)await refreshCurrentPob();
  if(!currentPobBuild){
    await openPob();
    return;
  }
  setAppMode('build');
  renderCurrentBuild();
}

async function openPobSkillInFinder(name){
  if(!name)return;
  setAppMode('finder');
  try{
    const d=await api('/api/skills?q='+encodeURIComponent(name));
    const results=d.results||[];
    const exact=results.find(x=>x.name.toLowerCase()===name.toLowerCase())||results[0];
    if(!exact){
      notify(`Não encontrei "${name}" na base RePoE importada.`,true);
      return;
    }
    await selectSkill(exact.id);
    window.scrollTo({top:0,behavior:'smooth'});
    notify(`${name} aberto no Finder usando a skill da sua build PoB.`);
  }catch(e){
    notify(e.message,true);
  }
}


function tagsHtml(tags){return tags.map(t=>`<button class="tag" data-tag="${esc(t)}" title="Filtrar pela tag ${esc(t)}">${esc(t)}</button>`).join('');}
function rawNotice(e){return e.availability==='released'?'':`<div class="availability">Estado na fonte: ${esc(e.availability||'não informado')}</div>`;}
async function refreshStatus(){
  status=await api('/api/status');await refreshCurrentPob();$('appVersion').textContent='v'+status.app_version;
  $('dataLabel').textContent=status.entities?`${fmt(status.entities)} entidades · v${status.app_version}`:'Nenhuma base importada';
  const nonFinder=!$('buildWorkspace').hidden||!$('buildLibraryWorkspace').hidden;
  $('welcome').hidden=nonFinder||status.entities>0;$('workspace').hidden=nonFinder||!status.entities;
  $('sourceSummary').textContent=`${fmt(status.counts.SKILL)} skills · ${fmt(status.counts.META)} meta · ${fmt(status.counts.SUPPORT)} supports · ${fmt(status.tree_import?.diagnostics?.nodes)} nós da árvore`;
  renderAscendancies();
  const warnings=[...(status.source_warnings||[])];if(status.entities&&!status.tree_import?.imported_at)warnings.push('Árvore e ascendências ainda não importadas. Abra Base de dados → Baixar só árvore + ascendências.');
  $('sourceWarnings').hidden=!warnings.length;$('sourceWarnings').textContent=warnings.join(' ');
  if(status.entities && !state.skill){await loadSkills();const s=await api('/api/skills?q=Flameblast');const initial=s.results.find(e=>e.name==='Flameblast');if(initial)await selectSkill(initial.id);else {renderAnchor();await explore();}}
  else if(status.entities){await loadSkills();if(state.skill)await selectSkill(state.skill.id);else await explore();}
}
async function loadSkills(){
  const ticket=++skillTicket;
  try{const d=await api('/api/skills?q='+encodeURIComponent($('skillSearch').value.trim()));if(ticket!==skillTicket)return;
    $('skillCount').textContent=fmt(d.total)+' encontradas';
    $('skillResults').innerHTML=d.results.map(e=>`<button class="skill-button ${state.skill?.id===e.id?'active':''}" data-skill="${esc(e.id)}" data-attr="${esc(e.color)}"><strong>${esc(e.name)}</strong><small>${esc(kind(e.kind))} · ${esc(e.attribute)} · ${e.tags.length} tags</small></button>`).join('')||'<p class="muted">Nenhuma skill encontrada.</p>';
  }catch(e){notify(e.message,true);}
}
async function selectSkill(id){
  const ticket=++anchorTicket;
  try{const e=await api('/api/entity?id='+encodeURIComponent(id));if(ticket!==anchorTicket)return;
    state.skill=e;state.component=e.components[0]?.id||'';state.offset=0;renderAnchor();await loadSkills();await explore();
  }catch(e){notify(e.message,true);}
}
function renderAnchor(){
  const s=state.skill;
  $('compatMode').disabled=!s;
  if(!s){$('anchor').innerHTML='<span class="eyebrow">BUSCA SEM SKILL FIXA</span><h1>Explore as mecânicas do catálogo.</h1><p class="muted">Busque um termo nos nomes, tags, descrições, regras e stats. Selecione uma skill à esquerda para cruzar compatibilidade de supports.</p>';return;}
  const c=s.components.find(x=>x.id===state.component)||s.components[0];
  $('anchor').innerHTML=`<div class="anchor-top"><div><span class="eyebrow">${esc(kind(s.kind))} · ${esc(s.attribute)}</span><h1>${esc(s.name)}</h1><p class="muted">Fonte: RePoE · ${s.components.length} efeito(s) concedido(s) · regras por efeito, sem misturar os tipos</p></div><button class="secondary" data-inspect="${esc(s.id)}">Ver dados da skill</button></div><div class="tags">${tagsHtml(s.tags)}</div>${s.summary?`<p class="skill-description">${esc(s.summary)}</p>`:''}${rawNotice(s)}
  ${s.components.length>1?`<div class="component-row"><label for="componentSelect">Efeito usado na compatibilidade</label><select id="componentSelect">${s.components.map((e,i)=>`<option value="${esc(e.id)}" ${e.id===state.component?'selected':''}>${i+1}. ${esc(e.name)}${e.resolved?'':' — não resolvido'}</option>`).join('')}</select></div>`:''}
  <details class="internal"><summary>Ver todos os tipos internos do efeito selecionado</summary><div class="tags">${(c?.types||[]).map(t=>`<span class="type-tag">${esc(t)}</span>`).join('')||'Tipos não disponíveis.'}</div></details>`;
  $('componentSelect')?.addEventListener('change',()=>{state.component=$('componentSelect').value;renderAnchor();state.offset=0;explore();});
}
function buildQuery(){
  const p=new URLSearchParams({q:$('query').value.trim(),skill_id:state.skill?.id||'',component:state.component,
    scope:state.scope,color:state.color,tag:state.tag,relation:$('relation').value,mode:$('compatMode').value,ascendancy:$('ascendancyFilter').value,kind:$('kindFilter').value,
    offset:String(state.offset),limit:String(state.limit)});return p.toString();
}
async function explore(){
  if(state.view==='interactions'){await loadInteractions();return;}
  const ticket=++searchTicket;$('resultCount').textContent='Consultando os dados…';
  $('tagFilter').hidden=!state.tag;$('tagFilter').querySelector('span').textContent='Tag: '+state.tag;
  try{const d=await api('/api/explore?'+buildQuery());if(ticket!==searchTicket)return;
    $('resultCount').textContent=`${fmt(d.total)} resultado(s)`;
    $('cards').innerHTML=d.results.map(renderCard).join('')||`<div class="empty-results"><h3>Nenhum resultado com estes filtros.</h3><p>Remova a tag ou o atributo, troque para “Toda a base” ou inclua incompatíveis e não verificados para investigar a cobertura.</p></div>`;
    $('pageInfo').textContent=d.total?`${state.offset+1}–${Math.min(state.offset+state.limit,d.total)} de ${fmt(d.total)}`:'0 resultados';
    $('previous').disabled=state.offset===0;$('next').disabled=state.offset+state.limit>=d.total;
  }catch(e){if(ticket!==searchTicket)return;$('cards').innerHTML=`<div class="empty-results data-error">${esc(e.message)}</div>`;$('resultCount').textContent='Consulta não concluída';}
}
function renderCard(e){
  const declarations=e.declared.map(l=>`<span class="declared ${l.relation==='CONSUMES'?'consume':''}" title="${esc(l.path+' · '+l.evidence)}">${esc(rel(l.relation))} → <b>${esc(l.label)}</b>${l.component==='minion_of_supported_skill'?' · minion':''}</span>`).join('');
  const text=e.evidence[0];const value=text?.text||'O arquivo não forneceu descrição legível; veja os dados brutos.';
  const shortened=value.length>430?value.slice(0,427)+'…':value;
  return `<article class="card" data-attr="${esc(e.color)}" data-entity="${esc(e.id)}"><div class="card-head"><button class="card-title" data-inspect="${esc(e.id)}">${esc(e.name)}</button><span class="attribute">${esc(e.attribute)}</span></div>
    <div class="tags">${tagsHtml(e.tags)}</div><div><span class="compat ${esc(e.compatibility.status)}" title="${esc(e.compatibility.reason)}">${esc(e.compatibility.label)}</span></div>
    ${e.ascendancy?`<p class="node-owner">${esc(e.ascendancy)}${e.is_notable?' · notable':''}</p>`:''}${declarations?`<div class="declarations">${declarations}</div>`:''}<div class="source-label">${esc(text?.source||'Dados importados')} · ${esc(kind(e.kind))}</div><p class="source-text">${esc(shortened)}</p>${rawNotice(e)}
    <div class="card-footer"><span>${fmt(e.text_count)} textos · ${fmt(e.stat_count)} valores/IDs</span><button class="text-button" data-inspect="${esc(e.id)}">Inspecionar →</button></div></article>`;
}
async function inspect(id){
  const ticket=++detailTicket;entity=null;detailTab='text';
  $('detailDialog').showModal();$('detailHeader').innerHTML='<h2>Carregando dados…</h2><button class="close" data-close="detailDialog" aria-label="Fechar">×</button>';$('detailTabs').innerHTML='';$('detailBody').textContent='';
  try{const e=await api('/api/entity?id='+encodeURIComponent(id));if(ticket!==detailTicket)return;entity=e;renderInspector();}
  catch(e){$('detailBody').textContent=e.message;}
}
function renderInspector(){
  if(!entity)return;const e=entity;
  $('detailHeader').dataset.attr=e.color;
  $('detailHeader').innerHTML=`<div><span class="eyebrow">${esc(kind(e.kind))} · ${esc(e.attribute)} · REPOE</span><h2>${esc(e.name)}</h2></div><button class="close" data-close="detailDialog" aria-label="Fechar">×</button>`;
  const tabs=[['text','Textos e ligações'],['tags','Tags e tipos'],['rules','Regras'],['stats','Stats / valores'],['raw','JSON original']];
  $('detailTabs').innerHTML=tabs.map(([k,v])=>`<button data-detail-tab="${k}" class="${detailTab===k?'active':''}">${v}</button>`).join('');
  if(detailTab==='text'){
    const all=e.texts.map(t=>`<div class="evidence-block"><p>${esc(t.text)}</p><code>${esc(t.path)}</code><details><summary>Texto original, com marcação do jogo</summary><pre class="raw-text">${esc(t.original)}</pre></details></div>`).join('');
    const meaningful=e.links.filter(l=>['PRODUCES','ENABLES','AMPLIFIES','REDUCES','MODIFIES','REQUIRES','PREVENTS','CONSUMES','GENERATES','CREATES','PREVENTS_CONSUMPTION'].includes(l.relation));
    const links=meaningful.map(l=>`<div class="evidence-block"><strong>${esc(rel(l.relation))} → ${esc(l.label)}</strong><p class="muted">Alcance: ${esc(l.scope||l.component)} · ${esc(l.basis||'flag')} · aspecto: ${esc(l.aspect||'não especificado')}</p>${l.condition?`<p class="condition">Condição preservada: ${esc(l.condition)}</p>`:''}<code>${esc(l.path)} = ${esc(l.evidence)}</code><div><button class="text-button" data-topic="${esc(l.label)}">Buscar este conceito em toda a base →</button></div></div>`).join('');
    const topics=new Map();for(const l of e.links)if(l.relation==='MENTIONS')topics.set(l.concept,l.label);
    $('detailBody').innerHTML=`<div class="inspector-notice">Texto da fonte e ligações explícitas. “Menciona” não significa “produz” ou “melhora”. As descrições ficam no idioma da exportação para não alterar as regras.</div>${all||'<p class="muted">Sem texto legível. Os stats e JSON original continuam disponíveis.</p>'}<h3>Relações identificadas, com evidências</h3>${links||'<p class="muted">Nenhuma relação semântica foi extraída neste registro. Os dados não interpretados continuam no catálogo; isso não significa ausência de interações.</p>'}<h3>Conceitos mencionados na descrição</h3><div class="topic-links">${[...topics.values()].map(t=>`<button data-topic="${esc(t)}">${esc(t)}</button>`).join('')||'<span class="muted">Sem referências marcadas no texto.</span>'}</div>`;
  }else if(detailTab==='tags'){
    $('detailBody').innerHTML=`<h3>Tags originais — preservadas integralmente</h3><div class="tags">${tagsHtml(e.tags)}</div><p class="muted">Cor: ${esc(e.attribute)} · Campo: ${esc(e.color_source)}<br>Pesos de atributo: ${esc(JSON.stringify(e.weights))}</p>${e.components.map((c,i)=>`<div class="evidence-block"><strong>${i+1}. ${esc(c.name)}</strong><p class="muted">ID: ${esc(c.id)} · ${c.resolved?'resolvido':'não resolvido'}</p><div class="tags">${(c.types||[]).map(t=>`<span class="type-tag">${esc(t)}</span>`).join('')||'Sem tipos disponíveis.'}</div>${c.minion_types?.length?`<p>Tipos dos minions: ${esc(c.minion_types.join(', '))}</p>`:''}</div>`).join('')}`;
  }else if(detailTab==='rules' && e.raw_dataset!=='gems'){
    $('detailBody').innerHTML=`<h3>Dados do nó / ascendência</h3><p class="muted">Alocação, caminho, nível e disponibilidade do personagem não foram simulados.</p>${e.ascendancy?`<p>Ascendência: <b>${esc(e.ascendancy)}</b></p>`:''}${e.granted_gem?`<button data-inspect="${esc(e.granted_gem.id)}">Skill concedida: ${esc(e.granted_gem.name)}</button>`:''}<pre class="raw-text">${esc(JSON.stringify(e.node_meta||{ascendancy:e.ascendancy_id,class_name:e.class_name},null,2))}</pre><h3>Vizinhos declarados na fonte</h3>${(e.neighbours||[]).map(n=>`<button data-inspect="${esc(n.id)}">${esc(n.name)}</button>`).join('')||'<p class="muted">Nenhuma lista de adjacência direta foi interpretada para este nó. Não foi inventado um caminho.</p>'}`;
  }else if(detailTab==='rules'){
    $('detailBody').innerHTML=`<div class="inspector-notice">Expressões originais em ordem, incluindo AND / OR / NOT. Os tipos dos efeitos secundários não são unidos ao primeiro efeito. Esta análise não simula todo o conjunto de supports, equipamento ou sockets.</div>${e.kind==='SUPPORT'?Object.entries(e.rules).map(([k,v])=>`<div class="rule"><strong>${esc(k)}</strong><pre class="raw-text">${esc(JSON.stringify(v,null,2))}</pre></div>`).join(''):'<p class="muted">Esta é uma skill. As regras allowed_types/excluded_types pertencem aos supports; os tipos de cada efeito estão na aba anterior.</p>'}`;
  }else if(detailTab==='stats'){
    const rows=e.stats.slice(0,250);
    $('detailBody').innerHTML=`<div class="inspector-notice">Valores e IDs como vieram do arquivo, com seus caminhos. Não são cálculo de DPS; níveis, unidades e conversões não são presumidos. Exibindo ${rows.length} de ${e.stats.length} entradas; o JSON contém tudo.</div><table class="stat-table"><thead><tr><th>Stat / campo e caminho</th><th>Valor original</th></tr></thead><tbody>${rows.map(s=>`<tr><td><b>${esc(s.id)}</b><br><small>${esc(s.path)}</small></td><td>${esc(JSON.stringify(s.value))}</td></tr>`).join('')}</tbody></table>`;
  }else if(detailTab==='raw'){
    $('detailBody').innerHTML='<p class="muted">Lendo registros originais…</p>';
    const id=e.id;
    api('/api/entity?id='+encodeURIComponent(id)+'&raw=1').then(d=>{
      if(entity?.id!==id||detailTab!=='raw')return;
      $('detailBody').innerHTML=`<div class="audit-grid"><span>Fonte</span><a href="${esc(e.source_url)}" target="_blank" rel="noreferrer">RePoE · ${esc(e.raw_dataset||'gems')}</a><span>ID original</span><code>${esc(e.source_id)}</code><span>Versão da fonte</span><span>${esc(e.source_version||'Não identificada — veja o hash em Base de dados')}</span></div><pre class="raw-text">${esc(JSON.stringify(d.raw,null,2))}</pre>`;
    }).catch(err=>{$('detailBody').textContent=err.message;});
  }
}
async function openData(){
  $('dataDialog').showModal();renderAudit();
  $('candidates').textContent='Procurando bases nas pastas de projetos próximas…';
  try{const d=await api('/api/candidates');$('candidates').innerHTML=d.results.map(e=>`<div class="candidate"><div><code>${esc(e.folder)}</code><br><small>${bytes(e.bytes)} em arquivos</small></div><button data-import-folder="${esc(e.folder)}">Usar esta base</button></div>`).join('')||'<p class="muted">Não encontrei os JSONs nas pastas próximas. Informe a pasta abaixo ou use o download.</p>';}
  catch(e){$('candidates').textContent=e.message;}
}
function renderAudit(){
  if(!status)return;const m=status.import||{},d=m.diagnostics||{};
  $('audit').innerHTML=`<div class="metrics">${[['Skills',status.counts.SKILL],['Meta skills',status.counts.META],['Supports',status.counts.SUPPORT],['Ligações',status.links]].map(([a,b])=>`<div class="metric"><strong>${fmt(b)}</strong><span>${a}</span></div>`).join('')}</div><div class="audit-grid"><span>Fonte</span><span>RePoE PoE2</span><span>Versão</span><span>${esc(m.repoe_version||'Não identificada no arquivo local')}</span><span>Importado em</span><span>${esc(m.imported_at||'Ainda não importado')}</span><span>IDs resolvidos</span><span>${fmt(d.resolved)} / ${fmt(d.grants)}</span><span>Não resolvidos</span><span>${fmt(d.unresolved)}</span><span>Supports sem regras</span><span>${fmt(d.missing_support_rules)} — não aprovados automaticamente</span><span>Registros ignorados</span><span>${fmt(d.skipped_records)} — formato não reconhecido</span><span>Origem local</span><code>${esc(m.folder||'—')}</code></div><details class="internal"><summary>Ver hashes e diagnóstico completo</summary><pre class="raw-text">${esc(JSON.stringify(m,null,2))}</pre></details>${treeAuditHtml()}<div class="divider"></div>`;
}
async function startImport(kind,folder=''){
  try{await api('/api/import',{kind,folder});$('dataDialog').close();$('toast').hidden=true;polling=true;lastFinished=null;await pollJob();}
  catch(e){notify(e.message,true);}
}
async function pollJob(){
  clearTimeout(jobTimer);
  try{const p=await api('/api/progress');
    if(!p.id){$('jobPanel').hidden=true;return;}
    $('jobPanel').hidden=false;$('jobStage').textContent=p.stage;$('jobDetail').textContent=p.detail;
    $('jobElapsed').textContent=Math.round(p.elapsed_seconds||0)+' s';
    $('jobBytes').textContent=p.downloaded!=null?`${bytes(p.downloaded)}${p.total?' / '+bytes(p.total):' recebidos'}${p.file_index?' · arquivo '+p.file_index+'/'+p.file_count:''}`:'Progresso por etapa; sem porcentagem estimada.';
    if(p.total&&p.downloaded!=null){$('jobProgress').max=p.total;$('jobProgress').value=p.downloaded;}else $('jobProgress').removeAttribute('value');
    $('cancelJob').hidden=!p.running;
    if(p.running){polling=true;jobTimer=setTimeout(pollJob,800);}
    else{polling=false;$('jobProgress').max=1;$('jobProgress').value=1;
      if(lastFinished!==p.id){lastFinished=p.id;if(p.error){notify(p.error,true);}else{notify('Dados importados. Agora escolha uma skill e busque uma mecânica, por exemplo Ignite.');await refreshStatus();}}
    }
  }catch(e){notify('Não foi possível consultar o andamento: '+e.message,true);if(polling)jobTimer=setTimeout(pollJob,2000);}
}
function resetExplore(){state.offset=0;explore();}
$('skillSearch').addEventListener('input',()=>{clearTimeout(skillTimer);skillTimer=setTimeout(loadSkills,220);});
$('query').addEventListener('input',()=>{clearTimeout(queryTimer);queryTimer=setTimeout(resetExplore,350);});
$('query').addEventListener('keydown',e=>{if(e.key==='Enter'){clearTimeout(queryTimer);resetExplore();}});
$('searchBtn').addEventListener('click',resetExplore);
$('relation').addEventListener('change',resetExplore);$('compatMode').addEventListener('change',resetExplore);
$('clearSkill').addEventListener('click',()=>{anchorTicket++;state.skill=null;state.component='';renderAnchor();loadSkills();resetExplore();});
$('scopeSupports').addEventListener('click',()=>setScope('supports'));
$('scopeAll').addEventListener('click',()=>setScope('all'));
$('scopePassives').addEventListener('click',()=>setScope('passives'));
$('scopeAscendancies').addEventListener('click',()=>setScope('ascendancies'));
$('previous').addEventListener('click',()=>{state.offset=Math.max(0,state.offset-state.limit);explore();});
$('next').addEventListener('click',()=>{state.offset+=state.limit;explore();});
$('tagFilter').querySelector('button').addEventListener('click',()=>{state.tag='';resetExplore();});
$('openBuildLibrary').addEventListener('click',openBuildLibrary);
document.querySelectorAll('[data-library-tab]').forEach(b=>b.addEventListener('click',()=>setLibraryTab(b.dataset.libraryTab)));
$('openCurrentBuild').addEventListener('click',openCurrentBuild);
$('openPob').addEventListener('click',openPob);$('importPob').addEventListener('click',importPob);
$('backToFinder').addEventListener('click',()=>setAppMode('finder'));$('changePob').addEventListener('click',openPob);
$('libraryBack').addEventListener('click',()=>setAppMode('finder'));$('libraryAdd').addEventListener('click',openPob);
for(const id of ['libraryClass','libraryAsc','librarySkill'])$(id).addEventListener('change',()=>loadBuildLibrary(false));
$('libraryQuery').addEventListener('input',()=>{clearTimeout(buildLibrary.timer);buildLibrary.timer=setTimeout(()=>loadBuildLibrary(false),220);});
document.querySelectorAll('[data-build-tab]').forEach(b=>b.addEventListener('click',()=>{buildTab=b.dataset.buildTab;renderCurrentBuild();}));
$('openCodex').addEventListener('click',()=>$('codexDialog').showModal());
$('openData').addEventListener('click',openData);$('reuseData').addEventListener('click',openData);
$('downloadData').addEventListener('click',()=>startImport('online'));$('refreshOnline').addEventListener('click',()=>startImport('online'));
$('downloadTree').addEventListener('click',()=>startImport('online_tree'));
$('importTreeFolder').addEventListener('click',()=>startImport('local_tree',$('folder').value.trim()));
$('importFolder').addEventListener('click',()=>startImport('local',$('folder').value.trim()));
$('cancelJob').addEventListener('click',async()=>{try{const d=await api('/api/cancel',{});notify(d.message);}catch(e){notify(e.message,true);}});
document.addEventListener('click',e=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.dataset.close){$(b.dataset.close).close();return;}
  if(b.hasAttribute('data-color')){state.color=b.dataset.color;document.querySelectorAll('[data-color]').forEach(x=>x.classList.toggle('active',x===b));resetExplore();return;}
  if(b.dataset.skill){selectSkill(b.dataset.skill);return;}
  if(b.dataset.inspect){inspect(b.dataset.inspect);return;}
  if(b.dataset.tag){state.tag=b.dataset.tag;$('detailDialog').close();setView('catalog');return;}
  if(b.dataset.detailTab){detailTab=b.dataset.detailTab;renderInspector();return;}
  if(b.dataset.interactionTopic){$('query').value=b.dataset.interactionTopic;setView('interactions');return;}
  if(b.dataset.catalogRelation){$('relation').value=b.dataset.catalogRelation;state.scope='all';setView('catalog');syncScope();return;}
  if(b.dataset.topic){$('query').value=b.dataset.topic;state.tag='';state.scope='all';syncScope();$('compatMode').value='all';$('detailDialog').close();resetExplore();return;}
  if(b.dataset.importFolder){startImport('local',b.dataset.importFolder);return;}
  if(b.dataset.buildTabJump){buildTab=b.dataset.buildTabJump;renderCurrentBuild();return;}
  if(b.dataset.gearSlot!==undefined){selectGearSlot(b.dataset.gearSlot);return;}
  if(b.hasAttribute('data-trade-prepare')||b.hasAttribute('data-trade-retry')){prepareGearTrade(gearTrade.slot);return;}
  if(b.hasAttribute('data-trade-search-base')){runTradeSearch(true);return;}
  if(b.hasAttribute('data-trade-search')){runTradeSearch(false);return;}
  if(b.dataset.openSkillFromPob!==undefined){openPobSkillInFinder(b.dataset.openSkillFromPob);return;}
  if(b.dataset.treeTopic!==undefined){
    setAppMode('finder');state.scope='passives';syncScope();$('query').value=b.dataset.treeTopic;state.offset=0;setView('catalog');return;
  }
  if(b.dataset.libraryUse!==undefined){useLibraryBuild(b.dataset.libraryUse);return;}
  if(b.dataset.libraryDelete!==undefined){deleteLibraryBuild(b.dataset.libraryDelete);return;}
  if(b.dataset.gggImport!==undefined){gggImportCharacter(b.dataset.gggImport);return;}
  if(b.id==='gggSaveConfig'){gggSaveConfig();return;}
  if(b.id==='gggAuthorize'){gggAuthorize();return;}
  if(b.id==='gggLogout'){gggLogout();return;}
  if(b.id==='gggImportSnapshot'){gggImportSnapshot();return;}
  if(b.dataset.linkerAdd!==undefined){if(linker.selected.length<5&&!linker.selected.includes(b.dataset.linkerAdd)){linker.selected.push(b.dataset.linkerAdd);linker.result=null;renderVirtualBody();}return;}
  if(b.dataset.linkerRemove!==undefined){linker.selected.splice(Number(b.dataset.linkerRemove),1);linker.result=null;renderVirtualBody();return;}
  if(b.id==='linkerReset'){linker.selected=currentGroupSupports(selectedGroup()).slice(0,5);linker.result=null;renderVirtualBody();return;}
  if(b.id==='linkerAnalyze'){linkerAnalyze();return;}
  if(b.id==='engineDetect'){engineDetect();return;}
  if(b.id==='engineInstallPob'){engineInstallPob();return;}
  if(b.id==='engineInstallBridge'){engineInstallBridge();return;}
  if(b.id==='engineSavePaths'){engineSavePaths();return;}
  if(b.id==='engineStart'){engineStart();return;}
  if(b.id==='engineStop'){engineStop();return;}
  if(b.id==='engineLoadCurrent'){engineLoadCurrent();return;}
});
$('ascendancyFilter').addEventListener('change',resetExplore);
$('kindFilter').addEventListener('change',()=>{if(state.view==='interactions')setView('catalog');resetExplore();});
$('viewCatalog').addEventListener('click',()=>setView('catalog'));
$('viewInteractions').addEventListener('click',()=>setView('interactions'));

document.addEventListener('change',async e=>{
  if(e.target?.id==='linkerGroup'){
    linker.groupIndex=Number(e.target.value);
    linker.selected=currentGroupSupports(selectedGroup()).slice(0,5);
    linker.result=null;
    $('buildContent').innerHTML='<div class="build-panel"><strong>PoB verificando supports compatíveis…</strong></div>';
    try{
      await refreshCompatibleSupports();
      renderVirtualBody();
    }catch(err){
      notify(err.message,true);
      renderVirtualBody();
    }
  }
});
let linkerSearchTimer=null;
document.addEventListener('input',e=>{
  if(e.target?.id==='linkerSearch'){
    linker.query=e.target.value;clearTimeout(linkerSearchTimer);
    linkerSearchTimer=setTimeout(()=>{renderVirtualBody();const i=$('linkerSearch');if(i){i.focus();i.setSelectionRange(i.value.length,i.value.length);}},120);
  }
});


let treeSearchTimer=null;
document.addEventListener('input',e=>{
  if(e.target?.id==='treeAllocatedSearch'){
    treeView.q=e.target.value;
    clearTimeout(treeSearchTimer);
    treeSearchTimer=setTimeout(()=>renderTreeAllocatedList(),90);
  }
});
document.addEventListener('change',e=>{
  if(e.target?.id==='treeAllocatedKind'){
    treeView.kind=e.target.value;
    renderTreeAllocatedList();
  }
});

refreshStatus().then(()=>pollJob()).catch(e=>notify('Falha ao abrir a base local: '+e.message,true));


function renderAscendancies(){
  const select=$('ascendancyFilter'),previous=select.value;
  select.innerHTML='<option value="">Todas as ascendências</option>'+(status.ascendancies||[]).map(a=>`<option value="${esc(a.id)}">${esc(a.name)}</option>`).join('');
  select.value=previous;
  if(!select.value)select.value='';
}
function treeAuditHtml(){
  const m=status?.tree_import||{},d=m.diagnostics||{};
  return `<div class="divider"></div><h3>Árvore & ascendências</h3><div class="metrics">${[['Nós',d.nodes],['Ascendências',d.ascendancies],['Nós com tradução',d.translated_nodes],['Relações semânticas',status?.semantic_links]].map(([a,b])=>`<div class="metric"><strong>${fmt(b)}</strong><span>${esc(a)}</span></div>`).join('')}</div><p class="muted">Versão: ${esc(m.repoe_version||'não identificada / ainda não importada')} · ${fmt(d.untranslated_stats)} stats da árvore sem tradução aplicada. IDs e valores permanecem pesquisáveis.</p><details class="internal"><summary>Diagnóstico da árvore e fontes</summary><pre class="raw-text">${esc(JSON.stringify(m,null,2))}</pre></details>`;
}
function syncScope(){
  for(const [id,value] of [['scopeSupports','supports'],['scopeAll','all'],['scopePassives','passives'],['scopeAscendancies','ascendancies']])$(id).classList.toggle('active',state.scope===value);
}
function setScope(value){state.scope=value;syncScope();setView('catalog');}
function setView(value){
  state.view=value;searchTicket++;state.offset=0;
  $('viewCatalog').classList.toggle('active',value==='catalog');$('viewInteractions').classList.toggle('active',value==='interactions');
  $('interactionPanel').hidden=value!=='interactions';
  for(const el of [$('cards'),document.querySelector('.pagination'),document.querySelector('.result-heading')])el.hidden=value==='interactions';
  $('relation').disabled=value==='interactions';$('kindFilter').disabled=value==='interactions';
  document.querySelector('.colors').hidden=value==='interactions';
  $('tagFilter').hidden=value==='interactions'||!state.tag;
  $('query').placeholder=value==='interactions'?'Qual mecânica conectar? Ignite, Power Charge, Fire Damage…':'Busque uma interação: Ignite, Power Charge, area…';
  explore();
}
const basisLabel=x=>({explicit_flag:'Flag explícita',exact_stat_id:'Stat exato',text_rule:'Regra textual',translated_stat_rule:'Stat traduzido pela fonte',text_mention:'Menção',translated_stat_mention:'Menção no stat'}[x]||x||'Dado da fonte');
function effectHtml(l){return `<div class="semantic-evidence"><span class="effect-label">${esc(rel(l.relation))} → ${esc(l.label)}</span><p>${esc(l.evidence)}</p><small>${esc(basisLabel(l.basis))} · ${esc(l.scope||l.component)}${l.aspect?' · '+esc(l.aspect):''}</small><details><summary>Evidência / condição</summary><code>${esc(l.path)}</code>${l.condition?`<p class="condition">${esc(l.condition)}</p>`:''}</details></div>`;}
function relationCard(r){
  return `<article class="relation-card" data-attr="${esc(r.color)}"><div class="card-head"><button class="card-title" data-inspect="${esc(r.id)}">${esc(r.name)}</button><span class="attribute">${esc(r.attribute)}</span></div><p class="node-owner">${esc(kind(r.kind))}${r.ascendancy?' · '+esc(r.ascendancy):''}</p><div class="tags">${tagsHtml(r.tags)}</div>${r.kind==='SUPPORT'?`<span class="compat ${esc(r.compatibility.status)}" title="${esc(r.compatibility.reason)}">${esc(r.compatibility.label)}</span>`:''}${r.evidence.slice(0,3).map(effectHtml).join('')}${r.evidence.length>3?`<button class="text-button" data-inspect="${esc(r.id)}">+${r.evidence.length-3} evidências no registro</button>`:''}</article>`;
}
async function loadInteractions(){
  const ticket=++searchTicket;const panel=$('interactionPanel');panel.innerHTML='<p class="muted">Cruzando relações dos dados importados…</p>';
  const params=new URLSearchParams({q:$('query').value.trim(),skill_id:state.skill?.id||'',component:state.component,
    ascendancy:$('ascendancyFilter').value,include_incompatible:$('compatMode').value==='all'?'1':'0',limit:'8'});
  try{
    const d=await api('/api/interactions?'+params);if(ticket!==searchTicket||state.view!=='interactions')return;
    const topics=d.topics.map(t=>`<button data-interaction-topic="${esc(t.name)}">${esc(t.name)} <small>${fmt(t.semantic_count)} relações com entidades</small></button>`).join('');
    if(!d.topic){panel.innerHTML=`<div class="interaction-intro"><h2>Encontre quem produz, modifica ou impede.</h2><p>${esc(d.message)}</p><div class="topic-links">${topics||'<span>Nenhum conceito reconhecido. Use o catálogo para consultar os dados ainda não interpretados.</span>'}</div></div>`;return;}
    const mappings={produces:'produces',modifies:'modifies',requires:'requires',prevents:'prevents',mentions:'mentions'};
    const paths=d.paths.map(p=>`<article class="path-card ${p.kind==='possible_conflict'?'conflict':''}"><span class="eyebrow">${p.kind==='possible_conflict'?'POSSÍVEL CONTRADIÇÃO':p.kind==='consumption'?'APLICAÇÃO → CONSUMO':'INTERAÇÃO CANDIDATA'}</span><div class="path-line"><button data-inspect="${esc(p.a.id)}" data-attr="${esc(p.a.color)}">${esc(p.a.name)}</button><span>${esc(rel(p.from_effect.relation))} →</span><b>${esc(p.label)}</b><span>← ${esc(rel(p.to_effect.relation))}</span><button data-inspect="${esc(p.b.id)}" data-attr="${esc(p.b.color)}">${esc(p.b.name)}</button></div><details><summary>Por que existe esta ligação? Ver condições e limites</summary><div class="path-evidence">${effectHtml(p.from_effect)}${effectHtml(p.to_effect)}</div>${p.warnings.map(w=>`<p class="path-warning">${esc(w)}</p>`).join('')}</details></article>`).join('');
    panel.innerHTML=`<div class="interaction-intro"><span class="eyebrow">BUSCA ENTRE CATEGORIAS</span><h2>${esc(d.topic.name)}</h2><p>${fmt(d.entity_count)} entidades relacionadas · ${fmt(d.hidden_incompatible)} supports incompatíveis ocultos · ${fmt(d.unknown_compatibility)} supports sem regras suficientes</p><p class="muted">${esc(d.message)}</p>${(d.source_warnings||[]).map(w=>`<p class="condition">${esc(w)}</p>`).join('')}</div><div class="relation-groups">${d.groups.map(g=>`<section class="relation-group" data-group="${esc(g.key)}"><h3>${esc(g.name)} <span>${fmt(g.count)}</span></h3>${g.results.map(relationCard).join('')||'<p class="muted">Nenhuma relação identificada. Isso não prova que não exista.</p>'}${g.count>g.results.length?`<button class="text-button" data-catalog-relation="${mappings[g.key]}">Ver todos no catálogo →</button>`:''}</section>`).join('')}</div><section class="paths-section"><h2>Cadeias candidatas</h2><p class="muted">Dois efeitos ligados pela mesma mecânica. Não calcula benefício, uptime ou caminho da árvore; a evidência precisa ser conferida. Até ${d.path_limit||32} cadeias distintas por consulta.</p>${paths||'<div class="empty-results">Ainda não há dois efeitos com papéis suficientes para formar uma cadeia. As menções acima não foram transformadas em sinergia artificial.</div>'}</section>`;
  }catch(e){if(ticket===searchTicket)panel.innerHTML=`<div class="empty-results data-error">${esc(e.message)}</div>`;}
}
