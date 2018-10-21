# conda-metachannel

This is a small little web application to behave like a conda channel but 
with constraints.  

By doing this you can add a small conda-forge channel that has a limited number of edges

```
<HOSTNAME>/conda-forge/pandas,ipython,scikit-learn
```

This is a channel that contains pandas, ipython and scikit-learn (and all of their dependencies),
and nothing else.

