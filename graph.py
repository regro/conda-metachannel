import bz2
from collections import deque, defaultdict
from logging import getLogger

import os
import pathlib
import typing
import operator
import ruamel_yaml

import networkx
import requests
from pandas.io import json

from sortedcontainers import SortedList
from cachetools import LRUCache, cachedmethod, cached, TTLCache


logger = getLogger(__name__)


def build_repodata_graph(
    repodata: dict, arch: str, url_prefix: str
) -> networkx.DiGraph:
    G = networkx.DiGraph()
    for p, v in repodata["packages"].items():
        name = v["name"]
        G.add_node(name)
        G.nodes[name].setdefault("arch", set())
        G.nodes[name]["arch"].add(arch)

        G.nodes[name].setdefault(f"packages_{arch}", {})
        G.nodes[name][f"packages_{arch}"][p] = v
        v["url"] = f"{url_prefix}/{p}"

        for dep in v["depends"]:
            dep_name, _, _ = dep.partition(" ")
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
        # If we requested a package that does not exist in our graph, skip it
        if n not in G.nodes:
            # TODO: switch logging to loguru so that we can have context
            logger.warning(f"Package {n} not found in graph!")
            done.add(n)
            continue
        # TODO: this seems to cause issues with root nodes like zlib
        children = list(G.predecessors(n))
        todo.extend(children)
        done.add(n)
    return done


class RawRepoData:
    _cache = TTLCache(maxsize=100, ttl=600)

    def __init__(self, channel: str, arch: str = "linux-64"):
        logger.info(f"RETRIEVING: {channel}, {arch}")
        url_prefix = f"https://conda.anaconda.org/{channel}/{arch}"
        repodata_url = f"{url_prefix}/repodata.json.bz2"
        data = requests.get(repodata_url)
        repodata = json.loads(bz2.decompress(data.content))
        self.channel = channel
        self.arch = arch
        self.graph = build_repodata_graph(repodata, arch, url_prefix)
        logger.info(f"GRAPH BUILD FOR {repodata_url}")

    def __repr__(self):
        return f"RawRepoData({self.channel}/{self.arch})"


class FusedRepoData:
    """Utility class describing a set of repodatas treated as a single repository.

    Packages in prior repodatas take precendence.

    """

    def __init__(self, raw_repodata: typing.Sequence[RawRepoData], arch):
        logger.debug(f"FUSING: {raw_repodata}")
        self.arch = arch
        self.component_channels = [raw_repodata[0].channel]
        # TODO: Maybe cache this?
        G = raw_repodata[0].graph
        for i in range(1, len(raw_repodata)):
            raw = raw_repodata[i]
            self.component_channels.append(raw.channel)
            H = raw.graph
            G = networkx.compose(G, H)
            # for n in G.nodes:
            #     if n in H.nodes:
            #         # Fuse the package sets together.
            #         packages = H.nodes[n].get(f'packages_{arch}', {})
            #         G.nodes[n].setdefault(f'packages_{arch}', {})
            #         G.nodes[n][f'packages_{arch}'].update(packages)

        self.graph = G

    def __repr__(self):
        return f"FusedRepoData([{''.join(self.component_channels)}], {self.arch})"


def get_repo_data(channel: typing.List[str], arch: str) -> FusedRepoData:
    repodatas = []
    for c in channel:
        key = (c, arch)
        # TODO: This should happen in parallel
        if key not in RawRepoData._cache:
            RawRepoData._cache[key] = RawRepoData(c, arch)
        repodatas.append(RawRepoData._cache[key])
    return FusedRepoData(repodatas, arch)


def parse_constraints(constraints):
    package_constraints = []
    # functional constrains are used to constrain within packages.
    #
    # These can be version constraints. Build number constraints etc
    functional_constraints = defaultdict(set)
    for c in constraints:
        if c.startswith("--"):
            key, _, val = c.partition("=")
            functional_constraints[key].add(val)
        else:
            package_constraints.append(c)
    return package_constraints, functional_constraints


@cached(cache={})
def get_blacklist(blacklist_name, channel, arch):
    path = pathlib.Path("blacklists") / channel / (blacklist_name + ".yml")
    if path.exists():
        with path.open() as fo:
            obj = ruamel_yaml.safe_load(fo)
            return set(obj.get(arch, []))
    else:
        return set()


