import asyncio
import argparse
import os
import subprocess
import logging

from quart import Quart as Flask, redirect, abort
from pandas.io import json
from graph import get_artifact_graph, ArtifactGraph, get_repo_data, REPODATA_FILE, REPODATA_FILE_CURRENT


logger = logging.getLogger(__name__)
app = Flask(__name__)
arch = ["linux-64", "noarch", "osx-64"]

VERSION = "0.1.0"
CHANNEL_MAP = {"conda-forge": "https://conda-static.anaconda.org/conda-forge"}
INDEX_STATIC = {}

CACHED_CHANNELS = [
    ("conda-forge", "noarch"),
    ("conda-forge", "osx-64"),
    ("conda-forge", "linux-64"),
    ("conda-forge", "win-64"),
    ("defaults", 'noarch'),
    ("defaults", 'osx-64'),
    ("defaults", 'linux-64'),
    ("defaults", 'win-64'),
]


def fetch_artifact_graph(channel, constraints, arch, repodata_file) -> ArtifactGraph:
    constraints = constraints.split(",")
    channel = channel.split(",")
    ag = get_artifact_graph(channel=channel, arch=arch, constraints=constraints, base_url=base_url, repodata_file=repodata_file)
    return ag


def current_repodata_json(channel, constraints, arch):
    ag = fetch_artifact_graph(channel, constraints, arch, REPODATA_FILE_CURRENT)
    res = ag.repodata_json()
    if res == 'null':
        return None
    return res


def repodata_json(channel, constraints, arch):
    ag = fetch_artifact_graph(channel, constraints, arch, REPODATA_FILE)
    return ag.repodata_json()


def repodata_json_bz2(channel, constraints, arch):
    ag = fetch_artifact_graph(channel, constraints, arch, REPODATA_FILE)
    return ag.repodata_json_bzip()


async def warm_cache(loop, channel, arch, base_url):
    while True:
        await loop.run_in_executor(None, get_repo_data, channel, arch, REPODATA_FILE_CURRENT, base_url)
        await loop.run_in_executor(None, get_repo_data, channel, arch, REPODATA_FILE, base_url)
        await asyncio.sleep(30)


@app.route("/<path:channel>/<constraints>/<arch>/<artifact>")
async def artifact(channel, constraints, arch, artifact):
    """
    Example:
          /conda-forge/pandas,ipython,scikitlearn/linux-64/artifact-5.0.0_1000.tar.bz2

    """
    loop = asyncio.get_event_loop()
    logger.info(locals())
    if artifact == "repodata.json":
        return await loop.run_in_executor(
            None, repodata_json, channel, constraints, arch
        )
    elif artifact == "repodata.json.bz2":
        return await loop.run_in_executor(
            None, repodata_json_bz2, channel, constraints, arch
        )
    elif artifact == 'current_repodata.json':
        # current repodata doesn't exist for everything, so we need to be a tad more careful
        json = await loop.run_in_executor(
            None, current_repodata_json, channel, constraints, arch
        )
        if json is None:
            abort(404)
        else:
            return json
    elif artifact.endswith('.json'):
        # if we ask for another magic json file that we don't know how to handle, just fake out
        abort(404)
    else:
        # TODO: Do some light processing on channels.  If we are not fusing channels we can just
        #       construct the redirect url directly without needing to do any work.

        # TODO fetch these things in parallel.  current *should* be cheaper so do both, 
        #      if success in any one of them cancel the other.  If both fail, die
        ag = await loop.run_in_executor(
            None, fetch_artifact_graph, channel, constraints, arch, REPODATA_FILE
        )
        # ag_current = await loop.run_in_executor(
        #     None, fetch_artifact_graph, channel, constraints, arch, REPODATA_FILE_CURRENT
        # )

        # Due to https://github.com/conda/conda/blob/master/conda/core/subdir_data.py#L358 we can't just use the stored
        # urls as part of the repodata, and have to retrieve the urls instead in order to detach fused channels
        true_url = ag.repodata_json_dict()["packages"][artifact]["url"]
        # true_url = f'{CHANNEL_MAP[channel]}/{arch}/{artifact}'
        return redirect(true_url)


@app.route("/version")
def version():
    """Returns version information

    Example:

        /version

    """
    return json.dumps({"version": VERSION})


@app.route("/blacklists")
def blacklists():
    import glob
    import pathlib

    base = pathlib.Path("blacklists")
    return json.dumps(list(base.glob("*/*.yml")))


@app.route("/")
def root():
    if os.path.exists("README.md"):
        return open("README.md").read()
    else:
        return "Welcome top conda-metachannel.  See https://github.com/regro/conda-metachannel for details"


def in_container():
    # type: () -> bool
    """ Determines if we're running in an lxc/docker container.

    Shamelessly acquired from https://stackoverflow.com/a/46436970
    """
    out = subprocess.check_output("cat /proc/1/sched", shell=True)
    out = out.decode("utf-8").lower()
    checks = [
        "docker" in out,
        "/lxc/" in out,
        out.split()[0] not in ("systemd", "init"),
        os.path.exists("/.dockerenv"),
        os.path.exists("/.dockerinit"),
        os.getenv("container", None) is not None,
    ]
    return any(checks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser("conda-metachannel")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=20124, type=int)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--base-url", default="https://conda.anaconda.org/")
    args = parser.parse_args()

    base_url = args.base_url

    try:
        if in_container() and args.host == "127.0.0.1":
            logger.warning(
                "Detected that we are running inside docker.  Overriding host"
            )
            args.host = "0.0.0.0"
    except:
        pass

    loop = asyncio.get_event_loop()
    # Start the background worker to run through all the channels
    for channel, arch in CACHED_CHANNELS:
        loop.create_task(warm_cache(loop, [channel], arch, base_url))

    app.run(host=args.host, port=args.port, use_reloader=args.reload, loop=loop)
