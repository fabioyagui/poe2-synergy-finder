"""Evidence first: mechanical relations, not tags scored as build power.
Rules act on all entities, not on a hand-picked list of gem names. Unrecognized
language and stats remain searchable. A mention is never promoted to a producer.
"""
from __future__ import annotations
import re

VERSION='semantics-0.8.0'
SEMANTIC={'PRODUCES','ENABLES','GENERATES','CREATES','CONSUMES','REQUIRES','AMPLIFIES','REDUCES','MODIFIES','PREVENTS','PREVENTS_CONSUMPTION'}
PRODUCERS={'PRODUCES','ENABLES','GENERATES','CREATES'}
LABELS={'IGNITE':'Ignite','FREEZE':'Freeze','SHOCK':'Shock','CHILL':'Chill','BLEEDING':'Bleeding','POISON':'Poison',
        'POWERCHARGE':'Power Charge','FRENZYCHARGE':'Frenzy Charge','ENDURANCECHARGE':'Endurance Charge',
        'RAGE':'Rage','ENERGY':'Energy','REMNANT':'Remnant','FISSURE':'Fissure',
        'LIFE':'Life','MANA':'Mana','ENERGYSHIELD':'Energy Shield','FIREDAMAGE':'Fire Damage',
        'COLDDAMAGE':'Cold Damage','LIGHTNINGDAMAGE':'Lightning Damage','PHYSICALDAMAGE':'Physical Damage',
        'CHAOSDAMAGE':'Chaos Damage','ATTACKDAMAGE':'Attack Damage','SPELLDAMAGE':'Spell Damage',
        'CASTSPEED':'Cast Speed','ATTACKSPEED':'Attack Speed','AREA':'Area of Effect','CRITICALHIT':'Critical Hit',
        'ARMOURBREAK':'Armour Break','EXPOSURE':'Exposure','OILGROUND':'Oil Ground'}
PATTERNS={
 'IGNITE':r'\b(?:ignites?|ignited|igniting)\b','FREEZE':r'\b(?:freezes?|frozen|freezing)\b',
 'SHOCK':r'\b(?:shocks?|shocked|shocking)\b','CHILL':r'\b(?:chills?|chilled|chilling)\b',
 'BLEEDING':r'\b(?:bleeding|bleeds?)\b','POISON':r'\b(?:poisons?|poisoned|poisoning)\b',
 'POWERCHARGE':r'\bpower charges?\b','FRENZYCHARGE':r'\bfrenzy charges?\b','ENDURANCECHARGE':r'\bendurance charges?\b',
 'RAGE':r'\brage\b','REMNANT':r'\bremnants?\b','FISSURE':r'\bfissures?\b','ENERGY':r'\benergy\b(?! shield)',
 'OILGROUND':r'\b(?:oiled|oil) ground\b','LIFE':r'\blife\b','MANA':r'\bmana\b','ENERGYSHIELD':r'\benergy shield\b',
 'FIREDAMAGE':r'\bfire damage\b','COLDDAMAGE':r'\bcold damage\b','LIGHTNINGDAMAGE':r'\blightning damage\b',
 'PHYSICALDAMAGE':r'\bphysical damage\b','CHAOSDAMAGE':r'\bchaos damage\b',
 'ATTACKDAMAGE':r'\battack damage\b','SPELLDAMAGE':r'\bspell damage\b',
 'CASTSPEED':r'\bcast(?:ing)? speed\b','ATTACKSPEED':r'\battack speed\b','AREA':r'\barea of effect\b',
 'CRITICALHIT':r'\bcritical (?:hits?|strikes?)\b','ARMOURBREAK':r'\b(?:armour break|break(?:s|ing)? armour|broken armour)\b',
 'EXPOSURE':r'\bexposure\b'}

