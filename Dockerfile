FROM mambaorg/micromamba:latest
WORKDIR /opt/viir
COPY ViiR.yml ./ViiR.yml
RUN micromamba create -y -n viir -f ViiR.yml && \
    micromamba run -n viir pip install flask && \
    micromamba run -n viir pip install .
COPY . .
EXPOSE 8080
ENTRYPOINT ["micromamba", "run", "-n", "viir", "python", "-m", "app.app"]
