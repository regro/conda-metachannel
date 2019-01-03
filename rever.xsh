import os

from rever.activity import activity


$GITHUB_ORG = 'regro'
$PROJECT = $GITHUB_REPO = 'conda-metachannel'
$ACTIVITIES = [
    'version_bump',
    'changelog',
    'tag',
    'push_tag',
    'ghrelease',
    # uncomment the following lines if we ever install this thing
    # 'pypi',
    # 'conda_forge',
    'docker_build',
    'docker_push',
    'deploy_to_gcloud',
]

$VERSION_BUMP_PATTERNS = [
    ('app.py', 'VERSION\s*=.*', 'VERSION = "$VERSION"'),
    ]
$CHANGELOG_FILENAME = 'CHANGELOG.rst'
$CHANGELOG_TEMPLATE = 'TEMPLATE.rst'
$PUSH_TAG_REMOTE = 'git@github.com:regro/conda-metachannel.git'

# docker config
$DOCKERFILE = 'Dockerfile'
$DOCKERFILE_TAGS = ('condaforge/conda-metachannel:$VERSION',
                    'condaforge/conda-metachannel:latest')

#
# Google Cloud
#
$GCLOUD_PROJECT_ID = 'conda-metachannel'
$GCLOUD_ZONE = 'us-central1-a'
$GCLOUD_CLUSTER = 'conda-metachannel-cluster01'


def _ensure_default_credentials():
    credfile = os.path.join($XDG_CONFIG_HOME, 'gcloud',
                            'application_default_credentials.json')
    if os.path.isfile(credfile):
        print_color('{YELLOW}Found ' + credfile + ' ...{NO_COLOR}')
    else:
        ![gcloud auth application-default login]
    $CLOUDSDK_CONTAINER_USE_APPLICATION_DEFAULT_CREDENTIALS = 'true'
    return credfile


def _ensure_account(n=0):
    if n > 3:
        raise RuntimeError('failed to log in to gcloud')
    account = $(gcloud config get-value account).strip()
    if account == '(unset)' or '@' not in account:
        n += 1
        print(f'gcloud account is {account}, login attempt {n}/3:')
        ![gcloud auth login]
        account = _ensure_account(n+1)
    return account


@activity
def deploy_to_gcloud():
    """Deploys the build docker containter to the google cloud"""
    # make sure we are logged in
    _ensure_default_credentials()
    account = _ensure_account()
    # get cluster credentials
    ![gcloud container clusters get-credentials --account @(account) \
      --zone=$GCLOUD_ZONE --project=$GCLOUD_PROJECT_ID $GCLOUD_CLUSTER]
    # set new image
    ![kubectl set image deployment/conda-metachannel-app conda-metachannel-app=docker.io/condaforge/conda-metachannel:$VERSION]


# Ensure that we have the proper software to perform release
def _ensure_packages():
    clis = [
        ('gcloud', 'google-cloud-sdk'),
        ('kubectl', 'kubernetes'),
        ]
    bad = []
    for cli, package in clis:
        if not !(which @(cli)):
            bad.append((cli, package))
    if bad:
        s = ''
        for cli, package in bad:
            s += f'Could not find {cli}! Try installing:\n  $ conda install {package}'
        print(s)
        raise RuntimeError(s)


_ensure_packages()
