#!/usr/bin/env bash
set -euo pipefail

# Simple wrapper around the Python CLI

INPUT=${1:-}
if [ -z "$INPUT" ]; then
  echo "Usage: $0 <fastq>" >&2
  exit 1
fi

python -m viir_core.cli trim "$INPUT"
python -m viir_core.cli assemble trimmed.fastq.gz
python -m viir_core.cli quant assembly.fasta
# add additional steps as needed
