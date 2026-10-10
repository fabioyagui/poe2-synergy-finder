from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from src import VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "ggg"
CONFIG_FILE = DATA_DIR / "config.json"
TOKEN_FILE = DATA_DIR / "oauth-token.json"

AUTH_URL = "https://www.pathofexile.com/oauth/authorize"
TOKEN_URL = "https://www.pathofexile.com/oauth/token"
API_BASE = "https://api.pathofexile.com"
SCOPES = ["account:profile", "account:characters"]

# The official docs currently say new applications cannot be processed.
# Keep this message visible in the UI rather than silently borrowing another
# application's client_id (e.g. Path of Building's).
REGISTRATION_NOTE = (
    "A documentação oficial da GGG informa atualmente que novos aplicativos "
    "OAuth não podem ser processados. Se você já possui um Public Client "
    "registrado, a integração abaixo funciona com ele."
)

_PENDING: dict | None = None


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_json(path: Path, default):
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception:
        return default


def load_config() -> dict:
    raw=_load_json(CONFIG_FILE,{})
    return {
        "client_id": str(raw.get("client_id") or "").strip(),
        "contact": str(raw.get("contact") or "").strip(),
    }


def save_config(values: dict) -> dict:
    client_id=str((values or {}).get("client_id") or "").strip()
    contact=str((values or {}).get("contact") or "").strip()
    if client_id and not all(c.isalnum() or c in "-_." for c in client_id):
        raise ValueError("Client ID contém caracteres inesperados.")
    if contact and len(contact)>160:
        raise ValueError("Contato longo demais.")
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"client_id":client_id,"contact":contact},ensure_ascii=False,indent=2),encoding="utf-8")
    return status()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class _DATA_BLOB(ctypes.Structure):
    _fields_=[("cbData",wintypes.DWORD),("pbData",ctypes.POINTER(ctypes.c_byte))]


