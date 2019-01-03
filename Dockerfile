FROM continuumio/miniconda

ADD environment.yml .
RUN conda env create -p /opt/env --file environment.yml

ENV PATH="/opt/env/bin:$PATH"

EXPOSE 20124

RUN mkdir /work
ADD . /work
WORKDIR /work

ENTRYPOINT ["python", "app.py"]
