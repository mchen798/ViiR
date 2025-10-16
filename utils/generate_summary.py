#! /usr/bin/env python3

import sys
import glob
import os
import re


fasta_dir = sys.argv[1]
result_dir = "/".join(fasta_dir.split("/")[:-1])
fasta_files = glob.glob("{}/*.fasta".format(fasta_dir))
fasta_files = [fasta_file for fasta_file in fasta_files if "all" not in os.path.basename(fasta_file)]

transcript_ids = {}
transcript_ids_cooksCutoff_FALSE = {}

def add_annotation(transcript_ids, transcript_id, annotation):
    if transcript_id not in transcript_ids:
        transcript_ids[transcript_id] = [annotation]
    else:
        transcript_ids[transcript_id].append(annotation)
    return transcript_ids

def get_expressions(transcript_id):
    with open("{}/30_count_matrix/RSEM.isoform.TMM.EXPR.matrix".format(result_dir)) as f:
        for line in f:
            if transcript_id in line:
                line = line.rstrip("\n")
                cols = line.split("\t")
                return cols[1:]

def get_pvalue(transcript_id):
    with open("{}/40_DEGseq2/DEGseq2_isoform_result_cooksCutoff_FALSE/RSEM.isoform.counts.matrix.N_vs_V.DESeq2.DE_results.cooksCutoff_FALSE".format(result_dir)) as f:
        for line in f:
            if transcript_id in line:
                line = line.rstrip("\n")
                cols = line.split("\t")
                pvalue = cols[9]
                return pvalue

for fasta_file in fasta_files:
    annotation = os.path.basename(fasta_file).split(".")[0]
    with open(fasta_file) as f:
        for line in f:
            if re.match(">", line):
                transcript_id = line.lstrip(">")
                transcript_id = transcript_id.rstrip("\n")
                if re.match(">", line):
                    if "cooksCutoff_FALSE" in fasta_file:
                        transcript_ids_cooksCutoff_FALSE = add_annotation(transcript_ids_cooksCutoff_FALSE, \
                                                                          transcript_id, \
                                                                          annotation)
                    else:
                        transcript_ids = add_annotation(transcript_ids, \
                                                        transcript_id, \
                                                        annotation)

for k, v in transcript_ids_cooksCutoff_FALSE.items():
    annotations = ",".join(set(v))
    exps = "\t".join(get_expressions(k))
    pvalue = get_pvalue(k)
    if k in transcript_ids:
        print(k, "-", annotations, ",".join(transcript_ids[k]), pvalue, exps, sep="\t")
    else:
        print(k, "+", annotations, "", pvalue, exps, sep="\t")

