import sys
import os
import argparse
import yaml
from datetime import datetime
from viir.__init__ import __version__



class Params(object):

    def __init__(self, program_name):
        self.program_name = program_name

    def set_options(self):
        parser = self.viir_options()

        # Add new argument for YAML config file
        parser.add_argument('--config', type=str, help='Path to a YAML configuration file.', default=None)

            # Clean sys.argv: remove script path if present as argument
        cleaned_argv = [arg for arg in sys.argv[1:] if not os.path.exists(arg) or arg.endswith('.yaml')]

        if '--config' in cleaned_argv:
            # First parse only --config to find the file path
            index = cleaned_argv.index('--config')
            try:
                config_path = cleaned_argv[index + 1]
            except IndexError:
                raise ValueError("Missing path after --config")

            # Load config from YAML
            with open(config_path, 'r') as f:
                config_dict = yaml.safe_load(f)

            if 'out' not in config_dict or not config_dict['out']:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                config_dict['out'] = f"output/run_{timestamp}"

            # After loading config_dict
            valid_keys = {a.dest for a in parser._actions if a.dest != 'help'}
            unknown_keys = set(config_dict.keys()) - valid_keys
            if unknown_keys:
                raise ValueError(f"Unknown config keys in YAML: {unknown_keys}")


            # Turn YAML config into args list
            yaml_arg_list = []
            for key, value in config_dict.items():
                key = f'--{key}'
                if isinstance(value, bool):
                    if value:
                        yaml_arg_list.append(key)
                else:
                    yaml_arg_list.extend([key, str(value)])

            # Combine YAML + CLI overrides
            extra_args = [arg for i, arg in enumerate(cleaned_argv) if i < index or i > index + 1]
            args = parser.parse_args(yaml_arg_list + extra_args)

        else:
            args = parser.parse_args() if len(cleaned_argv) > 1 else parser.parse_args(['-h'])

        return args



    def viir_options(self):
        parser = argparse.ArgumentParser(description='ViiR version {}'.format(__version__),
                                         formatter_class=argparse.RawTextHelpFormatter)
        parser.usage = 'viir -l <FASTQ_LIST> -o <OUT_DIR> [-t <INT>]'

        # set options
        parser.add_argument('-l',
                            '--fastq-list',
                            action='store',
                            required=('--config' not in sys.argv),
                            type=str,
                            help='Fastq list.',
                            metavar='')

        parser.add_argument('-o',
                            '--out',
                            action='store',
                            required=('--config' not in sys.argv),
                            type=str,
                            help=('Output directory. Specified name must not\n'
                                  'exist.'),
                            metavar='')

        parser.add_argument('-t',
                            '--threads',
                            action='store',
                            default=16,
                            type=int,
                            help='Number of threads. [16]',
                            metavar='')

        parser.add_argument('-a',
                            '--adapter',
                            action='store',
                            default="Default_adapter",
                            type=str,
                            help=("FASTA of adapter sequences. If you don't\n"
                                  'specify this option, the defaul adapter set\n'
                                  'will be used.'),
                            metavar='')

        parser.add_argument('--pfam',
                            action='store',
                            default="Default_list",
                            type=str,
                            help=("List of Pfam IDs. If you don't specify\n"
                                  'this option, the defaul list will be used.'),
                            metavar='')

        parser.add_argument('--SS-lib-type',
                            action='store',
                            default='No',
                            type=str,
                            help=('Type of strand specific library (No/FR/RF). [No]'),
                            metavar='')

        parser.add_argument('--blastndb',
                            action='store',
                            default='Default_db',
                            type=str,
                            help=('FASTA to annotate your trinity assembly.'),
                            metavar='')

        parser.add_argument('--pvalue',
                            action='store',
                            default=0.01,
                            type=float,
                            help='Threshold of pvalue in DESeq2. [0.01]',
                            metavar='')

        parser.add_argument('--max-memory',
                            action='store',
                            default='32G',
                            type=str,
                            help=('Max memory used in Trinity. [32G]'),
                            metavar='')

        # set version
        parser.add_argument('-v',
                            '--version',
                            action='version',
                            version='%(prog)s {}'.format(__version__))

        return parser

    