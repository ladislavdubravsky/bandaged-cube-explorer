#!/usr/bin/env python3
"""Validate the author's 2015 templates and compare exact PocketCube policies.

Run: v2/.venv/bin/python v2/research/compare_pocket_human_solution.py --output PATH
Needs the built bce_v2 extension and GAP. All move averages exhaust the 432
reference-shape colorings, exclude shape restoration, and simplify the complete
face word. Historical family policies are synthesized: the article does not
specify all recognition cases or a unique case policy.
"""
from __future__ import annotations
import argparse
from heapq import heappop, heappush
from itertools import combinations
import json
from pathlib import Path
import bce_v2 as c
from bce_v2.block_actions import BlockInventory, _NORMALS, _rotate, _inverse, _compose, _IDENTITY
from bce_v2.loop_rotations import rotation_tuple, rotate_moves
from bce_v2._moves import _simplified_moves
from bce_v2.human_algorithms import _metrics

NOTEBOOK_LABELS = [1,1,2,1,1,2,3,3,0,0,0,4,0,0,4,5,5,6,0,0,4,0,0,4,5,5,6]
SOURCE = "https://ladislavdubravsky.wordpress.com/2015/03/21/justin-pocket-cube-colored/"
ROT = rotation_tuple("x' y")
FRAMES = (_IDENTITY, ROT, _compose(ROT, ROT))
FACE_AT_NORMAL = {normal: face for face, normal in _NORMALS.items()}
IDENTITY = tuple(range(48))
DISPLAYS = {
    'A1': "R F' U' F R' rot F' R U2 R' F rot' R F' U F R'",
    'A2': "R F' U' F R' rot R F' U' R U R' U' R' F rot F' R U2 R' F rot' R F' U F R' rot'",
    'A3': "R F' U' F R' F' R U F R' rot R' D R D' rot R F' U F R' rot",
}

def then(a, b):
    return tuple(b[x] for x in a)

def inverse(p):
    r = [0] * 48
    for a,b in enumerate(p): r[b] = a
    return tuple(r)

def inverse_word(w):
    return ' '.join(t if t.endswith('2') else t[:-1] if t.endswith("'") else t+"'"
                    for t in reversed(w.split()))

def compile_display(word, frame=_IDENTITY):
    out = []
    for t in word.split():
        if t in ('rot', "rot'"):
            frame = _compose(ROT if t == 'rot' else _inverse(ROT), frame)
        else:
            out.append(FACE_AT_NORMAL[_rotate(_inverse(frame), _NORMALS[t[0]])] + t[1:])
    return _simplified_moves(out), frame

def costs(word):
    ts = word.split()
    return len(ts), sum(2 if t.endswith('2') else 1 for t in ts)

def alphabet(basis):
    found = {}
    for name, word, p in basis:
        found.setdefault(p, (name, word, p))
        found.setdefault(inverse(p), (name+"^-1", inverse_word(word), inverse(p)))
    return tuple(found.values())

def enumerate_words(basis, *, weighted=False):
    """The existing compiler's generator-count BFS, or additive HTM Dijkstra."""
    alpha = alphabet(basis)
    if not weighted:
        entries = {IDENTITY: ('', ())}
        queue = [IDENTITY]
        for p in queue:
            word, labels = entries[p]
            for name, w, q in alpha:
                r = then(p,q)
                if r not in entries:
                    entries[r] = ((word+' '+w).strip(), labels+(name,))
                    queue.append(r)
        return entries
    distances = {IDENTITY: (0, 0, ())}
    entries = {IDENTITY: ('', ())}
    heap = [(0,0,(),IDENTITY)]
    while heap:
        htm,n,labels,p = heappop(heap)
        if distances[p] != (htm,n,labels): continue
        word,_ = entries[p]
        for name,w,q in alpha:
            r = then(p,q)
            rank = (htm+costs(w)[0], n+1, labels+(name,))
            if r not in distances or rank < distances[r]:
                distances[r] = rank
                entries[r] = ((word+' '+w).strip(), rank[2])
                heappush(heap,(*rank,r))
    return entries

