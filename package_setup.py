#!/usr/bin/env python3

from setuptools import setup, find_packages

setup(
    name="viir",
    version="0.0.0",
    packages=find_packages(include=["viir_core", "viir_core.*"]),
    entry_points={
        "console_scripts": [
            "viir=viir_core.cli:main",
        ]
    },
)
