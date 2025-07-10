"""Minimal Typer stub using Click."""
from __future__ import annotations

import inspect
import click


class Option:
    def __init__(self, default=..., help: str | None = None):
        self.default = default
        self.help = help


class Argument:
    def __init__(self, default=..., help: str | None = None):
        self.default = default
        self.help = help


class Typer:
    def __init__(self, help: str | None = None):
        self._group = click.Group(help=help)

    def command(self, name: str | None = None):
        def decorator(func):
            cmd_name = name or func.__name__
            sig = inspect.signature(func)
            params = []
            for p in sig.parameters.values():
                default = p.default
                if isinstance(default, Option):
                    params.append(
                        click.Option(
                            [f"--{p.name.replace('_','-')}"],
                            default=default.default,
                            show_default=True,
                            help=default.help,
                        )
                    )
                else:
                    params.append(click.Argument([p.name]))
            def callback(*args, **kwargs):
                return func(*args, **kwargs)
            cmd = click.Command(cmd_name, params=params, callback=callback, help=func.__doc__)
            self._group.add_command(cmd)
            return func
        return decorator

    def __call__(self, *args, **kwargs):
        self._group(*args, **kwargs)

