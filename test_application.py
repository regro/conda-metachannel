"""CLI based test suite!"""


import json
import random
import subprocess
import time

import pytest


@pytest.fixture(scope="module")
def app_fixture():
    port = random.randint(30000, 40000)
    process = subprocess.Popen(["python", "app.py", "--port", str(port)])
    print("Warming process")
    time.sleep(1)

    yield f"http://127.0.0.1:{port}"
    process.terminate()


def test_subset(app_fixture):
    """Simple test that checks if we constrain our channel can we no longer find a given package

    """
    conda_search_command = [
        "conda",
        "search",
        "--override-channels",
        "-c",
        f"{app_fixture}/conda-forge/python",
        "--json",
    ]
    output = subprocess.check_output(
        encoding="utf8", args=conda_search_command + ["zlib"]
    )

    output = json.loads(output)
    assert "zlib" in output
    assert len(output["zlib"]) > 0

    process = subprocess.Popen(
        encoding="utf8",
        args=conda_search_command + ["flask"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = process.communicate()
    assert process.returncode != 0
    output = json.loads(stdout)
    assert "error" in output
    assert output["exception_name"] == "PackagesNotFoundError"


def test_blacklist(app_fixture):
    """Simple test that checks if we constrain our channel can we no longer find a given package

    """
    channel = f"{app_fixture}/conda-forge/python"
    channel_blacklist = f"{app_fixture}/conda-forge/python,--blacklist=abi"

    def conda_search_command(channel, package):
        return [
            "conda",
            "search",
            "--override-channels",
            "-c",
            channel,
            "--json",
            package,
        ]

    output = subprocess.check_output(
        encoding="utf8", args=conda_search_command(channel, "python")
    )
    output = json.loads(output)
    assert len(output["python"]) > 0

    stdout = subprocess.check_output(
        encoding="utf8", args=conda_search_command(channel_blacklist, "python")
    )
    output2 = json.loads(stdout)

    assert len(output2["python"]) < len(output["python"])


def test_current_repodata(app_fixture):
    channel = f"{app_fixture}/conda-forge/python"
    import requests

    full_repodata = requests.get(f"{channel}/linux-64/repodata.json").json()
    current_repodata = requests.get(f"{channel}/linux-64/current_repodata.json").json()

    assert len(current_repodata['packages']) < len(full_repodata['packages'])


def test_download_artifact(app_fixture):
    package = 'conda-forge-pinning'
    channel = f"{app_fixture}/conda-forge/{package}"
    import requests

    current_repodata = requests.get(f"{channel}/noarch/current_repodata.json").json()
    print(current_repodata)

    for k, v in sorted(current_repodata['packages'].items()):
        if v['name'] == package:
            filename = k

            resp = requests.get(f"{channel}/noarch/{filename}", allow_redirects=False)
            assert resp.ok
            assert resp.status_code // 100 == 3
            assert resp.headers["Location"] == f"https://conda.anaconda.org/conda-forge/noarch/{filename}"
            break
    else:
        raise LookupError("No file download attempted")