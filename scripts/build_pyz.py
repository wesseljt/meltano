#!/usr/bin/env python

from __future__ import annotations

import os
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import tomlkit

os.chdir(Path(__file__).parent.parent)  # CD to repository root

with open("pyproject.toml") as f:
    base_pyproject_toml = tomlkit.load(f)

poetry_config = base_pyproject_toml["tool"]["poetry"]
package_name: str = poetry_config["name"]
package_version: str = poetry_config["version"]

requirements = subprocess.run(
    (
        "poetry",
        "export",
        # TODO: read `pyproject.toml` and extract extras
        "--extras=azure",
        "--extras=gcs",
        "--extras=mssql",
        "--extras=s3",
    ),
    text=True,
    stdout=subprocess.PIPE,
    check=True,
).stdout

subprocess.run(
    ("pip", "wheel", "--no-deps", "--wheel-dir=dist", "."),
    check=True,
)

wheel = Path(f"dist/{package_name}-{package_version}-py3-none-any.whl").resolve()

with open(wheel, "rb") as f:
    wheel_sha256_hash = sha256(f.read()).hexdigest()

requirements += f"file://{wheel} --hash=sha256:{wheel_sha256_hash}\n"

with open("dist/requirements.txt", "w") as f:
    f.write(requirements)

package_dir = Path(f"dist/{package_name}").resolve()
package_dir.mkdir(exist_ok=True)

with open(package_dir / "pyproject.toml", "w") as f:
    tomlkit.dump(
        {
            "project": {
                "name": package_name,
                "version": package_version,
                "license": {"file": "LICENSE"},
                "readme": "README.md",
                "description": poetry_config["description"],
                "classifiers": poetry_config["classifiers"],
                "urls": {
                    "documentation": poetry_config["documentation"],
                    "homepage": poetry_config["homepage"],
                    **poetry_config["urls"],
                },
                "requires-python": poetry_config["dependencies"]["python"],
                "scripts": {package_name: f"{package_name}:main"},
                "dependencies": [],  # No dependencies!
            },
            "build-system": {
                "requires": ["flit-core==3.8.0", "wheel"],
                "build-backend": "flit_core.buildapi",
            },
        },
        f,
    )

root_module_dir = package_dir / package_name.replace("-", "_").replace(".", "_")
root_module_dir.mkdir(exist_ok=True)

shutil.copy("scripts/__init__.py", root_module_dir / "__init__.py")

main_file_content = """
from . import main

if __name__ == "__main__":
    main()
"""
with open(root_module_dir / "__main__.py", "w") as f:
    f.write(main_file_content)

# FIXME: Using a zipapp break all __main__.py files within the embedded
# package. For Meltano that means that `python -m meltano.cli` won't work.

shutil.copy("README.md", package_dir / "README.md")
shutil.copy("LICENSE", package_dir / "LICENSE")

subprocess.run(
    (
        "shiv",
        "-c",
        package_name,
        "-o",
        str(root_module_dir / f"{package_name}.pyz"),
        "--extend-pythonpath",
        "--reproducible",
        "--compressed",
        "--root",
        f"~/.{package_name}",
        "--requirement=dist/requirements.txt",
    ),
    check=True,
)

# Remove the wheel and requirements.txt; Shiv used them to create the pyz file.
os.remove("dist/requirements.txt")
os.remove(wheel)

subprocess.run(
    ("python", "-m", "build", "--wheel", "--outdir=dist", str(package_dir)),
    check=True,
)

shutil.rmtree(package_dir)

# TODO: turn this script into a local build backend. This not only makes it
# possible to distribute an sdist that'll exhibit the same behaviour, but also
# it'll also let us install tomlkit and shiv as build backend dependencies.
# As before, Poetry will be needed to build the sdist, and `pip wheel .` or
# `python -m build --wheel .` can be used to build the wheel.
