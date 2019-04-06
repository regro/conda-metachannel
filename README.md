# conda-metachannel

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)

This is a small little web application to behave like a conda channel but 
with user-specified constraints.  

By doing this you can add a small conda channel that has a limited number of packages.

There is a hosted version of metachannel provided at https://metachannel.conda-forge.org

```
https://metachannel.conda-forge.org/conda-forge/pandas,ipython,scikit-learn
```

This is a channel that contains pandas, ipython and scikit-learn (and all of their dependencies),
and nothing else.

## Recommended usage with conda-forge

Presently metachannel is best used when creating *new* environments.  For example

```bash
conda create --override-channels \
      -c https://metachannel.conda-forge.org/defaults,conda-forge/pandas \
      'pandas>=0.24' 
```

This will function similarly to `strict` channel priority in conda, except it will fuse the 
channels remotely and constrain the list of packages to be those that pandas requires to
be installed.

## Advanced features

### `--max-build-no`

Adding this to the constraint clause will filter out outdated builds from the graph.
This is typically what most users actually want to run.

e.g.

```bash
$ conda search --override-channels \
      -c https://metachannel.conda-forge.org/conda-forge/python \
      'python=3.6.1'

python                    3.6.1               0  conda-forge/python
python                    3.6.1               1  conda-forge/python
python                    3.6.1               2  conda-forge/python
python                    3.6.1               3  conda-forge/python

$ conda search --override-channels \
      -c http://<HOSTNAME>/conda-forge/python,--max-build-no 'python=3.6.1'

python                    3.6.1               3  conda-forge/python,--max-build-no
```

### channel fusing

You can fuse two or more channels together.  

```
https://metachannel.conda-forge.org/<CHANNELA>,<CHANNELB>/<CONSTRAINTS>
```

This will function like a composite of these two channels.  Packages that exist in channel `B` will
supercede those in channel `A` for *ALL* versions (just like strict channel priority).  

Channels that contain non-urlsafe characters need to be url-escaped

e.g.

```bash
$ conda search --override-channels -c https://metachannel.conda-forge.org/conda-forge,conda-forge%2Flabel%2Fgcc7/--max-build-no 'pandas'

pandas    0.23.4 py27h1702cab_1000  conda-forge,conda-forge%2Flabel%2Fgcc7/--max-build-no
pandas    0.23.4 py36h1702cab_1000  conda-forge,conda-forge%2Flabel%2Fgcc7/--max-build-no
pandas    0.23.4 py37h1702cab_1000  conda-forge,conda-forge%2Flabel%2Fgcc7/--max-build-no
```

### blacklists

conda-metachannel has the ability to apply package blacklists.  These need to be present as 
``blacklists/<channel>/<name>.yml`` 

```
$ conda search --override-channels -c https://metachannel.conda-forge.org/conda-forge/--blacklist=abi python
```

The default blacklist that ships with conda-metachannel is one that removes all potential abi
incompatible packages resulting from the compiler switchover from conda-forge.
