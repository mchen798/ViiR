#!/usr/bin/env bash -e


######################### Parameters #####################################
OUT_DIR=$(cd $(dirname $1); pwd)/$(basename $1)
FASTQ_LIST=$(cd $(dirname $2); pwd)/$(basename $2)
PVALUE=$3
PFAM_ID_LIST=$4
N_THREADS=$5
MAX_MEMORY=$6
SS_LIB_TYPE=$7
ADAPTER_FASTA=$8
BLASTNDB_FASTA=$9
##########################################################################


########################### Function ####################################
function download_if_not_exist() {
    local local_path="$1"
    local url="$2"
    local target_path="$3"

    if [ -f "./${filename}" ]; then
        cp "./${filename}" "$target_path"
        echo "📁 Use local file: ./${filename} → ${target_path}"
    elif [ -f "../${filename}" ]; then
        cp "../${filename}" "$target_path"
        echo "📁 Use ../Local file: ../${filename} → ${target_path}"
    else
        wget "$url" -O "$target_path"
        echo "🌐 Download file: $url → $target_path"
    fi
}
##################################################################
BASE_URL="https://raw.githubusercontent.com/YuSugihara/ViiR/master"


if [ ${ADAPTER_FASTA} != "Default_adapter" ]
then
    ADAPTER_FASTA=$(cd $(dirname $8); pwd)/$(basename $8)
fi

if [ ${BLASTNDB_FASTA} != "Default_db" ]
then
    BLASTNDB_FASTA=$(cd $(dirname $9); pwd)/$(basename $9)
fi

mkdir -p ${OUT_DIR}/00_fastq

if [ ${ADAPTER_FASTA} = "Default_adapter" ]
then

    download_if_not_exist "adapters.fasta" \
        "${BASE_URL}/example/adapters.fasta" \
        "${OUT_DIR}/00_fastq/adapter.fasta"
    # wget "${BASE_URL}/example/adapters.fasta \  
    #      -O ${OUT_DIR}/00_fastq/adapter.fasta

    ADAPTER_FASTA=${OUT_DIR}/00_fastq/adapter.fasta

fi


FASTQ_CNT=0
TRINITY_LEFT=""
TRINITY_RIGHT=""


while read LINE || [ -n "${LINE}" ]
do

    COLS=(${LINE})

    SAMPLE_TYPE=${COLS[0]}

    
    FASTQ1=${COLS[1]}
    FASTQ2=${COLS[2]}


    mkdir -p ${OUT_DIR}/00_fastq/${SAMPLE_TYPE}${FASTQ_CNT}

    PREFIX=${OUT_DIR}/00_fastq/${SAMPLE_TYPE}${FASTQ_CNT}/${SAMPLE_TYPE}${FASTQ_CNT}

    trimmomatic PE -threads ${N_THREADS} -phred33 \
    ${FASTQ1} \
    ${FASTQ2} \
    ${PREFIX}.1.trimmed.fastq.gz \
    ${PREFIX}.1.unpaired.trimmed.fastq.gz \
    ${PREFIX}.2.trimmed.fastq.gz \
    ${PREFIX}.2.unpaired.trimmed.fastq.gz \
    ILLUMINACLIP:${ADAPTER_FASTA}:2:30:10 \
    LEADING:20 \
    TRAILING:20 \
    SLIDINGWINDOW:4:15 \
    MINLEN:75

    echo "${SAMPLE_TYPE}    \
          ${SAMPLE_TYPE}${FASTQ_CNT}    \
          ${PREFIX}.1.trimmed.fastq.gz    \
          ${PREFIX}.2.trimmed.fastq.gz" >> ${OUT_DIR}/00_fastq/fastq_list.txt


    if [ ${FASTQ_CNT} = 0 ]
    then

        TRINITY_LEFT="${PREFIX}.1.trimmed.fastq.gz"
        TRINITY_RIGHT="${PREFIX}.2.trimmed.fastq.gz"

    else

        TRINITY_LEFT="${TRINITY_LEFT},${PREFIX}.1.trimmed.fastq.gz"
        TRINITY_RIGHT="${TRINITY_RIGHT},${PREFIX}.2.trimmed.fastq.gz"

    fi


    FASTQ_CNT=$((FASTQ_CNT+1))


