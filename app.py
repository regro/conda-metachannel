import asyncio
import argparse
import os
import subprocess
import logging

from quart import Quart as Flask, redirect
from pandas.io import json
from graph import get_artifact_graph, ArtifactGraph, get_repo_data


logger = logging.getLogger(__name__)
app = Flask(__name__)
arch = ['linux-64', 'noarch', 'osx-64']

VERSION = "0.0.4"
CHANNEL_MAP = {
    'conda-forge': 'https://conda-static.anaconda.org/conda-forge',
}
INDEX_STATIC = {

}

CACHED_CHANNELS = [
    ('conda-forge', 'noarch'),
    ('conda-forge', 'osx-64'),
    ('conda-forge', 'linux-64'),
    ('conda-forge', 'win-64'),
    ('conda-forge/label/gcc7', 'osx-64'),
    ('conda-forge/label/gcc7', 'linux-64'),
]


def fetch_artifact_graph(channel, constraints, arch) -> ArtifactGraph:
    constraints = constraints.split(',')
    channel = channel.split(',')
    ag = get_artifact_graph(channel, arch, constraints)
    return ag


def repodata_json(channel, constraints, arch):
    ag = fetch_artifact_graph(channel, constraints, arch)
    return ag.repodata_json()


def repodata_json_bz2(channel, constraints, arch):
    ag = fetch_artifact_graph(channel, constraints, arch)
    return ag.repodata_json_bzip()


async def warm_cache(loop, channel, arch):
    while True:
        await loop.run_in_executor(None, get_repo_data, channel, arch)
        await asyncio.sleep(30)


@app.route('/<path:channel>/<constraints>/<arch>/<artifact>')
async def artifact(channel, constraints, arch, artifact):
    """
    Example:

          /conda-forge/pandas,ipython,scikitlearn/linux-64/artifact.

    """
    print("ARTIFACT")
    print(locals())
    loop = asyncio.get_event_loop()
    if artifact == 'repodata.json':
        return await loop.run_in_executor(None, repodata_json, channel, constraints, arch)
    elif artifact == 'repodata.json.bz2':
        return await loop.run_in_executor(None, repodata_json_bz2, channel, constraints, arch)
    else:
        ag = await loop.run_in_executor(None, fetch_artifact_graph, channel, constraints, arch)
        # Due to https://github.com/conda/conda/blob/master/conda/core/subdir_data.py#L358 we can't just use the stored
        # urls as part of the repodata, and have to retrieve the urls instead in order to detach fused channels
        true_url = ag.repodata_json_dict()['packages'][artifact]['url']
        # true_url = f'{CHANNEL_MAP[channel]}/{arch}/{artifact}'
        return redirect(true_url)


@app.route('/version')
def version():
    """Returns version information

    Example:

        /version

    """
    return json.dumps({"version": VERSION})


@app.route('/')
def root():
    if os.path.exists('README.md'):
        return open('README.md').read()
    else:
        return 'Welcome top conda-metachannel.  See https://github.com/regro/conda-metachannel for details'


def in_container():
    # type: () -> bool
    """ Determines if we're running in an lxc/docker container.

    Shamelessly acquired from https://stackoverflow.com/a/46436970
    """
    out = subprocess.check_output('cat /proc/1/sched', shell=True)
    out = out.decode('utf-8').lower()
    checks = [
        'docker' in out,
        '/lxc/' in out,
        out.split()[0] not in ('systemd', 'init',),
        os.path.exists('/.dockerenv'),
        os.path.exists('/.dockerinit'),
        os.getenv('container', None) is not None
    ]
    return any(checks)


if __name__ == '__main__':
    parser = argparse.ArgumentParser("conda-metachannel")
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=20124, type=int)
    parser.add_argument('--reload', action='store_true')
    args = parser.parse_args()

    try:
        if in_container() and args.host == '127.0.0.1':
            logger.warning("Detected that we are running inside docker.  Overriding host")
            args.host = '0.0.0.0'
    except:
        pass

    loop = asyncio.get_event_loop()
    # Start the background worker to run through all the channels
    for channel, arch in CACHED_CHANNELS:
        loop.create_task(warm_cache(loop, [channel], arch))

    app.run(host=args.host, port=args.port, use_reloader=args.reload, loop=loop)
