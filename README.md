# conda-metachannel

This is a small little web application to behave like a conda channel but 
with constraints.  

By doing this you can add a small conda-forge channel that has a limited number of edges

```
<HOSTNAME>/conda-forge/pandas,ipython,scikit-learn
```

This is a channel that contains pandas, ipython and scikit-learn (and all of their dependencies),
and nothing else.



## Advanced features

### `--max-build-no`

Adding this to the constraint clause will filter out outdated builds from the graph.
This is typically what most users actually want to run.

eg

```bash
$ conda search --override-channels \
      -c http://<HOST>/conda-forge/python, 'python=3.6.1'

python                    3.6.1               0  conda-forge/python
python                    3.6.1               1  conda-forge/python
python                    3.6.1               2  conda-forge/python
python                    3.6.1               3  conda-forge/python

$ conda search --override-channels \
      -c http://<HOST>/conda-forge/python,--max-build-no 'python=3.6.1'

python                    3.6.1               3  conda-forge/python,--max-build-no
```