done < ${FASTQ_LIST}


mkdir -p ${OUT_DIR}/10_trinity


if [ ${SS_LIB_TYPE} = "No" ]
then

    Trinity --seqType fq \
            --max_memory ${MAX_MEMORY} \
            --left ${TRINITY_LEFT} \
            --right ${TRINITY_RIGHT} \
            --output ${OUT_DIR}/10_trinity/trinity_assembly \
            --CPU ${N_THREADS} \
            --full_cleanup

else

    Trinity --seqType fq \
            --max_memory ${MAX_MEMORY} \
            --left ${TRINITY_LEFT} \
            --right ${TRINITY_RIGHT} \
            --output ${OUT_DIR}/10_trinity/trinity_assembly \
            --SS_lib_type ${SS_LIB_TYPE} \
            --CPU ${N_THREADS} \
            --full_cleanup

fi


mkdir -p ${OUT_DIR}/20_estimate_abundance

cd ${OUT_DIR}/20_estimate_abundance


if [ ${SS_LIB_TYPE} = "No" ]
then

    align_and_estimate_abundance.pl --transcripts ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta \
                                    --gene_trans_map ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta.gene_trans_map \
                                    --seqType fq \
                                    --samples_file ${OUT_DIR}/00_fastq/fastq_list.txt \
                                    --est_method RSEM \
                                    --aln_method bowtie \
                                    --coordsort_bam \
                                    --trinity_mode \
                                    --prep_reference \
                                    --thread_count ${N_THREADS}

else

    align_and_estimate_abundance.pl --transcripts ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta \
                                    --gene_trans_map ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta.gene_trans_map \
                                    --seqType fq \
                                    --samples_file ${OUT_DIR}/00_fastq/fastq_list.txt \
                                    --SS_lib_type ${SS_LIB_TYPE} \
                                    --est_method RSEM \
                                    --aln_method bowtie \
                                    --coordsort_bam \
                                    --trinity_mode \
                                    --prep_reference \
                                    --thread_count ${N_THREADS}
fi



mkdir -p ${OUT_DIR}/30_count_matrix

cd ${OUT_DIR}/30_count_matrix


