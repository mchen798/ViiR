#!/bin/bash
# set -euo pipefail

# =================== 0. Dependency Check ==========================
# Check whether all required tools are installed before starting pipeline
# 只能检测是否存在，不能自动输出版本号
REQUIRED_TOOLS=(yq trimmomatic Trinity samtools barrnap wget)
for tool in "${REQUIRED_TOOLS[@]}"; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "[ERROR] Required tool '$tool' is not installed or not in PATH." >&2
        exit 1
    fi
done
echo "[INFO] All dependencies are satisfied."




# =================== 1. Parse YAML Parameters =====================
# Read pipeline parameters from a YAML config file
CONFIG_FILE="$1"

if [[ -z "${CONFIG_FILE:-}" ]]; then
  echo "[ERROR] Usage: viir <config.yaml>" >&2
  exit 2
fi

# Check if the config file exists
if [ ! -f "$CONFIG_FILE" ]; then
  echo "[ERROR] Config file not found: $CONFIG_FILE" >&2
  exit 1
fi
CONFIG_FILE="$(realpath -m "$CONFIG_FILE")"
CONFIG_DIR="$(dirname "$CONFIG_FILE")"

# 统一默认根（仅作为兜底；web 路径A下通常是 /workspace）
# WORKSPACE_ROOT="${WORKSPACE:-/workspace}"

# VIIR 默认资源与缓存（可由 docker -e 覆盖）
VIIR_RESOURCES="${VIIR_RESOURCES:-/opt/viir/resources}"
# VIIR_DB_CACHE="${VIIR_DB_CACHE:-$WORKSPACE_ROOT/.viir_db_cache}"

