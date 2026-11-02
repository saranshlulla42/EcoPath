"""Paired species cluster bootstrap, optionally crossed with training seeds."""
from collections import defaultdict
import random


def paired_bootstrap(rows, examples, method_a, method_b, metric, seeds, draws, seed):
    if draws < 1:
        raise ValueError('draws must be positive')
    index = {}
    for row in rows:
        key = (row['method'], row['training_seed'], row['example_id'])
        if key in index:
            raise ValueError('duplicate scores; select latest attempts first')
        index[key] = row
    clusters = defaultdict(list)
    for e in examples:
        clusters[e['species_id']].append(e['example_id'])
    eligible = {}
    excluded = []
    for species, ids in clusters.items():
        values = {}
        for method in (method_a, method_b):
            values[method] = {}
            for training_seed in seeds[method]:
                cells = [index.get((method, training_seed, eid)) for eid in ids]
                if all(c and metric in c['score']['metrics'] for c in cells):
                    defined=[c['score']['metrics'][metric]['value'] for c in cells if c['score']['metrics'][metric]['value'] is not None]
                    if defined:
                        values[method][training_seed] = sum(defined)/len(defined)
        if all(set(values[m]) == set(seeds[m]) and values[m] for m in (method_a,method_b)):
            eligible[species] = values
        else:
            excluded.append(species)
    ids = sorted(eligible)
    if not ids:
        return {'status':'no_complete_pairs','eligible_species':0,'excluded_species':excluded, 'estimate':None,'ci95':None}
    def delta(selected, sampled_seeds):
        return sum(sum(eligible[s][method_b][k] for k in sampled_seeds[method_b])/len(sampled_seeds[method_b])
                   -sum(eligible[s][method_a][k] for k in sampled_seeds[method_a])/len(sampled_seeds[method_a])
                   for s in selected)/len(selected)
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        selected = rng.choices(ids, k=len(ids))
        # Same sampled seeds across all species in each replicate. They are
        # complete training runs, not independent per-example perturbations.
        if set(seeds[method_a]) == set(seeds[method_b]) and None not in seeds[method_a]:
            common=rng.choices(seeds[method_a],k=len(seeds[method_a]))
            sampled_seeds={method_a:common,method_b:common}
        else:
            sampled_seeds = {m:rng.choices(seeds[m], k=len(seeds[m])) for m in (method_a,method_b)}
        samples.append(delta(selected, sampled_seeds))
    samples.sort()
    def quantile(p):
        x = (len(samples)-1)*p
        low = int(x)
        high = min(low+1,len(samples)-1)
        return samples[low]+(samples[high]-samples[low])*(x-low)
    per_seed = {m:{str(k):sum(eligible[s][m][k] for s in ids)/len(ids) for k in seeds[m]} for m in (method_a,method_b)}
    return {'status':'computed', 'difference':f'{method_b} minus {method_a}', 'metric':metric,
            'estimate':delta(ids,seeds),'ci95':[quantile(.025),quantile(.975)], 'eligible_species':len(ids),
            'excluded_species':excluded, 'variants_by_species':{s:clusters[s] for s in ids},
            'training_seeds':seeds, 'per_seed':per_seed, 'bootstrap_seed':seed,'draws':draws,
            'method':'paired species cluster percentile bootstrap with crossed within-method training-seed resampling',
            'training_seed_variation_estimable':{m:len([s for s in seeds[m] if s is not None])>1 for m in (method_a,method_b)},
            'caution':'A single adapted training seed cannot estimate training-seed variation; small species samples limit inference.'}
