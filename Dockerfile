FROM mambaorg/micromamba:latest
WORKDIR /opt/viir

# COPY ViiR.yml ./ViiR.yml
# 仅拷环境文件，最大化缓存命中
COPY ../ViiR.yml /tmp/ViiR.yml
COPY ../run_ViiR.bash ~/run_ViiR.bash


# 利用 BuildKit 缓存 conda 包，加速二次构建
RUN --mount=type=cache,target=/opt/conda/pkgs \
    micromamba create -y -n viir -f /tmp/ViiR.yml && \
    micromamba clean -a -y


# install BLAST without conda to avoid conflicts
RUN wget -q https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/ncbi-blast-*-x64-linux.tar.gz -O /tmp/blast.tar.gz \
    && tar -xzf /tmp/blast.tar.gz --strip-components=1 -C /usr/local \
    && rm /tmp/blast.tar.gz


    # 拷入 bash 与后端代码（先只拷必要的小文件以增进缓存）
COPY ../bin/viir.sh /usr/local/bin/viir
RUN chmod +x /usr/local/bin/viir


# 如果 Flask 不在 conda 里，就用 pip（带缓存）
RUN --mount=type=cache,target=/root/.cache/pip \
    micromamba run -n viir pip install --upgrade pip flask gunicorn

# 再拷 Web 代码（改代码不会让上面的昂贵环境层失效）
COPY ../app ./app

EXPOSE 8080
ENTRYPOINT ["micromamba","run","-n","viir","gunicorn","-w","2","-b","0.0.0.0:8080","app.app:app"]
# ENTRYPOINT ["micromamba", "run", "-n", "viir", "python", "-m", "app.app"]
