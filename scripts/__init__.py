from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib.abc import Loader, MetaPathFinder
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from zipfile import ZipFile

if sys.version_info >= (3, 8):
    from importlib import metadata as importlib_metadata
else:
    import importlib_metadata

__all__ = [
    "__version__",
]

archive = Path(__file__).parent / "meltano.pyz"
package_name = archive.stem

with ZipFile(archive) as meltano_zipapp:
    shiv_environment: dict[str, str] = json.loads(
        meltano_zipapp.read("environment.json"),
    )

site_packages = (
    Path(shiv_environment["root"]).expanduser().resolve()
    / f"{archive.name}_{shiv_environment['build_id']}"
    / "site-packages"
)

if not site_packages.exists():
    # Run the zipapp to make Shiv unpack the site-packages directory
    subprocess.run(
        (sys.executable, str(archive), "--help"),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

__version__ = importlib_metadata.version(package_name)

# FIXME: This won't work as a way to let us test Meltano because it only
# provides imports for Meltano, but not for any of Meltano's dependencies.
# We could work around that with a custom importer that operates as a fallback
# for any import, trying to find it in the zipapp site-packages directory.
# Atlternatively, maybe trying to test the zipapp directly it not worth it,
# since it requires complex run-time changes. Or rather, it's worth it, but
# the code that enables it should be within the test suite, not the application.
class ShivAppModuleLoader(Loader, MetaPathFinder):
    def __init__(self, package_name: str, package_path: Path):
        self.package_name = package_name
        self.package_path = package_path

    def find_spec(self, fullname, path=None, target=None):  # noqa: ARG002
        if not fullname.startswith(self.package_name + "."):
            return None
        module_name = fullname.split(".")[-1]
        file_module_path = self.package_path / f"{module_name}.py"
        dir_module_path = self.package_path / module_name / "__init__.py"
        if file_module_path.exists():
            return spec_from_file_location(fullname, file_module_path)
        elif dir_module_path.exists():
            return spec_from_file_location(fullname, dir_module_path)
        raise ModuleNotFoundError(f"No module named '{fullname}'")

    def create_module(self, spec):
        return module_from_spec(spec)

    def exec_module(self, module):
        pass


sys.meta_path.append(ShivAppModuleLoader(package_name, site_packages / package_name))


def main():
    os.execv(sys.executable, (sys.executable, str(archive), *sys.argv[1:]))


if __name__ == "__main__":
    main()
