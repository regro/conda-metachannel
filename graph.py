import bz2
from collections import deque
import typing

import networkx
import requests
from pandas.io import json


def build_repodata_graph(repodata):
    G = networkx.DiGraph()
    for p, v in repodata['packages'].items():
        name = v['name']
        G.add_node(name)

        G.nodes[name].setdefault('packages', {})
        G.nodes[name]['packages'][p] = v

        for dep in v['depends']:
            dep_name, _, _ = dep.partition(' ')
            G.add_edge(dep_name, name)

    return G


def recursive_parents(G: networkx.DiGraph, nodes):
    if isinstance(nodes, str):
        nodes = [nodes]

    done = set()
    todo = deque(nodes)
    while todo:
        n = todo.popleft()
        if n in done:
            continue
        children = list(G.predecessors(n))
        todo.extend(children)
        done.add(n)
    return done


class RawRepoData:
    _cache = {}

    def __init__(self, channel, arch='linux-64'):
        data = requests.get(f'https://conda.anaconda.org/{channel}/{arch}/repodata.json.bz2')
        repodata = json.loads(bz2.decompress(data.content))
        self.graph = build_repodata_graph(repodata)


def get_repo_data(channel, arch):
    key = (channel, arch)
    if key not in RawRepoData._cache:
        RawRepoData._cache[key] = RawRepoData(channel, arch)
    return RawRepoData._cache[key]


class ArtifactGraph:

    _cache = {}

    def __init__(self, channel, arch, constraints):
        self.raw = get_repo_data(channel, arch)
        self.constrain_graph(self.raw.graph, constraints)

    def constrain_graph(self, graph, constraints):
        if constraints:
            nodes = recursive_parents(graph, constraints)
            subset = self.raw.graph.subgraph(nodes)
            self.constrained_graph = subset
        else:
            self.constrained_graph = self.raw.graph

    def repodata_json_dict(self):
        packages = {}
        for n in self.constrained_graph:
            packages.update(self.constrained_graph.nodes[n].get('packages', {}))
        return {'packages': packages}

    def repodata_json(self):
        out_string = json.dumps(self.repodata_json_dict())
        return out_string

    def repodata_json_bzip(self):
        import bz2
        out_bytes = bz2.compress(self.repodata_json().encode('utf8'), compresslevel=1)
        return out_bytes


def get_artifact_graph(channel, arch, constraints) -> ArtifactGraph:
    if isinstance(constraints, str):
        constraints = [constraints]

    key = (channel, arch, tuple(sorted(constraints)))
    if key not in ArtifactGraph._cache:
        ArtifactGraph._cache[key] = ArtifactGraph(channel, arch, constraints)
    return ArtifactGraph._cache[key]