class ArtifactGraph:

    _cache = {}

    def __init__(self, channel, arch, constraints):
        self.arch = arch

        # TODO: These should run in parallel
        self.raw = get_repo_data(channel, arch)

        # TODO: Since solving the artifact graph happens twice for a given conda operation, once for arch and once for
        #       noarch we need to treat the noarch channel here as an arch channel.
        #       The choice of noarch standin as linux-64 is mostly convenience.
        #       In the future it may be wiser to just store the whole are collectively.

        if arch != "noarch":
            self.noarch = get_repo_data(channel, "noarch")
        else:
            self.noarch = get_repo_data(channel, "linux-64")

        self.package_constraints, self.functional_constraints = parse_constraints(
            constraints
        )

        self.constrain_graph(
            self.raw.graph, self.noarch.graph, self.package_constraints
        )
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
        all_packages = {}
        for n in self.constrained_graph:
            logger.debug(n)
            packages = self.constrained_graph.nodes[n].get(f"packages_{self.arch}", {})

            if "--max-build-no" in self.functional_constraints:
                # packages with build strings should always be included
                packages = self.constrain_by_build_number(packages)

            if "--untrack-features" in self.functional_constraints:
                packages = self.untrack_features(packages)

            if "--blacklist" in self.functional_constraints:
                for blacklist_name in self.functional_constraints["--blacklist"]:
                    packages = self.constrain_by_blacklist(packages, blacklist_name)

            if n == "blas":
                import pprint

                logger.debug(pprint.pformat(packages))
            all_packages.update(packages)

        return {"packages": all_packages}

    def constrain_by_build_number(self, packages):
        """For a given packages dictionary ensure that only the top build number for a given build_string is kept

        Packages without a build number (such as the blas mutex package are unaffected)

            k: artifact_name, v: package information dictionary

        For example

        0.23.0-py27_0, 0.23.0-py27_1, 0.23.0-py36_0
        ->
        0.23.0-py27_1, 0.23.0-py36_0

        """
        keep_packages = []
        packages_by_version = defaultdict(
            lambda: SortedList(key=lambda o: -o[1].get("build_number", 0))
        )
        for k, v in packages.items():
            build_string: str = v.get("build", "")
            build_string, _, build_number = build_string.rpartition("_")

            if not build_number.isnumeric():
                keep_packages.append((k, v))
            else:
                packages_by_version[(v["version"], build_string)].add((k, v))

        for version, ordered_builds in packages_by_version.items():
            keep_packages.append(ordered_builds[0])

        packages = dict(keep_packages)
        return packages

    def constrain_by_blacklist(self, packages, blacklist_name):
        effective_blacklist = set()
        for channel in self.raw.component_channels:
            effective_blacklist.update(
                get_blacklist(blacklist_name, channel, self.arch)
            )
        if len(effective_blacklist):
            return {k: v for k, v in packages.items() if k not in effective_blacklist}
        else:
            return packages

    def untrack_features(self, packages: dict) -> dict:
        """TODO: This function edits the package information dictionary so that packages that are tracked are
        instead replaced by the appropriate dependencies.

        """
        feature_map = {
            "blas_openblas": "blas * openblas",
            "blas_mkl": "blas * mkl",
            "blas_nomkl": "blas * nomkl",
            "vc9": "vs2008_runtime",
            "vc10": "vs2010_runtime",
            "vc14": "vs2015_runtime",
        }

        for k, v in packages.items():
            features = v.get("features", "").split(" ")
            kept_features = []
            for feature in features:
                if feature in feature_map:
                    v["depends"].append(feature_map[feature])
                else:
                    kept_features.append(feature)
            kept_features = " ".join(kept_features)
            if kept_features:
                v["features"] = kept_features
            else:
                v.pop("features", None)

            # For feature packages get rid of mapped things
            track_feature = v.get("track_features")
            if track_feature in feature_map:
                del v["track_features"]

        return packages

    @cachedmethod(operator.attrgetter("cache"))
    def repodata_json(self) -> str:
        out_string = json.dumps(self.repodata_json_dict())
        return out_string

    @cachedmethod(operator.attrgetter("cache"))
    def repodata_json_bzip(self) -> bytes:
        import bz2

        out_bytes = bz2.compress(self.repodata_json().encode("utf8"), compresslevel=1)
        return out_bytes


def get_artifact_graph(
    channel: typing.List[str], arch: str, constraints
) -> ArtifactGraph:
    if isinstance(constraints, str):
        constraints = [constraints]
    print(constraints)

    key = (tuple(channel), arch, tuple(sorted(constraints)))
    if key not in ArtifactGraph._cache:
        ArtifactGraph._cache[key] = ArtifactGraph(channel, arch, constraints)
    return ArtifactGraph._cache[key]
