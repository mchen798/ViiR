#! /usr/bin/env python3

import sys
import collections
from Bio import SeqIO


fasta = sys.argv[1]
kmer = int(sys.argv[2])
min_kmer_count = int(sys.argv[3])
max_seq_length = int(sys.argv[4])

def count_kmer(seq, kmer):
    segments = []
    for i in range(0, len(seq) - kmer):
        segments.append(seq[i:i + kmer])
    count_kmers = collections.Counter(segments)
    max_kmer_count = max(count_kmers.values())
    return max_kmer_count
    
records = SeqIO.parse(fasta, "fasta")

for record in records:
    if len(record.seq) <= max_seq_length:
        max_kmer_count = count_kmer(record.seq, kmer)
        if max_kmer_count >= min_kmer_count:
            print(record.id)