def metrics(words):
    totals = [0,0]; worst = [0,0]
    for word in words:
        pair = costs(_simplified_moves(word.split()))
        for j,v in enumerate(pair): totals[j] += v; worst[j] = max(worst[j],v)
    return {'states':len(words),'mean_htm':totals[0]/len(words),'worst_htm':worst[0],
            'total_htm':totals[0],'mean_qtm':totals[1]/len(words),'worst_qtm':worst[1],
            'total_qtm':totals[1]}

def single_block_chain(basis, inventory, feature_cells):
    """Exactly the first-BFS-representative policy used by _compile_plan."""
    entries = enumerate_words(basis)
    assert len(entries) == 432
    actions = {p: inventory.action(p) for p in entries}
    current = list(entries)
    stages = []; policies = []
    for cells in feature_cells:
        index = next(i for i,b in enumerate(inventory.blocks) if b.cells == tuple(cells))
        def observe(p):
            a = actions[p]
            return (a.destinations[index], a.phases[index])
        solved = observe(IDENTITY)
        reps = {}
        for p in current: reps.setdefault(observe(p),p)
        policy = {}
        for observation,p in reps.items():
            word,labels = entries[p]
            policy[observation] = (inverse(p), inverse_word(word), labels)
        following = [p for p in current if observe(p) == solved]
        stages.append({'cells':list(cells),'order_before':len(current),
                       'order_after':len(following),'index':len(reps)})
        policies.append((index,policy))
        current = following
    assert current == [IDENTITY]
    words=[]
    for initial in entries:
        p=initial; word=[]
        for index,policy in policies:
            a=actions[p]; correction,w,_=policy[(a.destinations[index],a.phases[index])]
            p=then(p,correction); word.extend(w.split())
        assert p==IDENTITY
        words.append(' '.join(word))
    return {'policy':'existing first-representative generator-count BFS',
            'stages':stages,'metrics':metrics(words)}

def family_policies(group, inventory, stage_specs, weighted):
    """Choose corrections by first BFS or additive HTM shortest representative.

    These are exact whole-family observation tables, not a reconstruction of
    the article's unspecified recognition policy. Later allowed alphabets are
    precisely its stated squared / three-conjugate stage macros.
    """
    actions={p:inventory.action(p) for p in group}
    current=list(group); policies=[]; stages=[]
    for name,indices,basis in stage_specs:
        def observe(p):
            a=actions[p]
            return tuple(x for i in indices for x in (a.destinations[i],a.phases[i]))
        solved=observe(IDENTITY)
        entries=enumerate_words(basis,weighted=weighted)
        available=[p for p in entries if p in current]
        if weighted:
            # Dijkstra insertion order is discovery order, not settled cost order.
            lookup={n:costs(w)[0] for n,w,p in alphabet(basis)}
            available.sort(key=lambda p:(sum(lookup[n] for n in entries[p][1]),
                                         len(entries[p][1]),entries[p][1]))
        reps={}
        for p in available: reps.setdefault(observe(p),p)
        observations={observe(p) for p in current}
        assert set(reps)==observations
        policy={o:(inverse(p),inverse_word(entries[p][0])) for o,p in reps.items()}
        following=[p for p in current if observe(p)==solved]
        stages.append({'family':name,'order_before':len(current),'order_after':len(following),
                       'index':len(reps),'nontrivial_cases':len(reps)-1,
                       'corrections':[{'observation':list(o),'word':_simplified_moves(w.split()),
                                       'htm':costs(_simplified_moves(w.split()))[0]}
                                      for o,(_,w) in sorted(policy.items())]})
        policies.append((indices,policy)); current=following
    assert current==[IDENTITY]
    words=[]
    for initial in group:
        p=initial; word=[]
        for indices,policy in policies:
            a=actions[p];o=tuple(x for i in indices for x in (a.destinations[i],a.phases[i]))
            q,w=policy[o];p=then(p,q);word.extend(w.split())
        assert p==IDENTITY
        words.append(' '.join(word))
    return {'policy':'additive HTM shortest stage representative' if weighted else 'generator-count BFS stage representative',
            'historical_literal_policy':False,'stages':stages,'metrics':metrics(words)}

