# 基底：Micromamba，方便管理 Conda 依赖
# FROM mambaorg/micromamba:1.5.8
FROM ubuntu:24.04

# 固定强制 IPv4；可用 ARG 开关控制（默认启用）
ARG APT_FORCE_IPV4=true
RUN if [ "$APT_FORCE_IPV4" = "true" ]; then \
      echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4; \
      echo 'Acquire::Retries "5";'      > /etc/apt/apt.conf.d/99retries; \
      echo 'Acquire::http::Timeout "30"; Acquire::https::Timeout "30";' > /etc/apt/apt.conf.d/99timeout; \
    fi

ARG UID=1000
ARG GID=1000

RUN groupadd -g ${GID} appuser && \
    useradd -m -u ${UID} -g ${GID} appuser

USER appuser

# 避免 timezone/apt 交互
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC \
    MAMBA_ROOT_PREFIX=/opt/micromamba \
    MAMBA_EXE=/usr/local/bin/micromamba \
    PATH=/opt/micromamba/bin:$PATH

# ------------ 基础工具 & BLAST（非conda，避免冲突） ----------------
# For Ubuntu 24.04 image, the default user is root.
# USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash coreutils findutils sed grep curl wget ca-certificates \
        python3 python3-pip \
        build-essential pkg-config \
        git pigz unzip tar jq procps libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 3) 安装 micromamba（官方推荐自举方式）
RUN curl -L https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj -C /usr/local/bin/ bin/micromamba --strip-components=1


# 4) 预置 conda 配置：严格优先级 + bioconda
RUN mkdir -p /root && printf '%s\n' \
  'channels:' \
  '  - conda-forge' \
  '  - bioconda' \
  '  - defaults' \
  'channel_priority: strict' \
  > /root/.condarc

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# install BLAST without conda to avoid conflicts
# 固定版本（可更新）access date 2025/10/09 lastest version:
# https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/ncbi-blast-2.17.0+-x64-linux.tar.gz
RUN set -eux pipefail \
    && mkdir -p /opt/ncbi/blast+ \
    && curl -fsSL --retry 5 --retry-delay 5 --connect-timeout 15 \
        -O https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/2.17.0/ncbi-blast-2.17.0+-x64-linux.tar.gz \
    && tar -xzf ncbi-blast-2.17.0+-x64-linux.tar.gz -C /opt/ncbi/blast+ --strip-components=1 \
    && rm ncbi-blast-2.17.0+-x64-linux.tar.gz

ENV PATH="/opt/ncbi/blast+/bin:${PATH}"


# ------------ 工作目录 & 环境缓存 ----------------
WORKDIR /opt/viir
# 提前 COPY 环境文件，最大化缓存利用
COPY env-ViiR.yml /tmp/ViiR.yml


# Micromamba 层：创建环境（用 BuildKit cache 加速重建）
# 利用 BuildKit 缓存 conda 包，加速二次构建
RUN --mount=type=cache,target=/opt/conda/pkgs \
    micromamba create -y -n viir -f /tmp/ViiR.yml && \
    micromamba clean -a -y

# 激活路径（供 ENTRYPOINT/后续 run 使用）
SHELL ["/bin/bash", "-lc"]
ENV MAMBA_DOCKERFILE_ACTIVATE=1
# 进入 viir 环境
# RUN micromamba activate viir


# ------------ Python 依赖（Web） ----------------
# Flask / Gunicorn 若已在 ViiR.yml 就不用这一步；若不确定，就稳妥再装一次
# RUN pip install --no-cache-dir --upgrade pip && \
#     pip install --no-cache-dir flask gunicorn
# ---- 追加 FastAPI 最小层----
# 1) 安装后端依赖
COPY api/requirements.txt /api/requirements.txt
# RUN pip3 install --no-cache-dir -r /api/requirements.txt
RUN micromamba install -y -n viir -c conda-forge pip
RUN --mount=type=cache,target=/root/.cache/pip \
    micromamba run -n viir python -m pip install --no-cache-dir -r /api/requirements.txt
ENV PATH=/opt/micromamba/envs/viir/bin:$PATH

# 2) 拷贝后端代码
COPY api /api

# 如果 Flask 不在 conda 里，就用 pip（带缓存）
# RUN --mount=type=cache,target=/root/.cache/pip \
#     micromamba run -n viir pip install --upgrade pip flask gunicorn


# ------------ 拷贝代码（分层：先小文件，后大/常改） ------------
# 运行器 & 资源（与脚本相对独立，更新频次低 → 缓存友好）
# ---- 资源统一到 /opt/viir/resources ----
RUN mkdir -p /opt/viir/resources
COPY utils/                        /opt/viir/resources/utils/
COPY hmm_models/                   /opt/viir/resources/hmm_models/
COPY Default_db/                   /opt/viir/resources/ViiR_DB/
COPY example/                   /opt/viir/resources/example/
COPY Pfam_IDs_list.txt     /opt/viir/resources/Pfam_IDs_list.txt
COPY adapters.fasta        /opt/viir/resources/adapters.fasta

# 拷入 bash 运行脚本（已验证可用）
# COPY ./run_viir_QIU_v4.sh /usr/local/bin/viir
COPY ./run_viir_Q.sh /usr/local/bin/viir
RUN chmod +x /usr/local/bin/viir


# Web 层（改动频繁，放后面以减少重建成本）
# Flask 应用（app/ 包含 app.app:app）
COPY app/ /opt/viir/app/
# # 如果有简单静态页或模板（可选）
# COPY webapp/ /opt/viir/webapp/

# ------------ 运行用户 & 数据目录 ----------------
# ---- 运行期默认变量（可被 -e 覆盖）----
ENV VIIR_RESOURCES=/opt/viir/resources \
    VIIR_THREADS_DEFAULT=16 \
    _JAVA_OPTIONS="-Xmx12g"
    # 考虑动态数据库（比如下载NCBI数据），它又有用
    # VIIR_DB_CACHE=/workspace/.viir_db_cache \


# ------------ 健康检查（可选） ----------------
# 需要 app 有 /healthz 路由；暂时注释，接入后放开
# HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
#   CMD curl -fsS http://localhost:8080/healthz || exit 1

# ------------ 启动项 ----------------
# 第一版先实验关于ViiR的运行
# ENTRYPOINT ["/bin/bash"]
# ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]


# 3) 暴露 API 端口（后端 8000）
EXPOSE 8080
# gunicorn 启 Flask: app.app:app
# ENTRYPOINT ["bash","-lc","micromamba run -n viir gunicorn -w 2 -k gthread --threads 8 --timeout 0 -b 0.0.0.0:8080 app.app:app"]
CMD ["micromamba", "run", "-n", "viir", "uvicorn", "main:app","--app-dir","/workspace/api", "--host", "0.0.0.0", "--port", "8000"]
# CMD ["micromamba", "run", "-n", "viir", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# 默认命令改成在 viir 环境里启动 bash
# CMD ["micromamba","activate","viir"]
