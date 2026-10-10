"""Synthetic records for tests only. NEVER used to seed the application database.

Field layout comes from RePoE's public schemas; values and names below are test data.
"""
import json
from pathlib import Path

def datasets():
    types=['Spell','Attack','Fire','Area','Damage','DamageOverTime','Minion','AND','OR','NOT','Channel','SkillConsumesIgnite','CannotConsumeCharges']
    skills={
        'outer-flame':{'id':'TestFlameEffect','active_skill':{'display_name':'Test flame','types':['Spell','Fire','Area','Damage','Channel'],
                         'description':'A synthetic [Fire] spell for parser tests.'},'static':{'stats':{'test_fire_damage':25}}},
        'outer-oil':{'id':'TestOilEffect','types':['Attack','Area'],'description':'Synthetic ground with [Ignite] in its description.'},
        'outer-red':{'id':'TestRedEffect','support_gem':{'allowed_types':['Spell'],'excluded_types':[],
                         'added_types':['SkillConsumesIgnite'],'added_minion_types':[]}},
        'outer-blue':{'id':'TestBlueEffect','allowed_types':['Spell'],'excluded_types':[],'added_types':[],
                         'static':{'stats':{'test_ignite_magnitude':30},'stat_text':{'x':'Test value for [Ignite].'}}},
        'outer-green':{'id':'TestGreenEffect','allowed_types':['Attack'],'excluded_types':[],'added_types':[]},
        'outer-drain':{'id':'TestDotEffect','allowed_types':['Spell','DamageOverTime','AND'],'excluded_types':[],
                         'added_types':[]},
        'outer-child':{'id':'TestChild','active_skill':{'types':['Spell','DamageOverTime']}},
        'outer-missing':{'id':'TestMissingEffect','added_types':[]},
        'outer-minion':{'id':'TestMinionEffect','allowed_types':['Spell'],'excluded_types':[],
                         'added_types':[],'added_minion_types':['SkillConsumesIgnite']},
        'outer-no':{'id':'TestNoEffect','allowed_types':['Spell'],'excluded_types':[],'added_types':['CannotConsumeCharges']},
    }
    gems={}
    def gem(sid,name,gt,color,grants,tags,text=''):
        gems[sid]={'base_item':{'id':sid,'display_name':name,'release_state':'released'},'gem_type':gt,
                   'color':color,'grants_skills':grants,'tags':tags,'support_text':text,
                   'requirement_weights':{'strength':100 if color=='r' else 0,'dexterity':100 if color=='g' else 0,'intelligence':100 if color=='b' else 0}}
    gem('test/flame','Flameblast [TEST]','skill','b',['TestFlameEffect'],['spell','area','fire','channelling','intelligence'])
    gem('test/oil','Oil [TEST]','skill','g',['TestOilEffect'],['attack','area'])
    gem('test/red','Red consumer [TEST]','support','r',['TestRedEffect'],['support','fire'],
        'Synthetic support: [Consume|Consumes] [Ignite].')
    gem('test/blue','Blue modifier [TEST]','support','b',['TestBlueEffect'],['support','fire','duration'],
        'Synthetic support referencing [Ignite].')
    gem('test/green','Green attack [TEST]','support','g',['TestGreenEffect'],['support','projectile'],
        'Synthetic support for [Attack] skills.')
    gem('test/dot','DoT requirement [TEST]','support','b',['TestDotEffect'],['support'],
        'Synthetic support requiring Spell and DamageOverTime.')
    gem('test/multi','Multiple effects [TEST]','skill','b',['TestFlameEffect','TestChild'],['spell','fire'])
    gem('test/missing','Unknown rules [TEST]','support','w',['TestMissingEffect'],['support'])
    gem('test/minion','Minion effect [TEST]','support','b',['TestMinionEffect'],['support','minion'])
    gem('test/no','No consumption [TEST]','support','b',['TestNoEffect'],['support'])
    return gems,skills,types

def write_fixture(folder):
    d=Path(folder);d.mkdir(parents=True,exist_ok=True)
    for name,data in zip(['skill_gems.min.json','skills.min.json','active_skill_types.min.json'],datasets()):
        (d/name).write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    (d/'manifest.json').write_text(json.dumps({'repoe_version':'TEST - synthetic fixture'}),encoding='utf-8')
    return d
