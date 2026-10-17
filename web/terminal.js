// Terminal na página: Claude Code ou Codex rodando na pasta do projeto, via WebSocket + xterm.js.
(function(){
  const $=id=>document.getElementById(id);
  const dialog=$('terminalDialog');if(!dialog)return;
  const host=$('terminalHost'),note=$('terminalNote');
  let term=null,fit=null,socket=null,status=null,current='claude',observer=null;

  function write(text){if(term)term.write(text);}
  function setNote(text,isError){note.textContent=text||'';note.classList.toggle('error',!!isError);}

  async function loadStatus(){
    const r=await fetch('/api/terminal/status',{cache:'no-store'});
    status=await r.json();
    dialog.querySelectorAll('[data-terminal-cli]').forEach(b=>{
      const info=status.clis[b.dataset.terminalCli]||{};
      b.disabled=!info.available;b.title=info.available?info.path:('Não encontrado. Instale: '+info.install);
      b.classList.toggle('active',b.dataset.terminalCli===current);
    });
    if(!status.pty_ok)setNote(status.pty_error,true);
    return status;
  }

  function ensureTerm(){
    if(term)return;
    term=new Terminal({cursorBlink:true,fontSize:13,fontFamily:'Cascadia Mono, Consolas, monospace',scrollback:5000,
      theme:{background:'#0f1115',foreground:'#e6e6e6',cursor:'#f5c451'}});
    fit=new FitAddon.FitAddon();term.loadAddon(fit);term.open(host);fit.fit();
    term.onData(d=>{if(socket&&socket.readyState===1)socket.send(JSON.stringify({type:'input',data:d}));});
    observer=new ResizeObserver(()=>{if(!dialog.open)return;try{fit.fit();}catch(e){return;}
      if(socket&&socket.readyState===1)socket.send(JSON.stringify({type:'resize',rows:term.rows,cols:term.cols}));});
    observer.observe(host);
  }

  function disconnect(){
    if(socket){try{socket.onclose=null;socket.close();}catch(e){}socket=null;}
  }

  function connect(cli){
    ensureTerm();disconnect();current=cli;
    dialog.querySelectorAll('[data-terminal-cli]').forEach(b=>b.classList.toggle('active',b.dataset.terminalCli===cli));
    const info=status&&status.clis[cli];
    if(!info||!info.available){setNote((info?info.label:cli)+' não encontrado nesta máquina. Instale: '+(info?info.install:''),true);return;}
    if(!status.pty_ok){return;}
    term.reset();fit.fit();
    setNote('Conectando '+info.label+' em '+status.cwd+' …');
    const proto=location.protocol==='https:'?'wss':'ws';
    const url=`${proto}://${location.host}/ws/terminal?cli=${encodeURIComponent(cli)}&token=${encodeURIComponent(status.token)}&rows=${term.rows}&cols=${term.cols}`;
    socket=new WebSocket(url);
    socket.onopen=()=>{setNote(info.label+' · '+status.cwd+' · Esc e atalhos vão para o terminal; feche pelo ×.');term.focus();};
    socket.onmessage=e=>{
      if(typeof e.data!=='string')return;
      if(e.data.startsWith('{"type":"exit"')){write('\r\n\x1b[90m[sessão encerrada; clique na aba para abrir outra]\x1b[0m\r\n');return;}
      write(e.data);
    };
    socket.onclose=()=>{setNote(info.label+' desconectado. Clique na aba para reconectar.');};
    socket.onerror=()=>{setNote('Falha na conexão com o terminal. O Finder precisa estar aberto nesta mesma origem.',true);};
  }

  dialog.addEventListener('cancel',e=>e.preventDefault()); // Esc pertence ao CLI, não fecha o painel
  dialog.querySelectorAll('[data-terminal-cli]').forEach(b=>b.addEventListener('click',()=>connect(b.dataset.terminalCli)));
  dialog.querySelector('[data-terminal-close]').addEventListener('click',()=>{dialog.close();});
  dialog.addEventListener('close',()=>{disconnect();setNote('');});
  $('openTerminal').addEventListener('click',async()=>{
    dialog.showModal();
    try{await loadStatus();}catch(e){setNote('Não foi possível consultar o terminal: '+e,true);return;}
    const first=['claude','codex'].find(c=>status.clis[c]&&status.clis[c].available)||'claude';
    connect(current&&status.clis[current]&&status.clis[current].available?current:first);
  });
})();