# Explicit, unambiguous stat IDs seen in the RePoE export. These are mechanic rules,
# not item names. Novel IDs stay raw until interpreted or translated by the source.
STAT_RULES={
 'base_ignite_effect_+%':('IGNITE','magnitude'),
 'ignite_duration_+%':('IGNITE','duration'),
 'base_ignite_duration_+%':('IGNITE','duration'),
 'base_shock_effect_+%':('SHOCK','magnitude'),
 'base_chill_effect_+%':('CHILL','magnitude'),
 'base_bleeding_damage_+%':('BLEEDING','damage'),
 'poison_duration_+%':('POISON','duration'),
 'fire_damage_+%':('FIREDAMAGE','damage'), 'cold_damage_+%':('COLDDAMAGE','damage'),
 'lightning_damage_+%':('LIGHTNINGDAMAGE','damage'),'physical_damage_+%':('PHYSICALDAMAGE','damage'),
 'chaos_damage_+%':('CHAOSDAMAGE','damage'),'spell_damage_+%':('SPELLDAMAGE','damage'),
 'attack_damage_+%':('ATTACKDAMAGE','damage'),'cast_speed_+%':('CASTSPEED','speed'),
 'attack_speed_+%':('ATTACKSPEED','speed'),'base_cast_speed_+%':('CASTSPEED','speed'),
 'area_of_effect_+%':('AREA','area'),'base_skill_area_of_effect_+%':('AREA','area'),
 'maximum_life_+%':('LIFE','maximum'),'maximum_mana_+%':('MANA','maximum'),
 'maximum_energy_shield_+%':('ENERGYSHIELD','maximum'),
}
AILMENTS={'IGNITE','FREEZE','SHOCK','CHILL','BLEEDING','POISON'}
RESOURCES={'POWERCHARGE','FRENZYCHARGE','ENDURANCECHARGE','RAGE','ENERGY','LIFE','MANA','ENERGYSHIELD'}


def relation(action,key,path,evidence,component='entity',**extra):
    return {'relation':action,'concept':key,'label':LABELS.get(key,key),'path':path,'evidence':evidence,
            'component':component,'basis':'text_rule','rule_id':VERSION,'scope':'unknown','condition':'',
            'aspect':'unspecified',**extra}

def text_relations(text,path,component='entity',default_scope='unknown'):
    from .importer import plain
    text=plain(text);out=[]
    # Keep full clauses as evidence/condition; never detach a conditional benefit.
    sentences=re.split(r'(?<=[.!?])\s+|[\r\n]+',text)
    for sentence in sentences:
        sentence=sentence.strip()
        if not sentence:continue
        s=sentence.lower();scope=default_scope
        if re.search(r'\b(?:minions?|companions?)\b',s):scope='minion'
        elif 'supported skill' in s:scope='supported_skill'
        elif re.search(r'\byour (?:hits?|skills?|attacks?|spells?)\b|\byou (?:gain|inflict|ignite)',s):scope='player'
        conditional=bool(re.search(r'\b(?:if|while|when|after|against|recently|on hit|on kill|chance|per |for each|nearby|presence)\b',s))
        condition=sentence if conditional else ''
        for key,pattern in PATTERNS.items():
            matches=list(re.finditer(pattern,s))
            if not matches:continue
            first=matches[0];before=s[:first.start()];after=s[first.end():]
            # Conditions affecting an incoming ailment are not outgoing application.
            self_ailment=key in AILMENTS and bool(re.search(r'\bon you\b|\byou are (?:ignited|frozen|shocked|chilled|poisoned|bleeding)',s))
            target=('SELF'+key) if self_ailment else key
            label=('Estado em você: '+LABELS[key]) if self_ailment else LABELS[key]
            def add(action,**kw):
                details={'scope':scope,'condition':condition,'label':label};details.update(kw)
                out.append(relation(action,target,path,sentence,component,**details))
            add('MENTIONS',basis='text_mention')
            # Descriptions saying "Supports skills ..." specify eligible skill types,
            # not that the support grants the property in that introductory sentence.
            if s.startswith(('supports skills','supports any skill','supports spells','supports attacks','supports melee')):continue
            # Negative effect applies to each ailment in an explicit inflict list.
            if key in AILMENTS and re.search(r'\b(?:cannot|can not|never)\b[^.;]*\b(?:inflict|cause|apply)\b',before):
                add('PREVENTS',aspect='application');continue
            if key in AILMENTS and re.search(r'\b(?:cannot|can not|never)\s*$',before):
                add('PREVENTS',aspect='application');continue
            if re.search(r'\b(?:cannot|never)\b[^.;]*\bconsum\w*\b',before):
                add('PREVENTS_CONSUMPTION');continue
            if re.search(r'\bconsum(?:e|es|ing)\b[^.;]*$',before) and key in AILMENTS|RESOURCES:
                # Text may describe consuming A to gain B: do not classify B as consumed.
                tail=re.split(r'\bconsum(?:e|es|ing)\b',before)[-1]
                if not re.search(r'\b(?:to|gain|grant|generate|trigger)\b',tail):add('CONSUMES');continue
            if key in AILMENTS:
                if re.search(r'\bchance to\s*(?:inflict\s+)?$',before) and not re.search(r'\b(?:increased|more|less|reduced)\b',before):
                    add('ENABLES',aspect='chance',condition=sentence);continue
                if re.search(r'\b(?:always|guaranteed to)\s*(?:inflict\s+)?$',before):
                    add('PRODUCES',aspect='application');continue
                if re.search(r'\b(?:inflict|inflicts|applies|apply)\s+(?:(?:an?|the)\s+)?$',before):
                    add('PRODUCES',aspect='application');continue
            if key in RESOURCES and re.search(r'\b(?:gain|gains|generate|generates|grant|grants|recover|recovers)\s+(?:up to\s+)?(?:\d+(?:\.\d+)?%?\s+)?(?:(?:a|an)\s+)?$',before):
                add('GENERATES');continue
            if key in {'FISSURE','OILGROUND','REMNANT'} and re.search(r'\b(?:create|creates|leave|leaves|generate|generates)\s+(?:(?:a|an|the)\s+)?$',before):
                add('CREATES');continue
            # A conditional reference is a requirement of that clause, not a global
            # inability to use a skill without the condition.
            req=re.search(r'\b(?:requires?|while|against|if|when)\b[^.;]*$',before)
            if req:
                add('REQUIRES',aspect='conditional_effect',condition=sentence)
                continue
            # Increased/reduced Chance to Ignite modifies chance, not guaranteed production.
            mod=re.search(r'\b(increased|more|reduced|less)\b',before)
            if mod:
                # "damage against ignited enemies" should have been caught as requirement.
                # Do not attach an increase in one clause to the next sentence/condition.
                aspect='magnitude' if 'magnitude' in s else 'duration' if 'duration' in s else 'chance' if 'chance' in s else 'damage' if 'damage' in s else 'capacity' if 'maximum' in s else 'unspecified'
                add('AMPLIFIES' if mod[1] in {'increased','more'} else 'REDUCES',aspect=aspect)
    return dedupe(out)

