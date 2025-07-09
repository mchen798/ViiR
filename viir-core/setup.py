#!/usr/bin/env python3

from distutils.core import setup
from viir.__init__ import __version__

setup(name='viir',
      version='{}'.format(__version__),
      description='ViiR : Virus Identification Independent of Reference sequences',
      author='Yu Sugihara',
      author_email='sugihara.yu.85s@kyoto-u.jp',
      url='https://github.com/YuSugihara/ViiR',
      license='GPL',
      packages=['viir'],
      entry_points={'console_scripts': [
            'viir = viir.viir:main',
            ]
        }
    )
