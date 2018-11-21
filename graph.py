import bz2
from collections import deque
import typing
import operator

import networkx
import requests
from pandas.io import json

from cachetools import LRUCache, cachedmethod, TTLCache


def build_repodata_graph(repodata, arch):
    G = networkx.DiGraph()
    for p, v in repodata['packages'].items():
        name = v['name']
        G.add_node(name)
        G.nodes[name].setdefault('arch', set())
        G.nodes[name]['arch'].add(arch)

        G.nodes[name].setdefault(f'packages_{arch}', {})
        G.nodes[name][f'packages_{arch}'][p] = v

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
        # TODO: this seems to cause issues with root nodes like zlib
        children = list(G.predecessors(n))
        todo.extend(children)
        done.add(n)
    return done


class RawRepoData:
    _cache = TTLCache(maxsize=100, ttl=600)

    def __init__(self, channel, arch='linux-64'):
        data = requests.get(f'https://conda.anaconda.org/{channel}/{arch}/repodata.json.bz2')
        repodata = json.loads(bz2.decompress(data.content))
        self.arch = arch
        self.graph = build_repodata_graph(repodata, arch)


def get_repo_data(channel, arch):
    key = (channel, arch)
    if key not in RawRepoData._cache:
        RawRepoData._cache[key] = RawRepoData(channel, arch)
    return RawRepoData._cache[key]


class ArtifactGraph:

    _cache = {}

    def __init__(self, channel, arch, constraints):
        self.raw = get_repo_data(channel, arch)
        self.arch = arch
        self.noarch = get_repo_data(channel, 'noarch')
        self.constrain_graph(self.raw.graph, self.noarch.graph, constraints)
        self.cache = TTLCache(100, ttl=600)

    def constrain_graph(self, graph, noarch_graph, constraints):
        # Since noarch is solved along with our normal channel we need to combine the two for our effective
        # graph.
        combined_graph = networkx.compose(graph, noarch_graph)
        if constraints:
            nodes = recursive_parents(combined_graph, constraints)
            subset = self.raw.graph.subgraph(nodes)
            self.constrained_graph = subset
        else:
            self.constrained_graph = self.raw.graph

    def repodata_json_dict(self):
        packages = {}
        for n in self.constrained_graph:
            packages.update(self.constrained_graph.nodes[n].get(f'packages_{self.arch}', {}))
        return {'packages': packages}

    @cachedmethod(operator.attrgetter('cache'))
    def repodata_json(self):
        out_string = json.dumps(self.repodata_json_dict())
        return out_string

    @cachedmethod(operator.attrgetter('cache'))
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
