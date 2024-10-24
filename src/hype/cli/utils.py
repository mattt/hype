import importlib.util
import os
import sys
from typing import Any

import click

from hype import Function


def import_module_from_path(path: str) -> Any:
    """Import a Python module from a file path."""
    module_name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise click.ClickException(f"Could not load module from {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def find_functions(module: Any) -> list:
    """Find all Function instances in a module."""
    functions = []
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, Function):
            functions.append(attr)
    return functions


def get_reload_dirs(module_path: str) -> list[str]:
    """Get directories to watch for reload."""
    module_dir = os.path.dirname(os.path.abspath(module_path))
    project_root = os.path.abspath(os.getcwd())
    dirs = [module_dir, project_root]
    src_dir = os.path.join(project_root, "src")
    if os.path.exists(src_dir):
        dirs.append(src_dir)
    return list(dict.fromkeys(dirs))
