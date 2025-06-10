# ViiR User Guide
#### Version 0.0.1

## Table of contents
- [What is ViiR?](#what-is-viir)
- [Installation](#installation)
  + [Dependencies](#dependencies)
  + [Installation](#installation)
- [Usage](#usage)
  + [Example 1 : Run ViiR with default settings](#example-1--run-viir-with-default-settings)
  + [Example 2 : Run ViiR with more threads and CPU memories](#example-2--run-viir-with-more-threads-and-cpu-memories)
  + [Example 3 : Run ViiR with strand specific library](#example-3--run-viir-with-strand-specific-library)


## What is ViiR?

ViiR is a software for 'Virus identification independent of Reference sequence'.

## Installation
### Dependencies
#### Softwares
- [Python3](https://www.python.org/downloads/)
- [wget](https://www.gnu.org/software/wget/)
- [Trinity package](https://github.com/trinityrnaseq/trinityrnaseq)
  + [Trinity](https://github.com/trinityrnaseq/trinityrnaseq)
  + [Trimmomatic](http://www.usadellab.org/cms/?page=trimmomatic)
  + [Samtools](http://www.htslib.org/doc/samtools.html)
- [HMMER](http://hmmer.org/)
- [R](https://www.r-project.org/)
- [DESeq2](https://bioconductor.org/packages/3.14/bioc/vignettes/DESeq2/inst/doc/DESeq2.html)
- [edgeR](https://bioconductor.org/packages/release/bioc/html/edgeR.html)
- [RSEM](https://deweylab.github.io/RSEM/)
- [Biopython](https://biopython.org)


### Installation
ViiR and its dependencies are easily installed via [bioconda](https://bioconda.github.io/index.html) like below:

```
conda create -n viir -c bioconda trinity hmmer wget samtools biopython barrnap
conda activate viir
conda install -c bioconda rsem bioconductor-deseq2 bioconductor-edger r bowtie
git clone https://github.com/YuSugihara/ViiR.git
cd ViiR
pip install . 
```

**If you install RSEM and DESeq2 with other dependencies at the same time, anaconda will take too long time to solve the environment or cannot solve it.** Therefore, we highly recommend the users to install them separately via bioconda.


If the error ```samtools: error while loading shared libraries: libcrypto.so.1.0.0: cannot open shared object file: No such file or directory``` appeared, the symbolic link might solve the error. 

```
ln -s ~/miniconda3/envs/viir/lib/libcrypto.so.3 ~/miniconda3/envs/viir/lib/libcrypto.so.1.0.0
```

Please change the path ```~/miniconda3/envs/viir/lib``` to your environment.



## Usage

```
usage: viir -l <FASTQ_LIST> -o <OUT_DIR> [-t <INT>]

ViiR version 0.0.1

optional arguments:
  -h, --help          show this help message and exit
  -l , --fastq-list   Fastq list.
  -o , --out          Output directory. Specified name must not
                      exist.
  -t , --threads      Number of threads. [16]
  -a , --adapter      FASTA of adapter sequences. If you don't
                      specify this option, the defaul adapter set
                      will be used.
  --pfam              List of Pfam IDs. If you don't specify
                      this option, the defaul list will be used.
  --SS-lib-type       Type of strand specific library (No/FR/RF). [No]
  --pvalue            Threshold of pvalue in DESeq2. [0.01]
  --max-memory        Max memory used in Trinity. [32G]
  -v, --version       show program's version number and exit
```

---

### 🧩 Using YAML Configuration File

Starting from version 0.0.2+, **ViiR now supports running via a YAML-based configuration file**, making it easier to batch-run analyses and archive parameter settings.

#### 📄 Example: `config_example.yaml`

```yaml
fastq-list: input/sample_list.txt         # Required: path to FASTQ list
out: output/run_20250527_01               # Required: output directory
threads: 16                               # Optional: number of threads
adapter: Default_adapter                  # Optional: adapter file or default
pfam: Default_list                        # Optional: Pfam ID list or default
SS-lib-type: No                           # Optional: strand specificity (No/FR/RF)
blastndb: Default_db                      # Optional: BLASTN DB or default
pvalue: 0.01                              # Optional: DESeq2 p-value threshold
max-memory: 32G                           # Optional: memory limit for Trinity
```

#### 🚀 How to Run with Config File

```bash
viir --config config/config_example.yaml
```

 If both `--config` and command-line arguments are used, **CLI arguments override config values**.
  
Override any value inline:

```bash
viir --config config/config_example.yaml --threads 32 --pvalue 0.005
```


#### 📁 Output Structure

When using YAML, ViiR will automatically:

* Save `config_used.yaml` inside the output folder for reproducibility.
* Download and execute the `run_viir.sh` pipeline script in the same output folder.

---


### Example 1 : Run ViiR with default settings

```
viir -l sample_list.txt \
     -o result \
```

`-l` : Sample list describing the paired-end FASTQ files.

`-o` : Name of the output directory. Specified name should not exist.

### Example 2 : Run ViiR with more threads and CPU memories

```
viir -l sample_list.txt \
     -o result \
     -t 40 \
     --max-memory 1000G
```

`-l` : Sample list describing the paired-end FASTQ files.

`-o` : Name of the output directory. Specified name should not exist.

`-t` : Number of threads.

`--max-memory` : Maximum memory used for Trinity.

### Example 3 : Run ViiR with strand specific library

```
viir -l sample_list.txt \
     -o result \
     -t 40 \
     --max-memory 1000G \
     --SS-lib-type FR
```

`-l` : Sample list describing the paired-end FASTQ files.

`-o` : Name of the output directory. Specified name should not exist.

`-t` : Number of threads.

`--max-memory` : Maximum memory used for Trinity.

`--SS-lib-type` : Type of strand specific library (FR or RF).

## Docker-based Web Interface

A prebuilt Docker image allows running ViiR together with a small web page.
Build the container:

```bash
docker build -t viir-web .
```

Run it with your data directory mounted:

```bash
docker run -p 8080:8080 \
  -v /path/to/data:/data \
  -m 32g --cpus 8 \
  viir-web
```

Then open `http://localhost:8080` in your browser to upload a YAML
configuration or FASTQ list and start the pipeline. Results will be
written inside the mounted `/path/to/data` folder.

When processing large NGS datasets you may want to increase the memory
(`-m`) and CPU (`--cpus`) options to match the size of your data.
