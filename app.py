import argparse

from quart import Quart as Flask, redirect
from graph import get_artifact_graph



app = Flask(__name__)
arch = ['linux-64', 'noarch', 'osx-64']


CHANNEL_MAP = {
    'conda-forge': 'https://conda-static.anaconda.org/conda-forge',
}
INDEX_STATIC = {

}


async def repodata_json(channel, constraints, arch):
    print("ARCH")
    constraints = constraints.split(',')
    ag = get_artifact_graph(channel, arch, constraints)
    return ag.repodata_json()


async def repodata_json_bz2(channel, constraints, arch):
    print("REPODATA")

    constraints = constraints.split(',')
    ag = get_artifact_graph(channel, arch, constraints)
    return ag.repodata_json_bzip()


@app.route('/<channel>/<constraints>/<arch>/<artifact>')
async def artifact(channel, constraints, arch, artifact):
    """
    Example:

          /conda-forge/pandas,ipython,scikitlearn/linux-64/artifact.

    """
    print("ARTIFACT")
    if artifact == 'repodata.json':
        return await repodata_json(channel, constraints, arch)
    elif artifact == 'repodata.json.bz2':
        return await repodata_json_bz2(channel, constraints, arch)
    else:
        true_url = f'{CHANNEL_MAP[channel]}/{arch}/{artifact}'
        return redirect(true_url)


if __name__ == '__main__':
    parser = argparse.ArgumentParser("conda-metachannel")
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=20124, type=int)
    parser.add_argument('--reload', action='store_true')
    args = parser.parse_args()

    app.run(host=args.host, port=args.port, use_reloader=args.reload)