abundance_estimates_to_matrix.pl --est_method RSEM \
                                 --gene_trans_map ${OUT_DIR}/10_trinity/trinity_assembly.Trinity.fasta.gene_trans_map \
                                 --name_sample_by_basedir \
                                 --out_prefix RSEM \
                                 ${OUT_DIR}/20_estimate_abundance/*/RSEM.isoforms.results



mkdir -p ${OUT_DIR}/40_DEGseq2

cd ${OUT_DIR}/40_DEGseq2

cut -f 1,2 ${OUT_DIR}/00_fastq/fastq_list.txt > fastq_list_for_DESeq2.txt


run_DE_analysis.pl --matrix ${OUT_DIR}/30_count_matrix/RSEM.gene.counts.matrix \
                   --method DESeq2 \
                   --samples_file fastq_list_for_DESeq2.txt \
                   --output ${OUT_DIR}/40_DEGseq2/DEGseq2_gene_result


run_DE_analysis.pl --matrix ${OUT_DIR}/30_count_matrix/RSEM.isoform.counts.matrix \
                   --method DESeq2 \
                   --samples_file fastq_list_for_DESeq2.txt \
                   --output ${OUT_DIR}/40_DEGseq2/DEGseq2_isoform_result


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


mkdir -p ${OUT_DIR}/50_hmmer
mkdir -p ${OUT_DIR}/60_fasta

cd ${OUT_DIR}/50_hmmer


if [ ${PFAM_ID_LIST} = "Default_list" ]
then

    # download_if_not_exist "Pfam_IDs_list.txt" \
    #     "${BASE_URL}/example/Pfam_IDs_list.txt" \
    #     "${OUT_DIR}/50_hmmer/Pfam_IDs_list.txt"
    wget "${BASE_URL}/example/Pfam_IDs_list.txt

    PFAM_ID_LIST=${OUT_DIR}/50_hmmer/Pfam_IDs_list.txt

fi


while read PFAM_ID || [ -n "${PFAM_ID}" ]
do

    mkdir -p ${OUT_DIR}/50_hmmer/${PFAM_ID}

    # download_if_not_exist "/hmm_models/${PFAM_ID}.hmm" \
    #     "${BASE_URL}/hmm_models/${PFAM_ID}.hmm" \
    #     "${OUT_DIR}/50_hmmer/${PFAM_ID}/${PFAM_ID}.hmm"

    wget "${BASE_URL}/hmm_models/${PFAM_ID}.hmm \
         -O ${PFAM_ID}/${PFAM_ID}.hmm


    hmmpress ${PFAM_ID}/${PFAM_ID}.hmm


    PREFIX=`get_prefix isoform TRUE`

    hmmscan  --cpu ${N_THREADS} \
             --tblout ${PFAM_ID}/${PFAM_ID}_hmmscan.txt \
             ${PFAM_ID}/${PFAM_ID}.hmm \
             ${PREFIX}.significant_isoforms.AA.fasta \
             1> /dev/null


    PREFIX=`get_prefix isoform FALSE`

    hmmscan  --cpu ${N_THREADS} \
             --tblout ${PFAM_ID}/${PFAM_ID}_hmmscan.cooksCutoff_FALSE.txt \
             ${PFAM_ID}/${PFAM_ID}.hmm \
             ${PREFIX}.significant_isoforms.AA.fasta \
             1> /dev/null

    get_hmmscan_list ${PFAM_ID}/${PFAM_ID}_hmmscan.txt \
                   > ${PFAM_ID}/${PFAM_ID}_hmmscan.isoform_list.txt

    get_hmmscan_list ${PFAM_ID}/${PFAM_ID}_hmmscan.cooksCutoff_FALSE.txt \
                   > ${PFAM_ID}/${PFAM_ID}_hmmscan.cooksCutoff_FALSE.isoform_list.txt

    get_hmmscan_fasta ${PFAM_ID}/${PFAM_ID}_hmmscan.isoform_list.txt "TRUE"
    get_hmmscan_fasta ${PFAM_ID}/${PFAM_ID}_hmmscan.cooksCutoff_FALSE.isoform_list.txt "FALSE"

done < ${PFAM_ID_LIST}


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


wget "${BASE_URL}/utils/generate_summary.py \
     -O ${OUT_DIR}/generate_summary.py

cd ${OUT_DIR}

python3 ${OUT_DIR}/generate_summary.py ${OUT_DIR}/60_fasta > ${OUT_DIR}/60_fasta/summary_table.txt


mkdir -p ${OUT_DIR}/70_barrnap/isoform_list

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


mkdir -p ${OUT_DIR}/80_kmer/isoform_list

wget "${BASE_URL}/utils/count_kmers.py \
     -O ${OUT_DIR}/count_kmers.py

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


mkdir -p ${OUT_DIR}/90_blastn/blastndb
cd ${OUT_DIR}/90_blastn/blastndb

if [ ${BLASTNDB_FASTA} = "Default_db" ]
then
  git clone https://github.com/YuSugihara/ViiR_DB.git
  cd ViiR_DB
  cat ./NCBI_Virus_RefSeq_nuc-23-01-23.*.fasta.gz > ../NCBI_Virus_RefSeq_nuc-23-01-23.fasta.gz
  cd ..
  gzip -d NCBI_Virus_RefSeq_nuc-23-01-23.fasta.gz
  BLASTNDB_FASTA=${OUT_DIR}/90_blastn/blastndb/NCBI_Virus_RefSeq_nuc-23-01-23.fasta
else
  ln -s ${BLASTNDB_FASTA}
fi

makeblastdb -dbtype nucl \
            -in `basename ${BLASTNDB_FASTA}` \
            -parse_seqids \
            -out `basename ${BLASTNDB_FASTA}`

cd ${OUT_DIR}/90_blastn/

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
