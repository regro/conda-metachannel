FROM continuumio/miniconda

ADD environment.yml .
RUN conda env create --copy -p /opt/env

ENV PATH="/opt/env/bin:$PATH"

EXPOSE 20124

RUN mnkdir /work
ADD . /work
WORKDIR /work

ENTRYPOINT ["python", "app.py"]
