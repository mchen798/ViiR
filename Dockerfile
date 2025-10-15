# FROM mambaorg/micromamba:latest
# 基底：Micromamba，方便管理 Conda 依赖
FROM mambaorg/micromamba:1.5.8

# 避免 tz/apt 交互
ENV DEBIAN_FRONTEND=noninteractive

# ------------ 基础工具 & BLAST（非conda，避免冲突） ----------------
USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
      wget curl ca-certificates tar jq procps pigz unzip coreutils libgomp1 git \
    && rm -rf /var/lib/apt/lists/*

# install BLAST without conda to avoid conflicts
# 固定版本（可更新）access date 2025/10/09 lastest version:
# https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/ncbi-blast-2.17.0+-x64-linux.tar.gz
RUN set -euxo pipefail \
    && mkdir -p /opt/ncbi/blast+ \
    && curl -fsSL --retry 5 --retry-delay 5 --connect-timeout 15 \
        -O https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/2.17.0/ncbi-blast-2.17.0+-x64-linux.tar.gz \
    && tar -xzf ncbi-blast-2.17.0+-x64-linux.tar.gz -C /opt/ncbi/blast+ --strip-components=1 \
    && rm ncbi-blast-2.17.0+-x64-linux.tar.gz


# RUN wget -q https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/ncbi-blast-*-x64-linux.tar.gz -O /tmp/blast.tar.gz \
#     && tar -xzf /tmp/blast.tar.gz --strip-components=1 -C /opt/ncbi/blast+ \
#     && rm /tmp/blast.tar.gz
ENV PATH="/opt/ncbi/blast+/bin:${PATH}"


# ------------ 工作目录 & 环境缓存 ----------------
WORKDIR /opt/viir
# 提前 COPY 环境文件，最大化缓存利用
COPY ViiR.yml /tmp/ViiR.yml


# Micromamba 层：创建环境（用 BuildKit cache 加速重建）
# 利用 BuildKit 缓存 conda 包，加速二次构建
RUN --mount=type=cache,target=/opt/conda/pkgs \
    micromamba create -y -n viir -f /tmp/ViiR.yml && \
    micromamba clean -a -y

# 激活路径（供 ENTRYPOINT/后续 run 使用）
SHELL ["/bin/bash", "-lc"]
ENV MAMBA_DOCKERFILE_ACTIVATE=1
# 进入 viir 环境
RUN micromamba activate viir


# ------------ Python 依赖（Web） ----------------
# Flask / Gunicorn 若已在 ViiR.yml 就不用这一步；若不确定，就稳妥再装一次
# RUN pip install --no-cache-dir --upgrade pip && \
#     pip install --no-cache-dir flask gunicorn

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
ENTRYPOINT ["/bin/bash"]
# ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# EXPOSE 8080
# gunicorn 启 Flask: app.app:app
# ENTRYPOINT ["bash","-lc","micromamba run -n viir gunicorn -w 2 -k gthread --threads 8 --timeout 0 -b 0.0.0.0:8080 app.app:app"]


# 默认命令改成在 viir 环境里启动 bash
# CMD ["micromamba","activate","viir"]
