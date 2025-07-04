# ViiR User Guide

ViiR identifies viral sequences without relying on a reference genome. The
pipeline combines Trinity assembly, differential expression analysis and several
annotation steps. Version 0.0.2 packages the helper scripts and HMM models with
the tool so an internet connection is only required the first time the BLASTn
reference database is downloaded.

## Installation

ViiR is distributed as a Python package. We recommend creating a fresh conda
environment with the required bioinformatics tools:

```bash
conda create -n viir -c bioconda trinity hmmer wget samtools biopython barrnap
conda activate viir
conda install -c bioconda rsem bioconductor-deseq2 bioconductor-edger r blast
git clone https://github.com/YuSugihara/ViiR.git
cd ViiR
pip install .
```

The first run will fetch a viral BLAST database (~9 MB) and store it under
`~/.viir_db`. Subsequent executions reuse this cache.

## Basic Usage

```
viir -l <FASTQ_LIST> -o <OUT_DIR> [options]
```

Common options:

- `-t / --threads` – number of CPU threads (default: 16)
- `--max-memory` – memory for Trinity (default: 32G)
- `--SS-lib-type` – strand specificity (`No`, `FR` or `RF`)
- `--adapter` – FASTA of adapter sequences. If omitted the bundled example set
  is used.
- `--pfam` – list of Pfam IDs. Defaults to the bundled list.
- `--blastndb` – FASTA for BLAST annotation. Defaults to the cached reference.

### YAML Configuration

Parameters can also be supplied in a YAML file:

```yaml
fastq-list: path/to/sample_list.txt
out: output/run1
threads: 32
pvalue: 0.01
```

Run with:

```bash
viir --config config.yaml
```

Command line arguments override values in the configuration file.

## Output

All pipeline steps run inside the specified output directory. `config_used.yaml`
and a copy of `run_viir.sh` are saved for reproducibility. Intermediate files are
placed in numbered subdirectories (10_trinity, 40_DEGseq2, …). At the end the
pipeline reports summary tables of detected Pfam domains, rRNAs and k‑mers.

## Docker Web Interface

A lightweight Docker image is provided for running ViiR with a small web front
end. Build and run it with your data directory mounted:

```bash
docker build -t viir-web .
docker run -p 8080:8080 \
  -v /path/to/data:/data \
  viir-web
```

Navigate to `http://localhost:8080` to upload a configuration file and start the
analysis. Results are written inside the mounted data directory.