def _dpapi_encrypt(raw: bytes) -> str | None:
    if os.name != "nt":
        return None
    try:
        buf=ctypes.create_string_buffer(raw)
        in_blob=_DATA_BLOB(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_byte)))
        out_blob=_DATA_BLOB()
        ok=ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(in_blob),"PoE2 Synergy Finder",None,None,None,0,ctypes.byref(out_blob)
        )
        if not ok: return None
        try:
            data=ctypes.string_at(out_blob.pbData,out_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
        return base64.b64encode(data).decode("ascii")
    except Exception:
        return None


def _dpapi_decrypt(encoded: str) -> bytes | None:
    if os.name != "nt":
        return None
    try:
        raw=base64.b64decode(encoded)
        buf=ctypes.create_string_buffer(raw)
        in_blob=_DATA_BLOB(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_byte)))
        out_blob=_DATA_BLOB()
        ok=ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),None,None,None,None,0,ctypes.byref(out_blob)
        )
        if not ok: return None
        try:
            return ctypes.string_at(out_blob.pbData,out_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return None


def _save_token(token: dict):
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(token,ensure_ascii=False).encode("utf-8")
    encrypted=_dpapi_encrypt(payload)
    if encrypted is not None:
        wrapper={"storage":"windows-dpapi","payload":encrypted}
    else:
        # Test/non-Windows fallback only. The user's Windows build uses DPAPI.
        wrapper={"storage":"plain-local-fallback","payload":base64.b64encode(payload).decode("ascii")}
    TOKEN_FILE.write_text(json.dumps(wrapper,ensure_ascii=False,indent=2),encoding="utf-8")


def _load_token() -> dict | None:
    wrapper=_load_json(TOKEN_FILE,None)
    if not isinstance(wrapper,dict): return None
    try:
        if wrapper.get("storage")=="windows-dpapi":
            raw=_dpapi_decrypt(wrapper.get("payload") or "")
        else:
            raw=base64.b64decode(wrapper.get("payload") or "")
        if not raw: return None
        data=json.loads(raw.decode("utf-8"))
        return data if isinstance(data,dict) else None
    except Exception:
        return None


def logout() -> dict:
    global _PENDING
    _PENDING=None
    TOKEN_FILE.unlink(missing_ok=True)
    return status()


def _user_agent() -> str:
    cfg=load_config()
    cid=cfg.get("client_id") or "unconfigured-synergy-finder"
    contact=cfg.get("contact") or "local-user"
    return f"OAuth {cid}/{VERSION} (contact: {contact}) PoE2-Synergy-Finder"


def _token_post(fields: dict, timeout=25) -> dict:
    body=urllib.parse.urlencode(fields).encode("utf-8")
    req=urllib.request.Request(
        TOKEN_URL,data=body,method="POST",
        headers={
            "Content-Type":"application/x-www-form-urlencoded",
            "Accept":"application/json",
            "User-Agent":_user_agent(),
        },
    )
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            data=json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail=exc.read().decode("utf-8",errors="replace")[:800]
        raise ValueError(f"GGG OAuth respondeu HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Não foi possível acessar o OAuth da GGG: {exc.reason}") from exc
    if not isinstance(data,dict) or not data.get("access_token"):
        raise ValueError("A GGG não retornou um access token válido.")
    data["obtained_at"]=int(time.time())
    data["expires_at"]=int(time.time())+int(data.get("expires_in") or 0)
    return data


def start_oauth(server_port: int) -> dict:
    global _PENDING
    cfg=load_config()
    client_id=cfg.get("client_id")
    if not client_id:
        raise ValueError("Configure primeiro o Client ID do seu próprio Public OAuth Client da GGG.")
    verifier=_b64url(secrets.token_bytes(48))
    challenge=_b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    state=secrets.token_urlsafe(24)
    redirect_uri=f"http://127.0.0.1:{int(server_port)}/oauth/callback"
    _PENDING={
        "state":state,"verifier":verifier,"redirect_uri":redirect_uri,
        "created_at":time.time(),"client_id":client_id,
    }
    query=urllib.parse.urlencode({
        "client_id":client_id,
        "response_type":"code",
        "scope":" ".join(SCOPES),
        "state":state,
        "redirect_uri":redirect_uri,
        "code_challenge":challenge,
        "code_challenge_method":"S256",
    })
    return {
        "authorize_url":AUTH_URL+"?"+query,
        "redirect_uri":redirect_uri,
        "state":state,
        "scopes":SCOPES,
    }


def finish_oauth(code: str, state: str) -> dict:
    global _PENDING
    pending=_PENDING
    if not pending:
        raise ValueError("Nenhuma autorização OAuth está aguardando retorno.")
    if time.time()-float(pending.get("created_at") or 0)>600:
        _PENDING=None
        raise ValueError("A tentativa OAuth expirou. Inicie novamente.")
    if not secrets.compare_digest(str(state or ""),str(pending.get("state") or "")):
        _PENDING=None
        raise ValueError("OAuth state não confere. A autorização foi descartada.")
    if not code:
        raise ValueError("A GGG não retornou authorization code.")
    token=_token_post({
        "client_id":pending["client_id"],
        "grant_type":"authorization_code",
        "code":code,
        "redirect_uri":pending["redirect_uri"],
        "scope":" ".join(SCOPES),
        "code_verifier":pending["verifier"],
    })
    _save_token(token)
    _PENDING=None
    return status()


def _ensure_token() -> dict:
    token=_load_token()
    if not token or not token.get("access_token"):
        raise ValueError("Conta GGG não autorizada.")
    if int(token.get("expires_at") or 0) > int(time.time())+60:
        return token
    refresh=token.get("refresh_token")
    cfg=load_config()
    if not refresh or not cfg.get("client_id"):
        logout()
        raise ValueError("Token GGG expirado e não há refresh token utilizável.")
    renewed=_token_post({
        "client_id":cfg["client_id"],
        "grant_type":"refresh_token",
        "refresh_token":refresh,
    })
    if not renewed.get("refresh_token"):
        renewed["refresh_token"]=refresh
    _save_token(renewed)
    return renewed


def _api_get(path: str, timeout=25) -> dict:
    token=_ensure_token()
    req=urllib.request.Request(
        API_BASE+path,
        headers={
            "Accept":"application/json",
            "Authorization":"Bearer "+token["access_token"],
            "User-Agent":_user_agent(),
        },
    )
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            data=json.loads(response.read().decode("utf-8"))
            return data if isinstance(data,dict) else {"data":data}
    except urllib.error.HTTPError as exc:
        detail=exc.read().decode("utf-8",errors="replace")[:800]
        if exc.code==401:
            logout()
            raise ValueError("A autorização GGG expirou ou foi revogada. Autorize novamente.") from exc
        if exc.code==429:
            retry=exc.headers.get("Retry-After")
            raise ValueError(f"Limite de requisições da GGG atingido. Tente novamente em {retry or 'alguns'} segundos.") from exc
        raise ValueError(f"GGG API respondeu HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Não foi possível acessar a API da GGG: {exc.reason}") from exc


def profile() -> dict:
    return _api_get("/profile")


def list_characters() -> dict:
    data=_api_get("/character/poe2")
    chars=data.get("characters") or []
    if not isinstance(chars,list): chars=[]
    chars=sorted(chars,key=lambda c:(-(int(c.get("level") or 0)),str(c.get("name") or "").casefold()))
    return {"characters":chars,"count":len(chars)}


def get_character(name: str) -> dict:
    name=str(name or "").strip()
    if not name or len(name)>120:
        raise ValueError("Nome de personagem inválido.")
    data=_api_get("/character/poe2/"+urllib.parse.quote(name,safe=""),timeout=35)
    char=data.get("character")
    if not isinstance(char,dict):
        raise ValueError("A GGG não retornou o snapshot completo desse personagem.")
    return char


def _gem_name(item: dict) -> str:
    return str(item.get("gemSkill") or item.get("typeLine") or item.get("baseType") or item.get("name") or "").strip()


def _prop_number(item: dict, wanted: str):
    for prop in item.get("properties") or []:
        if str(prop.get("name") or "").casefold()!=wanted.casefold(): continue
        vals=prop.get("values") or []
        if vals and isinstance(vals[0],list) and vals[0]:
            raw=str(vals[0][0]).replace("%","").replace("+","").strip()
            try:
                num=float(raw)
                return int(num) if num.is_integer() else num
            except Exception: return raw
    return None


def _item_preview(item: dict) -> list[str]:
    rows=[]
    for key in ("implicitMods","explicitMods","runeMods","bondedMods","enchantMods"):
        for mod in item.get(key) or []:
            if isinstance(mod,dict): text=mod.get("description") or ""
            else: text=str(mod)
            if text: rows.append(text)
    return rows[:12]


def _item_record(item: dict) -> dict:
    return {
        "id": item.get("id") or "",
        "name": item.get("name") or "",
        "base_type": item.get("typeLine") or item.get("baseType") or "",
        "rarity": item.get("rarity") or "",
        "ilvl": item.get("ilvl"),
        "inventory_id": item.get("inventoryId") or "",
        "preview": _item_preview(item),
        "trade_lines": _item_preview(item),
        "icon": item.get("icon") or "",
    }


def character_to_summary(character: dict, source_label: str | None=None) -> dict:
    if not isinstance(character,dict):
        raise ValueError("Snapshot de personagem inválido.")
    name=str(character.get("name") or "").strip()
    if not name:
        raise ValueError("Snapshot GGG sem nome de personagem.")

    groups=[]
    for raw in character.get("skills") or []:
        if not isinstance(raw,dict): continue
        if raw.get("support") is True:
            continue
        main=_gem_name(raw)
        if not main: continue
        gems=[{
            "name":main,
            "level":_prop_number(raw,"Level"),
            "quality":_prop_number(raw,"Quality"),
            "enabled":True,
            "support":False,
        }]
        for support in raw.get("socketedItems") or []:
            if not isinstance(support,dict): continue
            sname=_gem_name(support)
            if not sname: continue
            gems.append({
                "name":sname,
                "level":_prop_number(support,"Level"),
                "quality":_prop_number(support,"Quality"),
                "enabled":True,
                "support":True,
            })
        groups.append({
            "label":main,
            "slot":raw.get("inventoryId") or "Skills",
            "main_gem":main,
            "main_index":0,
            "gems":gems,
        })

    # GGG doesn't label a "main DPS skill". Keep that fact explicit; for card
    # display only, pick the most-linked active gem as a preview candidate.
    preview_main=""
    if groups:
        preview_main=max(groups,key=lambda g:len(g.get("gems") or []))["main_gem"]

    slots=[]
    for index,item in enumerate(character.get("equipment") or [],1):
        if not isinstance(item,dict): continue
        rec=_item_record(item)
        slots.append({
            "slot": item.get("inventoryId") or f"Equipment {index}",
            "item_id": item.get("id") or str(index),
            "item": rec,
        })

    passives=character.get("passives") or {}
    hashes=list(passives.get("hashes") or []) if isinstance(passives,dict) else []
    specialisations=passives.get("specialisations") or {} if isinstance(passives,dict) else {}
    spec_count=sum(len(v or []) for v in specialisations.values()) if isinstance(specialisations,dict) else 0
    quest_stats=list(passives.get("quest_stats") or []) if isinstance(passives,dict) else []

    class_name=str(character.get("class") or "")
    meta=character.get("metadata") or {}
    return {
        "source": source_label or f"GGG API · {name}",
        "source_type":"ggg-character",
        "has_pob_xml":False,
        "character_name":name,
        "ggg_character_id":character.get("id") or "",
        "league":character.get("league") or "",
        "class_name":class_name,
        "ascendancy":class_name,
        "level":int(character.get("level") or 0),
        "experience":int(character.get("experience") or 0),
        "target_version":meta.get("version") if isinstance(meta,dict) else None,
        "main_socket_group":None,
        "main_skill":preview_main,
        "main_skill_inferred":bool(preview_main),
        "player_stats":{},
        "all_player_stats":{},
        "player_stat_count":0,
        "skills":groups,
        "skill_group_count":len(groups),
        "tree":{
            "allocated_nodes":len(hashes)+spec_count,
            "base_hashes":hashes,
            "specialisations":specialisations if isinstance(specialisations,dict) else {},
            "quest_stats":quest_stats,
            "ascendancy_internal_id":"",
            "tree_version":meta.get("version") if isinstance(meta,dict) else None,
        },
        "items":{
            "count":len(slots),
            "defined_count":len(slots),
            "items":[x["item"] for x in slots],
            "slots":slots,
            "unresolved_slots":[],
        },
        "jewels_count":len(character.get("jewels") or []),
        "config":{"count":0,"values":{}},
        "snapshot_at":_now_iso(),
    }


def status() -> dict:
    cfg=load_config()
    token=_load_token()
    authenticated=bool(token and token.get("access_token"))
    return {
        "configured":bool(cfg.get("client_id")),
        "authenticated":authenticated,
        "client_id":cfg.get("client_id") or "",
        "contact":cfg.get("contact") or "",
        "scopes":SCOPES,
        "registration_note":REGISTRATION_NOTE,
        "registration_new_apps_available":False,
        "token_storage":(
            "Windows DPAPI" if os.name=="nt" else "fallback local (test/non-Windows)"
        ),
        "pending":bool(_PENDING),
        "policy_note":"Não reutiliza o client_id do Path of Building ou do poe.ninja.",
    }


def import_snapshot_json(payload) -> dict:
    if isinstance(payload,str):
        try: data=json.loads(payload)
        except json.JSONDecodeError as exc: raise ValueError("JSON do snapshot inválido.") from exc
    else:
        data=payload
    if not isinstance(data,dict): raise ValueError("Snapshot precisa ser um objeto JSON.")
    char=data.get("character") if isinstance(data.get("character"),dict) else data
    return {"character":char,"summary":character_to_summary(char,"GGG API · snapshot JSON")}