def run(timeout):
    reference=c.Shape(NOTEBOOK_LABELS)
    historical=reference.rotated(14)
    assert historical==reference.rotated(16)
    inventory=BlockInventory(historical)
    old_complete=c.isotropy_loops(historical)
    records={}; variants=[]
    for name,display in DISPLAYS.items():
        for j,frame in enumerate(FRAMES):
            word,final=compile_display(display,frame)
            assert final==frame
            state=c.State(historical).apply(word)
            assert state.shape==historical
            p=state.sticker_permutation
            variants.append((f'{name}_rot{j}',word,p))
            if j==0:
                matches=[{'generator_id':g.id,'htm':g.htm_length,
                          'inverse':g.permutation!=p,'word':g.turn_sequence}
                         for g in old_complete.generators
                         if p in (g.permutation,inverse(g.permutation))]
                records[name]={'display_word':display,'face_word_historical_grip':word,
                               'face_word_notebook_grip':rotate_moves(word,"x'"),
                               'htm':costs(word)[0],'qtm':costs(word)[1],
                               'action':inventory.action(p).to_dict(),
                               'power2_action':(inventory.action(p)**2).notation,
                               'matching_native_generators':matches}
    literal=[v for v in variants if v[0].endswith('rot0')]
    all_group=enumerate_words(variants)
    assert len(all_group)==432
    original_analysis=c.analyze_isotropy(reference,timeout=timeout)
    selection=c.select_human_chain(original_analysis,timeout=timeout)
    repertoire=c.generator_human_repertoire(selection.method,timeout=timeout)
    method=repertoire.method
    current=[(f'M{i}',g.turn_sequence,g.permutation) for i,g in enumerate(method.generators,1)]
    for record in records.values():
        historical_p=c.State(reference).apply(record['face_word_notebook_grip']).sticker_permutation
        matches=[]
        for name,word,p in current:
            for rotation in ('',*c.bandage_symmetries(reference)):
                regripped=c.State(reference).apply(rotate_moves(word,rotation)).sticker_permutation
                if historical_p in (regripped,inverse(regripped)):
                    matches.append({'current_master':name,'rotation':rotation,
                                    'inverse':historical_p!=regripped})
        record['matching_current_master_regrips']=matches
    notebook_inventory=BlockInventory(reference)
    feature_cells=[s.feature.cells for s in method.stages]
    old_notebook=[(n,rotate_moves(w,"x'"),c.State(reference).apply(rotate_moves(w,"x'")).sticker_permutation)
                  for n,w,p in variants]
    old_three=[old_notebook[i] for i in (0,1,3)] # A1, rot A1, A2; all 432.
    assert len(enumerate_words(old_three))==432
    full_triples=[]
    for indices in combinations(range(len(old_notebook)),3):
        basis=[old_notebook[i] for i in indices]
        if len(enumerate_words(basis))==432:
            full_triples.append((sum(costs(w)[0] for n,w,p in basis),indices))
    min_cost, min_indices=min(full_triples)
    old_cheapest=[old_notebook[i] for i in min_indices]
    current_policy=single_block_chain(current,notebook_inventory,feature_cells)
    exact_actual=_metrics(method,{p:notebook_inventory.action(p) for p in method._permutations})
    for key,value in current_policy['metrics'].items(): assert exact_actual[key]==value
    stage_macros={}
    for name,display in [('corner_twist',DISPLAYS['A2']+' '+DISPLAYS['A2']),
                         ('big_cycle',DISPLAYS['A3']+' '+DISPLAYS['A3']),
                         ('big_swap',' rot '.join([DISPLAYS['A2']]*3)+' rot')]:
        word,frame=compile_display(display);assert frame==_IDENTITY
        p=c.State(historical).apply(word).sticker_permutation
        stage_macros[name]={'face_word':word,'htm':costs(word)[0],'qtm':costs(word)[1],
                            'action':inventory.action(p).to_dict()}
    # Use the exact article C3 frame, avoiding an assumed standard spelling.
    def macro_variants(name):
        rec=stage_macros[name];out=[]
        for j,frame in enumerate(FRAMES):
            w,_=compile_display(rec['face_word'],frame)
            out.append((f'{name}_rot{j}',w,c.State(historical).apply(w).sticker_permutation))
        return out
    small=tuple(i for i,b in enumerate(inventory.blocks) if b.kind=='Edge')
    big=tuple(i for i,b in enumerate(inventory.blocks) if b.kind=='Pair')
    corners=tuple(i for i,b in enumerate(inventory.blocks) if b.kind=='Corner')
    specs=[('all three small edges',small,[v for v in variants if v[0].startswith(('A1','A2'))]),
           ('all three big edges',big,macro_variants('big_cycle')+macro_variants('big_swap')),
           ('both free corners',corners,macro_variants('corner_twist'))]
    weighted_controls={}
    for name,basis in [('current_three_fixed_grip',current),('historical_three_complete_fixed_grip',old_three),
                       ('historical_minimum_definition_three_fixed_grip',old_cheapest),
                       ('historical_three_templates_with_C3',old_notebook)]:
        entries=enumerate_words(basis,weighted=True)
        assert len(entries)==432
        weighted_controls[name]={'objective':'shortest additive HTM over fixed macro alphabet; not shortest face word',
                                 'metrics':metrics([w for w,labels in entries.values()])}
    return {'format':'bce-v2-pocket-human-comparison','version':1,'source':SOURCE,
            'scope':'all 432 reference-shape colored states; shape restoration excluded; full word simplified',
            'historical_reference_rotation':{'notebook_active_rotation_index':14,'notebook_active_rotation_word':"x'",
                                             'article_rot_active_rotation_word':"x' y",'article_rot_face_cycle':'R -> F -> D -> R'},
            'shape_count':original_analysis.loops.shape_count,'group_order':432,
            'historical_algorithms':records,'historical_literal_fixed_grip_group_order':len(enumerate_words(literal)),
            'historical_C3_template_group_order':len(all_group),
            'historical_fixed_frame_basis_scan':{'candidate_triples':84,'complete_triples':len(full_triples),
                                                'minimum_definition_htm':min_cost,
                                                'chosen_minimum_basis':[n for n,w,p in old_cheapest],
                                                'two_templates_A1_A3_with_C3_group_order':len(enumerate_words([v for v in variants if v[0].startswith(('A1','A3'))]))},
            'historical_stage_macros':stage_macros,
            'current_displayed_repertoire':{'metrics':exact_actual,'generators':[{'id':g.id,'face_word':g.turn_sequence,'htm':g.htm_length} for g in method.generators],
                                             'metadata':repertoire.metadata},
            'current_selected_before_repertoire_rebuild':{'metrics':_metrics(selection.method,{p:selection.method.inventory.action(p) for p in selection.method._permutations})},
            'same_chain_same_BFS_policy':{'current_three':current_policy,
                                         'historical_three_complete':{'basis':[n for n,w,p in old_three],**single_block_chain(old_three,notebook_inventory,feature_cells)},
                                         'historical_minimum_definition_three':{'basis':[n for n,w,p in old_cheapest],**single_block_chain(old_cheapest,notebook_inventory,feature_cells)},
                                         'historical_templates_with_C3':single_block_chain(old_notebook,notebook_inventory,feature_cells)},
            'historical_family_stage_policies':{'BFS':family_policies(all_group,inventory,specs,False),
                                                'weighted':family_policies(all_group,inventory,specs,True)},
            'weighted_full_group_controls':weighted_controls,
            'notes':['The article specifies stage recipes, not a complete case table; family-stage measurements use synthesized policies.',
                     'The three memorized templates plus C3 regrips represent nine fixed-frame executable algorithms.',
                     'A2 twists the two free corners in place in the verified action; the article describes an additional corner transposition.',
                     'Whole-cube regrips have zero face-turn cost; rotation/regrip count and human recognition cost are not scored.']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--timeout',type=float,default=120)
    args=parser.parse_args()
    result=run(args.timeout)
    text=json.dumps(result,indent=2,sort_keys=True)+'\n'
    if args.output: args.output.write_text(text,encoding='utf-8')
    else: print(text,end='')

if __name__=='__main__': main()
