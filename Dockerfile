FROM continuumio/miniconda

ADD environment.yml .
RUN conda env create -p /opt/env --file environment.yml

ENV PATH="/opt/env/bin:$PATH"
ENV PYTHONUNBUFFERED="1"

EXPOSE 20124

RUN mkdir /work
ADD . /work
WORKDIR /work

ENTRYPOINT ["/opt/env/bin/python", "app.py", "--host", "0.0.0.0", "--port", "20214"]
