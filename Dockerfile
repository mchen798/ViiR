FROM mambaorg/micromamba:latest
WORKDIR /opt/viir
COPY ViiR.yml ./ViiR.yml
RUN micromamba create -y -n viir -f ViiR.yml && \
    micromamba run -n viir pip install flask && \
    micromamba run -n viir pip install .

# install BLAST without conda to avoid conflicts
RUN wget -q https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/ncbi-blast-*-x64-linux.tar.gz -O /tmp/blast.tar.gz \
    && tar -xzf /tmp/blast.tar.gz --strip-components=1 -C /usr/local \
    && rm /tmp/blast.tar.gz
COPY . .
EXPOSE 8080
ENTRYPOINT ["micromamba", "run", "-n", "viir", "python", "-m", "app.app"]
