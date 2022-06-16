"""Transform Add Service."""

import os
from pathlib import Path
from typing import Optional

import yaml

from .plugin.plugin_settings_service import PluginSettingsService
from .plugin.project_plugin import ProjectPlugin
from .project import Project
from .project_plugins_service import ProjectPluginsService


class TransformAddService:
    """Transform Add Service."""

    def __init__(self, project: Project):
        """Instantiate TransformAddService instance.

        Args:
            project: Meltano Project instance.
        """
        self.project = project

        self.plugins_service = ProjectPluginsService(project)

        dbt_plugin = self.plugins_service.get_transformer()

        settings_service = PluginSettingsService(
            project, dbt_plugin, plugins_service=self.plugins_service
        )
        dbt_project_dir = settings_service.get("project_dir")
        dbt_project_path = Path(dbt_project_dir)

        self.packages_file = dbt_project_path.joinpath("packages.yml")
        self.dbt_project_file = dbt_project_path.joinpath("dbt_project.yml")

    def add_to_packages(self, plugin: ProjectPlugin):
        """Add package to packages file.

        Args:
            plugin: dbt plugin to use.

        Raises:
            ValueError: if missing pip url for transform plugin.
        """
        if not os.path.exists(self.packages_file):
            open(self.packages_file, "a").close()  # noqa: WPS515

        package_yaml = yaml.safe_load(self.packages_file.open()) or {"packages": []}

        git_repo = plugin.pip_url
        if not git_repo:
            raise ValueError(f"Missing pip_url for transform plugin '{plugin.name}'")

        revision: Optional[str] = None
        if len(git_repo.split("@")) == 2:
            git_repo, revision = git_repo.split("@")
        for package in package_yaml["packages"]:
            same_ref = (
                package.get("git", "") == git_repo
                and package.get("revision", None) == revision
            )
            if same_ref:
                return

        package_ref = {"git": git_repo}
        if revision:
            package_ref["revision"] = revision
        package_yaml["packages"].append(package_ref)

        with open(self.packages_file, "w") as pkg_f:
            pkg_f.write(
                yaml.dump(package_yaml, default_flow_style=False, sort_keys=False)
            )

    def update_dbt_project(self, plugin: ProjectPlugin):
        """Set transform package variables in `dbt_project.yml`.

        If not already present, the package name will also be added under dbt 'models'.

        Args:
            plugin: dbt plugin to use.
        """
        settings_service = PluginSettingsService(
            self.project, plugin, plugins_service=self.plugins_service
        )

        package_name = settings_service.get("_package_name")
        package_vars = settings_service.get("_vars")

        dbt_project_yaml = yaml.safe_load(self.dbt_project_file.open())

        model_def = {}

        if package_vars:
            # Add variables scoped to the plugin's package name
            config_version = dbt_project_yaml.get("config-version", 1)
            if config_version == 1:
                model_def["vars"] = package_vars
            else:
                project_vars = dbt_project_yaml.get("vars", {})
                project_vars[package_name] = package_vars
                dbt_project_yaml["vars"] = project_vars

        # Add the package's definition to the list of models:
        dbt_project_yaml["models"][package_name] = model_def

        with open(self.dbt_project_file, "w") as dbt_pf:
            dbt_pf.write(
                yaml.dump(dbt_project_yaml, default_flow_style=False, sort_keys=False)
            )