# 小工具：相对路径 -> 绝对路径（相对 config.yaml 所在目录）
resolve_rel_to_config() {
  local p="$1"
  if [[ -z "$p" || "$p" == "." ]]; then
    realpath -m "$CONFIG_DIR"
  elif [[ "$p" = /* ]]; then
    realpath -m "$p"
  else
    realpath -m "$CONFIG_DIR/$p"
  fi
}

# 读取原始值（保留字面量，用于 Default_* 识别）
OUT_DIR_RAW=$(yq '.out' "$CONFIG_FILE" | tr -d '"')

# OUT_DIR=$(cd $(dirname $OUT_DIR); pwd)/$(basename $OUT_DIR)

FASTQ_LIST_RAW=$(yq '."fastq-list"' "$CONFIG_FILE" | tr -d '"')
# FASTQ_LIST=$(cd $(dirname $FASTQ_LIST); pwd)/$(basename $FASTQ_LIST)

N_THREADS=$(yq '.threads' "$CONFIG_FILE")
ADAPTER_RAW=$(yq '.adapter' "$CONFIG_FILE" | tr -d '"')
# ADAPTER_FASTA=$(cd $(dirname $ADAPTER_FASTA); pwd)/$(basename $ADAPTER_FASTA)

PFAM_RAW=$(yq '.pfam' "$CONFIG_FILE" | tr -d '"')
# PFAM_ID_LIST=$(cd $(dirname $PFAM_ID_LIST); pwd)/$(basename $PFAM_ID_LIST)
HMM_DIR_RAW=$(yq '."hmm-folder"' "$CONFIG_FILE" | tr -d '"')

SS_LIB_TYPE=$(yq '."SS-lib-type"' "$CONFIG_FILE" | tr -d '"')
BLASTNDB_RAW=$(yq '.blastndb' "$CONFIG_FILE" | tr -d '"')
# BLASTNDB_FASTA=$(cd $(dirname $BLASTNDB_FASTA); pwd)/$(basename $BLASTNDB_FASTA)
PVALUE=$(yq '.pvalue' "$CONFIG_FILE")
MAX_MEMORY=$(yq '."max-memory"' "$CONFIG_FILE" | tr -d '"')

# 解析输出目录和 fastq 列表（相对 config.yaml）
OUT_DIR="$(resolve_rel_to_config "$OUT_DIR_RAW")"
FASTQ_LIST="$(resolve_rel_to_config "$FASTQ_LIST_RAW")"
# 解析 Adapter / Pfam / HMM：
# 允许三种来源优先级：
#   1) config.yaml 指定具体路径（相对 config.yaml 解析）
#   2) 占位符：Default_adapter / Default_list / 默认 HMM 目录 -> 回落到 VIIR_RESOURCES
#   3) 最后兜底到 VIIR_RESOURCES
case "$ADAPTER_RAW" in
  ""|"Default_adapter") ADAPTER_FASTA="$VIIR_RESOURCES/adapters.fasta" ;;
  *) ADAPTER_FASTA="$(resolve_rel_to_config "$ADAPTER_RAW")" ;;
esac

case "$PFAM_RAW" in
  ""|"Default_list") PFAM_ID_LIST="$VIIR_RESOURCES/Pfam_IDs_list.txt" ;;
  *) PFAM_ID_LIST="$(resolve_rel_to_config "$PFAM_RAW")" ;;
esac

if [[ -z "${HMM_DIR_RAW:-}" || "$HMM_DIR_RAW" == "." ]]; then
  HMM_DIR="$VIIR_RESOURCES/hmm_models"
else
  HMM_DIR="$(resolve_rel_to_config "$HMM_DIR_RAW")"
fi


# BLAST DB：支持 "Default_db" 占位符或用户路径；我们使用“目录或前缀”都可。
# 约定：如果是 Default_db，则使用内置小库（或你自带的目录结构）
case "$BLASTNDB_RAW" in
  ""|"Default_db") BLASTNDB_FASTA="$VIIR_RESOURCES/ViiR_DB" ;;
  *) BLASTNDB_FASTA="$(resolve_rel_to_config "$BLASTNDB_RAW")" ;;
esac

# =================== 2. Logging Setup =============================
# Prepare logging to both console and a log file
mkdir -p "$OUT_DIR"
# mkdir -p "$OUT_DIR" "$VIIR_DB_CACHE"
LOG_FILE="${OUT_DIR}/run_viir.log"
log() { echo "[$(date +'%F %T')] $*" | tee -a "$LOG_FILE"; }

log "[INFO] Pipeline started."
log "[INFO] CONFIG_FILE    = $CONFIG_FILE"
log "[INFO] OUT_DIR        = $OUT_DIR"
log "[INFO] FASTQ_LIST     = $FASTQ_LIST"
log "[INFO] THREADS        = $N_THREADS"
log "[INFO] ADAPTER        = $ADAPTER_FASTA"
log "[INFO] PFAM_LIST      = $PFAM_ID_LIST"
log "[INFO] HMM_DIR        = $HMM_DIR"
log "[INFO] SS_TYPE        = $SS_LIB_TYPE"
log "[INFO] BLASTNDB_FASTA  = $BLASTNDB_FASTA"
log "[INFO] PVALUE         = $PVALUE"
log "[INFO] MAX_MEMORY     = $MAX_MEMORY"
log "[INFO] VIIR_RESOURCES = $VIIR_RESOURCES"
# log "[INFO] VIIR_DB_CACHE  = $VIIR_DB_CACHE"



export TRINITY_CPU=${N_THREADS}
export TRINITY_MAX_MEMORY=${MAX_MEMORY}


# =================== 3. Directory Preparation (Robust Version) ======================
# Define required directories in an array for maintainability and clarity
REQUIRED_DIRS=(
    "$OUT_DIR/00_fastq"
    "$OUT_DIR/10_trinity"
    "$OUT_DIR/20_estimate_abundance"
    "$OUT_DIR/30_count_matrix"
    "$OUT_DIR/40_DEGseq2"
    "$OUT_DIR/50_hmmer"
    "$OUT_DIR/60_fasta"
    "$OUT_DIR/70_barrnap"
    "$OUT_DIR/80_kmer"
    "$OUT_DIR/90_blastn"
)
# Function for robust directory creation with logging and error handling
create_dir() {
    local dir="$1"
    if [ -d "$dir" ]; then
        log "[INFO] Directory already exists: $dir"
    else
        mkdir -p "$dir"
        if [ $? -eq 0 ]; then
            log "[INFO] Created directory: $dir"
        else
            log "[ERROR] Failed to create directory: $dir"
            exit 1
        fi
    fi
    # Optional: check write permission
    if [ ! -w "$dir" ]; then
        log "[ERROR] No write permission for directory: $dir"
        exit 1
    fi
}

# Batch create all required directories
for dir in "${REQUIRED_DIRS[@]}"; do
    create_dir "$dir"
done



# =================== 4. Resource Preparation =======================
# Adapter/DB/Pfam file download with local cache support
BASE_URL="https://raw.githubusercontent.com/mchen798/ViiR/master"
############### Function #########################
function download_if_not_exist() {
    local local_path="$1"
    local url="$2"
    local target_path="$3"

    if [ -f "${local_path}" ]; then
        #config file specific resource 
        cp "${local_path}" "$target_path"
        log "📁 Use local file: ${local_path} → ${target_path}"
       
    # elif [ -f "../${local_path}" ]; then
    # ViiR default resource
    #     cp "../${local_path}" "$target_path"
    #     log "📁 Use ../Local file: ../${local_path} → ${target_path}"
    else
        wget "$url" -O "$target_path" </dev/null
        log "🌐 Download file: $url → $target_path"
    fi
}
#################################################


########### 4. Resource Preparation ############
# --- Prepare Adapter FASTA ---
if [ "$ADAPTER_FASTA" = "Default_adapter" ]; then
    # Download/copy the default adapter if needed
    download_if_not_exist "${VIIR_RESOURCES}/adapters.fasta" \
        "${BASE_URL}/example/adapters.fasta" \
        "${OUT_DIR}/00_fastq/adapter.fasta"
    ADAPTER_FASTA="${OUT_DIR}/00_fastq/adapter.fasta"
    log "[INFO] Adapter file set to $ADAPTER_FASTA"
else
    ADAPTER_FASTA="$(readlink -f "$ADAPTER_FASTA")"
    log "[INFO] User provided adapter file: $ADAPTER_FASTA"
fi

# --- Prepare Pfam ID List ---
if [ "$PFAM_ID_LIST" = "Default_list" ]; then
    download_if_not_exist "${VIIR_RESOURCES}/Pfam_IDs_list.txt" \
        "${BASE_URL}/example/Pfam_IDs_list.txt" \
        "${OUT_DIR}/50_hmmer/Pfam_IDs_list.txt"
    PFAM_ID_LIST="${OUT_DIR}/50_hmmer/Pfam_IDs_list.txt"
    log "[INFO] Pfam ID list file set to $PFAM_ID_LIST"
else
    PFAM_ID_LIST="$(readlink -f "$PFAM_ID_LIST")"
    log "[INFO] User provided Pfam ID list: $PFAM_ID_LIST"
fi

# --- Prepare BLASTN Database FASTA ---
if [ "$BLASTNDB_RAW" = "Default_db" ]; then
    # 这里只是记录变量，实际克隆和解压留给后续主流程步骤
    # BLASTNDB_FASTA="Default_db"
    log "[INFO] Will download/build default BLASTN database in later step."
else
    BLASTNDB_FASTA="$(readlink -f "$BLASTNDB_FASTA")"
    log "[INFO] User provided BLASTN db fasta: $BLASTNDB_FASTA"
fi

log "[INFO] Resource preparation finished."



# ========================== 5. Main Pipeline Functions ============================

# ---- 5.1 FASTQ Preprocessing with Trimmomatic ----
run_trimmomatic() {
    log "[STEP] Running Trimmomatic on FASTQ files..."
    FASTQ_CNT=0
    TRINITY_LEFT=""
    TRINITY_RIGHT=""


    
    local fastq_list_output="${OUT_DIR}/00_fastq/fastq_list.txt"
    > "$fastq_list_output"  # Clear previous file if exists

    while read LINE || [ -n "$LINE" ]; do
        COLS=($LINE)
        SAMPLE_TYPE=${COLS[0]}
        FASTQ1=${COLS[1]}
        FASTQ2=${COLS[2]}
        
        SUBDIR="${OUT_DIR}/00_fastq/${SAMPLE_TYPE}${FASTQ_CNT}"
        PREFIX="${SUBDIR}/${SAMPLE_TYPE}${FASTQ_CNT}"

        create_dir "$SUBDIR"
        (
          # 给 Trimmomatic 这一次设置 JVM 堆和 java.io.tmpdir（命令前缀，非全局）
        #    _JAVA_OPTIONS="-Xms${MAX_MEMORY} -Xmx${MAX_MEMORY} -Djava.io.tmpdir=${TRINITY_TMPDIR}" \
          _JAVA_OPTIONS="-Xms${MAX_MEMORY} -Xmx${MAX_MEMORY}" \
          trimmomatic PE -threads "${N_THREADS}" -phred33 \
              "${FASTQ1}" "${FASTQ2}" \
              "${PREFIX}.1.trimmed.fastq.gz" "${PREFIX}.1.unpaired.trimmed.fastq.gz" \
              "${PREFIX}.2.trimmed.fastq.gz" "${PREFIX}.2.unpaired.trimmed.fastq.gz" \
              ILLUMINACLIP:"${ADAPTER_FASTA}":2:30:10 \
              LEADING:20 TRAILING:20 SLIDINGWINDOW:4:15 MINLEN:75
        )
        # trimmomatic PE -threads ${N_THREADS} -phred33 \
        #     "${FASTQ1}" "${FASTQ2}" \
        #     "${PREFIX}.1.trimmed.fastq.gz" "${PREFIX}.1.unpaired.trimmed.fastq.gz" \
        #     "${PREFIX}.2.trimmed.fastq.gz" "${PREFIX}.2.unpaired.trimmed.fastq.gz" \
        #     ILLUMINACLIP:"${ADAPTER_FASTA}":2:30:10 \
        #     LEADING:20 TRAILING:20 SLIDINGWINDOW:4:15 MINLEN:75

        echo -e "${SAMPLE_TYPE}\t${SAMPLE_TYPE}${FASTQ_CNT}\t${PREFIX}.1.trimmed.fastq.gz\t${PREFIX}.2.trimmed.fastq.gz" >> "$fastq_list_output"

        if [ $FASTQ_CNT -eq 0 ]; then
            TRINITY_LEFT="${PREFIX}.1.trimmed.fastq.gz"
            TRINITY_RIGHT="${PREFIX}.2.trimmed.fastq.gz"
        else
            TRINITY_LEFT="${TRINITY_LEFT},${PREFIX}.1.trimmed.fastq.gz"
            TRINITY_RIGHT="${TRINITY_RIGHT},${PREFIX}.2.trimmed.fastq.gz"
        fi
        FASTQ_CNT=$((FASTQ_CNT+1))
    done < "$FASTQ_LIST"

    # Export these variables for use by downstream functions
    export TRINITY_LEFT TRINITY_RIGHT
    log "[STEP] Trimmomatic preprocessing complete."
}

run_trimmomatic


# ---- 5.2 Trinity de novo Assembly ----
run_trinity() {


    # export _JAVA_OPTIONS="-Xms${MAX_MEMORY} -Xmx${MAX_MEMORY}"

    export TRINITY_CPU="${N_THREADS}"
    export TRINITY_MAX_MEMORY="${MAX_MEMORY}"
    export TRINITY_TMPDIR=/dev/shm/trinity_tmp
    export TMPDIR=/dev/shm/trinity_tmp
    mkdir -p /dev/shm/trinity_tmp

    (
        export OMP_NUM_THREADS=1
        export OPENBLAS_NUM_THREADS=1
        export MKL_NUM_THREADS=1

        log "[STEP] Running Trinity assembly..."
        create_dir "${OUT_DIR}/10_trinity"
        # local trinity_cmd="Trinity --seqType fq --max_memory ${MAX_MEMORY} \
        #     --left ${TRINITY_LEFT} --right ${TRINITY_RIGHT} \
        #     --output ${OUT_DIR}/10_trinity/trinity_assembly \
        #     --CPU ${N_THREADS} --full_cleanup"
    # 用数组避免 eval/转义问题
        local -a tr_cmd=(
            Trinity
            --seqType fq
            --max_memory "${TRINITY_MAX_MEMORY}"
            --left "${TRINITY_LEFT}"
            --right "${TRINITY_RIGHT}"
            --output "${OUT_DIR}/10_trinity/trinity_assembly"
            --CPU "${TRINITY_CPU}"
            --full_cleanup
        )


        # if [ "$SS_LIB_TYPE" != "No" ]; then
        #     trinity_cmd="${trinity_cmd} --SS_lib_type ${SS_LIB_TYPE}"
        # fi
        # eval "$trinity_cmd"
        # log "[STEP] Trinity assembly complete."

        # 只有在 SS_LIB_TYPE 非空 且 不为 "No" 时才追加
        if [[ -n "${SS_LIB_TYPE:-}" && "${SS_LIB_TYPE}" != "No" ]]; then
            tr_cmd+=( --SS_lib_type "${SS_LIB_TYPE}" )
        fi

        log "[INFO] Trinity cmd: ${tr_cmd[*]}"
        _JAVA_OPTIONS="-Xms${TRINITY_MAX_MEMORY} -Xmx${TRINITY_MAX_MEMORY}" \
            "${tr_cmd[@]}"
        local rc=$?
        if (( rc != 0 )); then
            log "[ERROR] Trinity failed (exit $rc)"; exit $rc
        fi
        log "[STEP] Trinity assembly complete."
    )
}

run_trinity



# ---- 5.3 Abundance Estimation ----
run_abundance_estimation() {
    log "[STEP] Estimating transcript abundance..."
    create_dir "${OUT_DIR}/20_estimate_abundance"
    local abundance_dir="${OUT_DIR}/20_estimate_abundance"
    cd "$abundance_dir"
    export TRINITY_CPU="${N_THREADS}"
    # local abundance_cmd="align_and_estimate_abundance.pl --transcripts ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta \
    #     --gene_trans_map ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta.gene_trans_map \
    #     --seqType fq --samples_file ${OUT_DIR}/00_fastq/fastq_list.txt \
    #     --est_method RSEM --aln_method bowtie --coordsort_bam --trinity_mode --prep_reference --thread_count ${N_THREADS}"
    local abundance_cmd="align_and_estimate_abundance.pl --transcripts ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta \
        --gene_trans_map ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta.gene_trans_map \
        --seqType fq --samples_file ${OUT_DIR}/00_fastq/fastq_list.txt \
        --est_method RSEM --aln_method bowtie2 --coordsort_bam --trinity_mode --prep_reference --thread_count ${N_THREADS}"


    if [ "$SS_LIB_TYPE" != "No" ]; then
        abundance_cmd="${abundance_cmd} --SS_lib_type ${SS_LIB_TYPE}"
    fi
    eval "$abundance_cmd"
    log "[STEP] Abundance estimation complete."
}

run_abundance_estimation


# ---- 5.4 Count Matrix and DESeq2 ----
run_degseq2() {
    log "[STEP] Generating count matrix and running DESeq2..."
    create_dir "${OUT_DIR}/30_count_matrix"
    cd "${OUT_DIR}/30_count_matrix"
    abundance_estimates_to_matrix.pl --est_method RSEM \
        --gene_trans_map ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta.gene_trans_map \
        --name_sample_by_basedir --out_prefix RSEM \
        ${OUT_DIR}/20_estimate_abundance/*/RSEM.isoforms.results

    create_dir "${OUT_DIR}/40_DEGseq2"
    cd "${OUT_DIR}/40_DEGseq2"
    cut -f 1,2 ${OUT_DIR}/00_fastq/fastq_list.txt > fastq_list_for_DESeq2.txt

    run_DE_analysis.pl --matrix ${OUT_DIR}/30_count_matrix/RSEM.gene.counts.matrix \
        --method DESeq2 --samples_file fastq_list_for_DESeq2.txt \
        --output ${OUT_DIR}/40_DEGseq2/DEGseq2_gene_result
    run_DE_analysis.pl --matrix ${OUT_DIR}/30_count_matrix/RSEM.isoform.counts.matrix \
        --method DESeq2 --samples_file fastq_list_for_DESeq2.txt \
        --output ${OUT_DIR}/40_DEGseq2/DEGseq2_isoform_result
    log "[STEP] DESeq2 analysis complete."
}

run_degseq2

function make_cooksCutoff_FALSE() {

    DATA_TYPE=$1

    DIR_PREFIX=${OUT_DIR}/40_DEGseq2/DEGseq2_${DATA_TYPE}_result
    FILE_PREFIX=RSEM.${DATA_TYPE}.counts.matrix.N_vs_V.DESeq2

    mkdir -p ${DIR_PREFIX}_cooksCutoff_FALSE

    cat ${DIR_PREFIX}/${FILE_PREFIX}.Rscript | \
    sed "s/contrast)/contrast\,\ cooksCutoff\=FALSE)/g" \
    > ${DIR_PREFIX}_cooksCutoff_FALSE/${FILE_PREFIX}.cooksCutoff_FALSE.Rscript

    Rscript ${DIR_PREFIX}_cooksCutoff_FALSE/${FILE_PREFIX}.cooksCutoff_FALSE.Rscript

    mv ${FILE_PREFIX}.* ${DIR_PREFIX}_cooksCutoff_FALSE

    mv ${DIR_PREFIX}_cooksCutoff_FALSE/${FILE_PREFIX}.DE_results \
       ${DIR_PREFIX}_cooksCutoff_FALSE/${FILE_PREFIX}.DE_results.cooksCutoff_FALSE

    mv ${DIR_PREFIX}_cooksCutoff_FALSE/${FILE_PREFIX}.count_matrix \
       ${DIR_PREFIX}_cooksCutoff_FALSE/${FILE_PREFIX}.count_matrix.cooksCutoff_FALSE

    mv ${DIR_PREFIX}_cooksCutoff_FALSE/${FILE_PREFIX}.DE_results.MA_n_Volcano.pdf \
       ${DIR_PREFIX}_cooksCutoff_FALSE/${FILE_PREFIX}.DE_results.MA_n_Volcano.cooksCutoff_FALSE.pdf

}


function get_prefix() {

    DATA_TYPE=$1
    COOKSCUTOFF=$2

    if [ ${COOKSCUTOFF} = "TRUE" ]
    then

        DIR_PREFIX=${OUT_DIR}/40_DEGseq2/DEGseq2_${DATA_TYPE}_result
        FILE_PREFIX=RSEM.${DATA_TYPE}.counts.matrix.N_vs_V.DESeq2.DE_results

    else

        DIR_PREFIX=${OUT_DIR}/40_DEGseq2/DEGseq2_${DATA_TYPE}_result_cooksCutoff_FALSE
        FILE_PREFIX=RSEM.${DATA_TYPE}.counts.matrix.N_vs_V.DESeq2.DE_results.cooksCutoff_FALSE

    fi

    PREFIX=${DIR_PREFIX}/${FILE_PREFIX}

    echo ${PREFIX}

}


function get_significant_list() {

    DATA_TYPE=$1
    COOKSCUTOFF=$2

    PREFIX=`get_prefix ${DATA_TYPE} ${COOKSCUTOFF}`

    cat ${PREFIX} | \
    awk '{if ($10 < '${PVALUE}') print $0}' | \
    awk '{if ($7 < 0) print $0}' | \
    cut -f 1 \
    > ${PREFIX}.significant_${DATA_TYPE}s

}


function get_significant_fasta() {

    COOKSCUTOFF=$1


    PREFIX=`get_prefix isoform ${COOKSCUTOFF}`

    samtools faidx -r ${PREFIX}.significant_isoforms \
                      ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta \
                    > ${PREFIX}.significant_isoforms.fasta

    esl-translate ${PREFIX}.significant_isoforms.fasta | \
    sed "s/\ source\=/-/g" > ${PREFIX}.significant_isoforms.AA.fasta

}

function get_hmmscan_list() {

    HMMSCAN_RESULT=$1

    cat ${HMMSCAN_RESULT} | \
    grep -v "#" | \
    awk '{print $3}' | \
    cut -f 2 -d "-" | \
    sort | \
    uniq

}


function get_hmmscan_fasta() {

    ISOFORM_LIST=$1
    COOKSCUTOFF=$2

    if [ `cat ${ISOFORM_LIST} | wc -l` -gt 0 ]
    then

        if [ ${COOKSCUTOFF} = "TRUE" ]
        then

            samtools faidx -r ${ISOFORM_LIST} \
                            ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta \
                            > ${OUT_DIR}/60_fasta/${PFAM_ID}.fasta

        else

            samtools faidx -r ${ISOFORM_LIST} \
                            ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta \
                            > ${OUT_DIR}/60_fasta/${PFAM_ID}.cooksCutoff_FALSE.fasta

        fi

    fi

}


export make_cooksCutoff_FALSE
export get_prefix
export get_significant_list
export get_significant_fasta
export get_hmmscan_list
export get_hmmscan_fasta


make_cooksCutoff_FALSE "gene" 
make_cooksCutoff_FALSE "isoform"


get_significant_list "gene"    "TRUE"
get_significant_list "gene"    "FALSE"
get_significant_list "isoform" "TRUE"
get_significant_list "isoform" "FALSE"


get_significant_fasta "TRUE"
get_significant_fasta "FALSE"


# ---- 5.5 HMMER (Pfam Domain Scan) ----
run_hmmer() {
    log "[STEP] Running HMMER for Pfam domain annotation..."
    create_dir "${OUT_DIR}/50_hmmer"
    create_dir "${OUT_DIR}/60_fasta"
    cd "${OUT_DIR}/50_hmmer"

    # 用 FD 3 单独读取 Pfam 列表，避免任何子命令消耗循环输入
    exec 3< "$PFAM_ID_LIST"
    
    export TRINITY_CPU="${N_THREADS}"

    log "[HMMER INFO] hmm_model and P_fam_ID_list: ${PFAM_ID_LIST}"

    # Download Pfam_IDs_list.txt if needed
    if [ "$PFAM_ID_LIST" = "Default_list" ]; then
        download_if_not_exist "${VIIR_RESOURCES}/Pfam_IDs_list.txt" \
            "${BASE_URL}/example/Pfam_IDs_list.txt" \
            "${OUT_DIR}/50_hmmer/Pfam_IDs_list.txt"
        PFAM_ID_LIST="${OUT_DIR}/50_hmmer/Pfam_IDs_list.txt"
    fi

    # while read PFAM_ID || [ -n "$PFAM_ID" ]
    # do
    while IFS= read -r PFAM_ID <&3 || [ -n "$PFAM_ID" ]; do
        # 跳过空行/注释
        [ -z "$PFAM_ID" ] && continue
        case "$PFAM_ID" in \#*) continue ;; esac


        create_dir "${OUT_DIR}/50_hmmer/${PFAM_ID}"

        download_if_not_exist "${VIIR_RESOURCES}/hmm_models/${PFAM_ID}.hmm" \
            "${BASE_URL}/hmm_models/${PFAM_ID}.hmm" \
            "${OUT_DIR}/50_hmmer/${PFAM_ID}/${PFAM_ID}.hmm"
        
        log "[P_fam INFO] hmm_model and P_fam_ID_list: ${PFAM_ID_LIST}"


        hmmpress "${PFAM_ID}/${PFAM_ID}.hmm" </dev/null

        PREFIX=`get_prefix isoform TRUE`

        hmmscan  --cpu ${N_THREADS} \
                --tblout ${PFAM_ID}/${PFAM_ID}_hmmscan.txt \
                ${PFAM_ID}/${PFAM_ID}.hmm \
                ${PREFIX}.significant_isoforms.AA.fasta \
                1> /dev/null </dev/null


        PREFIX=`get_prefix isoform FALSE`

        hmmscan  --cpu ${N_THREADS} \
                --tblout ${PFAM_ID}/${PFAM_ID}_hmmscan.cooksCutoff_FALSE.txt \
                ${PFAM_ID}/${PFAM_ID}.hmm \
                ${PREFIX}.significant_isoforms.AA.fasta \
                1> /dev/null </dev/null

        get_hmmscan_list ${PFAM_ID}/${PFAM_ID}_hmmscan.txt \
                    > ${PFAM_ID}/${PFAM_ID}_hmmscan.isoform_list.txt

        get_hmmscan_list ${PFAM_ID}/${PFAM_ID}_hmmscan.cooksCutoff_FALSE.txt \
                    > ${PFAM_ID}/${PFAM_ID}_hmmscan.cooksCutoff_FALSE.isoform_list.txt

        get_hmmscan_fasta ${PFAM_ID}/${PFAM_ID}_hmmscan.isoform_list.txt "TRUE"
        get_hmmscan_fasta ${PFAM_ID}/${PFAM_ID}_hmmscan.cooksCutoff_FALSE.isoform_list.txt "FALSE"

    done < ${PFAM_ID_LIST}

    # 关闭 FD 3
    exec 3<&-


    cat ./*/*_hmmscan.isoform_list.txt | \
    sort | \
    uniq \
    > all_hmmscan.isoform_list.txt


    cat ./*/*_hmmscan.cooksCutoff_FALSE.isoform_list.txt | \
    sort | \
    uniq \
    > all_hmmscan.cooksCutoff_FALSE.isoform_list.txt 

    PFAM_ID="all"
    get_hmmscan_fasta all_hmmscan.isoform_list.txt "TRUE"
    get_hmmscan_fasta all_hmmscan.cooksCutoff_FALSE.isoform_list.txt  "FALSE"
    log "[STEP] HMMER analysis complete."

    download_if_not_exist "${VIIR_RESOURCES}/utils/generate_summary.py" \
     "${BASE_URL}/utils/generate_summary.py" \
     "${OUT_DIR}/generate_summary.py"

    cd ${OUT_DIR}

    python3 ${OUT_DIR}/generate_summary.py ${OUT_DIR}/60_fasta > ${OUT_DIR}/60_fasta/summary_table.txt

}

run_hmmer



# ---- 5.6 Barrnap (rRNA Annotation) ----
run_barrnap() {
    log "[STEP] Running barrnap for rRNA annotation..."
    create_dir "${OUT_DIR}/70_barrnap/isoform_list"
    barrnap --kingdom bac \
            ${OUT_DIR}/40_DEGseq2/DEGseq2_isoform_result/RSEM.isoform.counts.matrix.N_vs_V.DESeq2.DE_results.significant_isoforms.fasta \
            > ${OUT_DIR}/70_barrnap/barrnap_result.bac.txt

    barrnap --kingdom euk \
            ${OUT_DIR}/40_DEGseq2/DEGseq2_isoform_result/RSEM.isoform.counts.matrix.N_vs_V.DESeq2.DE_results.significant_isoforms.fasta \
            > ${OUT_DIR}/70_barrnap/barrnap_result.euk.txt

    barrnap --kingdom bac \
            ${OUT_DIR}/40_DEGseq2/DEGseq2_isoform_result_cooksCutoff_FALSE/RSEM.isoform.counts.matrix.N_vs_V.DESeq2.DE_results.cooksCutoff_FALSE.significant_isoforms.fasta \
            > ${OUT_DIR}/70_barrnap/barrnap_result.bac.cooksCutoff_FALSE.txt

    barrnap --kingdom euk \
            ${OUT_DIR}/40_DEGseq2/DEGseq2_isoform_result_cooksCutoff_FALSE/RSEM.isoform.counts.matrix.N_vs_V.DESeq2.DE_results.cooksCutoff_FALSE.significant_isoforms.fasta \
            > ${OUT_DIR}/70_barrnap/barrnap_result.euk.cooksCutoff_FALSE.txt


    for cooksCutoff in "" ".cooksCutoff_FALSE"
    do
    for rRNA in rRNA 5S_rRNA 16S_rRNA 23S_rRNA
    do
        cat ${OUT_DIR}/70_barrnap/barrnap_result.bac${cooksCutoff}.txt | \
        grep -v "#" | \
        grep ${rRNA} | \
        cut -f 1 | \
        sort | \
        uniq > ${OUT_DIR}/70_barrnap/bac_${rRNA}${cooksCutoff}.isoform_list.txt
        
        if [ `cat ${OUT_DIR}/70_barrnap/bac_${rRNA}${cooksCutoff}.isoform_list.txt | wc -l` -gt 0 ]
        then
        samtools faidx -r ${OUT_DIR}/70_barrnap/bac_${rRNA}${cooksCutoff}.isoform_list.txt \
        ${OUT_DIR}/40_DEGseq2/DEGseq2_isoform_result_cooksCutoff_FALSE/RSEM.isoform.counts.matrix.N_vs_V.DESeq2.DE_results.cooksCutoff_FALSE.significant_isoforms.fasta \
        > ${OUT_DIR}/70_barrnap/bac_${rRNA}${cooksCutoff}.fasta
        else
        touch ${OUT_DIR}/70_barrnap/bac_${rRNA}${cooksCutoff}.fasta
        fi
    done
    done

    for cooksCutoff in "" ".cooksCutoff_FALSE"
    do
    for rRNA in rRNA 5.8S_rRNA 18S_rRNA 28S_rRNA
    do
        cat ${OUT_DIR}/70_barrnap/barrnap_result.euk${cooksCutoff}.txt | \
        grep -v "#" | \
        grep ${rRNA} | \
        cut -f 1 | \
        sort | \
        uniq > ${OUT_DIR}/70_barrnap/euk_${rRNA}${cooksCutoff}.isoform_list.txt

        if [ `cat ${OUT_DIR}/70_barrnap/euk_${rRNA}${cooksCutoff}.isoform_list.txt | wc -l` -gt 0 ]
        then
        samtools faidx -r ${OUT_DIR}/70_barrnap/euk_${rRNA}${cooksCutoff}.isoform_list.txt \
        ${OUT_DIR}/40_DEGseq2/DEGseq2_isoform_result_cooksCutoff_FALSE/RSEM.isoform.counts.matrix.N_vs_V.DESeq2.DE_results.cooksCutoff_FALSE.significant_isoforms.fasta \
        > ${OUT_DIR}/70_barrnap/euk_${rRNA}${cooksCutoff}.fasta
        else
        touch ${OUT_DIR}/70_barrnap/euk_${rRNA}${cooksCutoff}.fasta
        fi



    done
    done

    mv ${OUT_DIR}/70_barrnap/euk_rRNA.cooksCutoff_FALSE.fasta ${OUT_DIR}/70_barrnap/euk_all_rRNA.cooksCutoff_FALSE.fasta
    mv ${OUT_DIR}/70_barrnap/euk_rRNA.cooksCutoff_FALSE.isoform_list.txt ${OUT_DIR}/70_barrnap/euk_all_rRNA.cooksCutoff_FALSE.isoform_list.txt
    mv ${OUT_DIR}/70_barrnap/euk_rRNA.fasta ${OUT_DIR}/70_barrnap/euk_all_rRNA.fasta
    mv ${OUT_DIR}/70_barrnap/euk_rRNA.isoform_list.txt ${OUT_DIR}/70_barrnap/euk_all_rRNA.isoform_list.txt

    mv ${OUT_DIR}/70_barrnap/bac_rRNA.cooksCutoff_FALSE.fasta ${OUT_DIR}/70_barrnap/bac_all_rRNA.cooksCutoff_FALSE.fasta
    mv ${OUT_DIR}/70_barrnap/bac_rRNA.cooksCutoff_FALSE.isoform_list.txt ${OUT_DIR}/70_barrnap/bac_all_rRNA.cooksCutoff_FALSE.isoform_list.txt
    mv ${OUT_DIR}/70_barrnap/bac_rRNA.fasta ${OUT_DIR}/70_barrnap/bac_all_rRNA.fasta
    mv ${OUT_DIR}/70_barrnap/bac_rRNA.isoform_list.txt ${OUT_DIR}/70_barrnap/bac_all_rRNA.isoform_list.txt

    mv ${OUT_DIR}/70_barrnap/*.isoform_list.txt ${OUT_DIR}/70_barrnap/isoform_list

    python3 ${OUT_DIR}/generate_summary.py ${OUT_DIR}/70_barrnap > ${OUT_DIR}/70_barrnap/rRNA_summary_table.txt

    log "[STEP] Barrnap rRNA annotation complete."
}

run_barrnap



# ---- 5.7 K-mer Analysis ----
run_kmer() {
    log "[STEP] Running k-mer analysis..."
    create_dir "${OUT_DIR}/80_kmer/isoform_list"

    download_if_not_exist "${VIIR_RESOURCES}/utils/count_kmers.py" \
        "${BASE_URL}/utils/count_kmers.py" \
        "${OUT_DIR}/count_kmers.py"

    for KMER in 100 150 200
    do
    python3 ${OUT_DIR}/count_kmers.py ${OUT_DIR}/40_DEGseq2/DEGseq2_isoform_result/RSEM.isoform.counts.matrix.N_vs_V.DESeq2.DE_results.significant_isoforms.fasta ${KMER} 2 1000 \
    > ${OUT_DIR}/80_kmer/kmer_${KMER}.isoform_list.txt
    
    python3 ${OUT_DIR}/count_kmers.py ${OUT_DIR}/40_DEGseq2/DEGseq2_isoform_result_cooksCutoff_FALSE/RSEM.isoform.counts.matrix.N_vs_V.DESeq2.DE_results.cooksCutoff_FALSE.significant_isoforms.fasta ${KMER} 2 2000 \
    > ${OUT_DIR}/80_kmer/kmer_${KMER}.cooksCutoff_FALSE.isoform_list.txt

    if [ `cat ${OUT_DIR}/80_kmer/kmer_${KMER}.isoform_list.txt | wc -l` -gt 0 ]
    then
        samtools faidx -r ${OUT_DIR}/80_kmer/kmer_${KMER}.isoform_list.txt \
        ${OUT_DIR}/40_DEGseq2/DEGseq2_isoform_result/RSEM.isoform.counts.matrix.N_vs_V.DESeq2.DE_results.significant_isoforms.fasta \
        > ${OUT_DIR}/80_kmer/kmer_${KMER}.fasta
    fi

    if [ `cat ${OUT_DIR}/80_kmer/kmer_${KMER}.cooksCutoff_FALSE.isoform_list.txt | wc -l` -gt 0 ]
    then
        samtools faidx -r ${OUT_DIR}/80_kmer/kmer_${KMER}.cooksCutoff_FALSE.isoform_list.txt \
        ${OUT_DIR}/40_DEGseq2/DEGseq2_isoform_result_cooksCutoff_FALSE/RSEM.isoform.counts.matrix.N_vs_V.DESeq2.DE_results.cooksCutoff_FALSE.significant_isoforms.fasta \
        > ${OUT_DIR}/80_kmer/kmer_${KMER}.cooksCutoff_FALSE.fasta
    fi
    done

    mv ${OUT_DIR}/80_kmer/*.isoform_list.txt ${OUT_DIR}/80_kmer/isoform_list

    python3 ${OUT_DIR}/generate_summary.py ${OUT_DIR}/80_kmer > ${OUT_DIR}/80_kmer/kmer_summary_table.txt

    log "[STEP] K-mer analysis complete."
}

run_kmer


# ---- 5.8 BLASTN ----
run_blastn() {
    log "[STEP] Running BLASTN annotation..."
    create_dir "${OUT_DIR}/90_blastn/blastndb"
    cd ${OUT_DIR}/90_blastn/blastndb

    export TRINITY_CPU="${N_THREADS}"

    if [ ${BLASTNDB_RAW} = "Default_db" ]
    # if [ ${BLASTNDB_FASTA} = "${VIIR_RESOURCES}/Default_db" ]
    then
        # git clone https://github.com/YuSugihara/ViiR_DB.git
        # cd ViiR_DB
        log "[INFO] BLASTN with Default_db..."
        cd ${BLASTNDB_FASTA}
        cat ./NCBI_Virus_RefSeq_nuc-23-01-23.*.fasta.gz > ../NCBI_Virus_RefSeq_nuc-23-01-23.fasta.gz
        cd ..
        gzip -d NCBI_Virus_RefSeq_nuc-23-01-23.fasta.gz
        
        cp ${VIIR_RESOURCES}/NCBI_Virus_RefSeq_nuc-23-01-23.fasta ${OUT_DIR}/90_blastn/blastndb/
        BLASTNDB_FASTA=${OUT_DIR}/90_blastn/blastndb/NCBI_Virus_RefSeq_nuc-23-01-23.fasta
        # BLASTNDB_FASTA=${OUT_DIR}/90_blastn/blastndb/${DB_basename%.gz}
        cd ${OUT_DIR}/90_blastn/blastndb/
        log "[INFO] BLASTN addess: $BLASTNDB_FASTA"

        makeblastdb -dbtype nucl \
            -in `basename ${BLASTNDB_FASTA}` \
            -parse_seqids \
            -out `basename ${BLASTNDB_FASTA}`
    else
        ln -s ${BLASTNDB_FASTA}
    fi

    cd ${OUT_DIR}/90_blastn/
    log "[INFO] BLASTN query ..."
    blastn -db ${OUT_DIR}/90_blastn/blastndb/`basename ${BLASTNDB_FASTA}` \
        -query ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta \
        -evalue 0.001 \
        -max_target_seqs 5 \
        -num_threads ${N_THREADS} \
        -outfmt "6 qseqid sacc stitle evalue bitscore length pident qcovs" | \
    awk -F"\t" '$8 >= 40' > blastn_result.tsv

    cut -f 1 blastn_result.tsv  | sort | uniq > blastn_result.isoform_list.txt

    if [ `cat blastn_result.isoform_list.txt | wc -l` -gt 0 ]
    then
    samtools faidx -r blastn_result.isoform_list.txt \
    ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta \
    > blastn_result.isoform_list.fasta
    fi

    rm -rf ${OUT_DIR}/90_blastn/blastndb/*.fasta.*
    cd ${OUT_DIR}/90_blastn/blastndb
    if [ ${BLASTNDB_FASTA} = "Default_db" ]
    then
    rm -rf ${BLASTNDB_FASTA}
    BLASTNDB_FASTA=${OUT_DIR}/90_blastn/blastndb/adapter.fasta
    else
    unlink `basename ${BLASTNDB_FASTA}`
    fi
    cd ..
    rm -rf blastndb

    log "[STEP] BLASTN annotation complete."
}

run_blastn

# ========================== 6. Execute Main Pipeline ============================
# run_trimmomatic
# run_trinity
# run_abundance_estimation
# run_degseq2
# run_hmmer
# run_barrnap
# run_kmer
# run_blastn

log "[INFO] ViiR pipeline complete."
