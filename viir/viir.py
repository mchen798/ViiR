#!/usr/bin/env python3

from viir.params import Params

import os
import sys
import yaml
import shutil
import subprocess as sbp

def make_path_absolute(path, base_dir):
    return path if os.path.isabs(path) else os.path.abspath(os.path.join(base_dir, path))

def find_project_root(filename="run_viir.sh"):
    current = os.path.dirname(__file__)
    while current != '/' and not os.path.exists(os.path.join(current, filename)):
        current = os.path.dirname(current)
    return current

class ViiR(object):

    def __init__(self, args):
        self.args = args

    def normalize_paths(self):
    config_path = getattr(self.args, "config", None)
    base_dir = os.path.dirname(config_path) if config_path else os.getcwd()

    self.args.fastq_list = make_path_absolute(self.args.fastq_list, base_dir)
    if self.args.adapter != "Default_adapter":
        self.args.adapter = make_path_absolute(self.args.adapter, base_dir)
    if self.args.pfam != "Default_list":
        self.args.pfam = make_path_absolute(self.args.pfam, base_dir)
    if self.args.blastndb != "Default_db":
        self.args.blastndb = make_path_absolute(self.args.blastndb, base_dir)

    def prepare_output_directory(self):
        os.makedirs(self.args.out, exist_ok=True)

        config_dump_path = os.path.join(self.args.out, 'config_used.yaml')
        with open(config_dump_path, 'w') as f:
            yaml.safe_dump(vars(self.args), f, sort_keys=False)

    def fetch_run_script(self):
        run_sh_name = "run_viir.sh"
        run_sh_target = os.path.join(self.args.out, run_sh_name)

        for search_path in [".", "..", find_project_root()]:
            if not search_path:
                continue
            candidate = os.path.abspath(os.path.join(search_path, run_sh_name))
            if os.path.isfile(candidate):
                shutil.copy(candidate, run_sh_target)
                print(f"[INFO] Copied {run_sh_name} from {candidate}")
                return run_sh_target

        print(f"[INFO] Downloading {run_sh_name} from GitHub...")
        url = f"https://raw.githubusercontent.com/YuSugihara/ViiR/master/{run_sh_name}"
        cmd = f"wget {url} -O {run_sh_target}"
        sbp.run(cmd, stdout=sys.stdout, stderr=sys.stderr, shell=True, check=True)
        return run_sh_target

    def run_pipeline(self, script_path):
        cmd = [
            'bash', '-e', script_path, 
            self.args.out, self.args.fastq_list, self.args.pvalue,
            self.args.pfam, self.args.threads, self.args.max_memory,
            self.args.SS_lib_type, self.args.adapter, self.args.blastndb
        ]
        print(cmd, file=sys.stderr, flush=True)
        sbp.run(cmd, stdout=sys.stdout, stderr=sys.stderr, shell=True, check=True)

    def run(self):
        self.prepare_output_directory()
        self.normalize_paths()
        run_sh_path = self.fetch_run_script()
        self.run_pipeline(run_sh_path)



def main():
    # Get parameters via argparse or YAML
    args = Params('viir').set_options()

    # Run main pipeline
    ViiR(args).run()

if __name__ == '__main__':
    main()