def dedupe(links):
    unique={}
    for l in links:
        sig=(l['relation'],l['concept'],l['component'],l['path'],l.get('aspect',''),l.get('evidence',''))
        unique.setdefault(sig,l)
    return list(unique.values())

def enrich(entity):
    """Adds evidence on all imported entities. Does not delete tags or original links."""
    scope='supported_skill' if entity['kind']=='SUPPORT' else 'player' if entity['kind'] not in {'SKILL','META'} else 'skill'
    out=[]
    for t in entity.get('texts',[]):
        component=t.get('component','supported_skill' if entity['kind']=='SUPPORT' else 'node' if entity['kind'] not in {'SKILL','META'} else 'entity')
        if not t.get('component'):
            # Keep evidence inside the resolved child, rather than giving child effects
            # to every skill supported by this gem.
            for cm in entity.get('components',[]):
                if cm.get('raw_key') and t['path'].startswith('skills.'+cm['raw_key']):
                    rule_paths=entity.get('rule_paths',{})
                    is_support_rule=entity['kind']=='SUPPORT' and any(isinstance(p,str) and p.startswith('skills.'+cm['raw_key']) for p in rule_paths.values())
                    component='supported_skill' if is_support_rule else cm['id'];break
        for l in text_relations(t['text'],t['path'],component,scope):
            if t.get('stat_ids'):l.update(stat_ids=t['stat_ids'],values=t.get('values'),translation_path=t.get('translation_path'),basis='translated_stat_rule' if l['relation']!='MENTIONS' else 'translated_stat_mention')
            out.append(l)
    # Passive stats are real fixed values. For gem level tables we deliberately do
    # not invent level, sign or scope by parsing fragments of identifiers.
    for s in entity.get('stats',[]):
        sid=s['id'];v=s.get('value')
        if s.get('semantic_fixed') and sid in STAT_RULES and isinstance(v,(int,float)) and not isinstance(v,bool) and v!=0:
            key,aspect=STAT_RULES[sid]
            out.append(relation('AMPLIFIES' if v>0 else 'REDUCES',key,s['path'],f'{sid} = {v}',
                component='node',scope='player',aspect=aspect,basis='exact_stat_id',value=v))
    for l in entity.get('links',[]):
        if l['relation'] in SEMANTIC and not l.get('basis'):
            l.update(basis='explicit_flag',rule_id=VERSION,scope=l.get('component','unknown'),condition='',aspect='unspecified')
    entity['links']=dedupe(entity.get('links',[])+out)
    entity['semantic_count']=sum(l['relation'] in SEMANTIC for l in entity['links'])
    return entity
