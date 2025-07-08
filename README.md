# ViiR

ViiR (Virus Identification Independent of Reference sequences) assembles and annotates viral reads from RNA-Seq data. The pipeline combines Trinity, differential expression analysis and several annotation steps.

## Requirements
- [Docker](https://docs.docker.com/get-docker/) installed on your system.

## Build the Docker image
Clone the repository and build the image:

```bash
git clone https://github.com/YuSugihara/ViiR.git
cd ViiR
docker build -t viir .
```

## Running ViiR
### Web interface
Run the container with a directory containing your FASTQ files mounted under `/data`:

```bash
docker run -p 8080:8080 \
  -v /path/to/data:/data \
  viir
```

Open `http://localhost:8080` in your browser to upload a FASTQ list or YAML configuration file and start an analysis. Results are written inside the mounted directory.

### Command-line usage
You can also execute the pipeline directly from the command line. Mount a data directory and override the container entrypoint:

```bash
docker run --rm \
  -v /path/to/data:/data \
  --entrypoint micromamba \
  viir run -n viir viir -l /data/sample_list.txt -o /data/out
```

The image includes example adapter sequences, Pfam lists and HMM models. On the first run a small BLAST database (~9&nbsp;MB) is downloaded and cached under `/root/.viir_db`. Set `VIIR_DB_CACHE` to change this location. The `VIIR_RESOURCES` variable can point to alternate resource files if needed.

## Output
All results are written to the specified output directory. `config_used.yaml` and a copy of `run_viir.sh` are saved for reproducibility. Intermediate files are placed in numbered folders (10_trinity, 40_DEGseq2, ...). Summary tables of Pfam domains, rRNAs and k‑mers are produced at the end of the run.

