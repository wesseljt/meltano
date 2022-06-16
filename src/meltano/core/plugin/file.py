"""File Plugin."""
import click

from meltano.core.behavior.hookable import hook
from meltano.core.plugin import BasePlugin, PluginType
from meltano.core.plugin.plugin_settings_service import PluginSettingsService
from meltano.core.plugin.project_plugin import ProjectPlugin
from meltano.core.plugin_install_service import (
    PluginInstallReason,
    PluginInstallService,
)
from meltano.core.setting_definition import SettingDefinition, SettingKind
from meltano.core.venv_service import VirtualEnv


class FilePlugin(BasePlugin):
    """File Plugin."""

    __plugin_type__ = PluginType.FILES

    EXTRA_SETTINGS = [
        SettingDefinition(
            name="_update", kind=SettingKind.OBJECT, aliases=["update"], value={}
        )
    ]

    def is_invokable(self):
        """Plugin invokable status.

        Returns:
            False
        """
        return False

    def should_add_to_file(self):
        """Determine if plugin should add to (update) files.

        Returns:
            True if updates are required.
        """
        return bool(self.extras.get("update", []))

    def file_contents(self, project):
        """Get file contents.

        Args:
            project: Meltano Project instance.

        Returns:
            A dictionary of form {path: content} with current project files contents.
        """
        venv = VirtualEnv(project.plugin_dir(self, "venv"))
        bundle_dir = venv.site_packages_dir.joinpath("bundle")

        return {
            path.relative_to(bundle_dir): path.read_text()
            for path in bundle_dir.glob("**/*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path != bundle_dir.joinpath("__init__.py")
        }

    def update_file_header(self, relative_path):
        """File header content.

        Args:
            relative_path: Path to insert into header content.

        Returns:
            A list of strings representing line of header comments.
        """
        return "\n".join(
            [
                f"# This file is managed by the '{self.name}' {self.type.descriptor} and updated automatically when `meltano upgrade` is run.",
                f"# To prevent any manual changes from being overwritten, remove the {self.type.descriptor} from `meltano.yml` or disable automatic updates:",
                f"#     meltano config --plugin-type={self.type} {self.name} set _update {relative_path} false",
            ]
        )

    def project_file_contents(self, project, paths_to_update):
        """Get project file contents.

        Args:
            project: Meltano Project instance.
            paths_to_update: Paths to add header content to.

        Returns:
            A dictionary of form {path: content}.
        """

        def with_update_header(content, relative_path):
            if str(relative_path) in paths_to_update:
                content = "\n\n".join([self.update_file_header(relative_path), content])

            return content

        return {
            relative_path: with_update_header(content, relative_path)
            for relative_path, content in self.file_contents(project).items()
        }

    def write_file(self, project, relative_path, content):
        """Write file.

        Args:
            project: Meltano Project instance.
            relative_path: Path to write to.
            content: Content to write to path.

        Returns:
            Boolean, true if write was successful.
        """
        project_path = project.root_dir(relative_path)
        if project_path.exists() and project_path.read_text() == content:
            return False

        project_path.parent.mkdir(parents=True, exist_ok=True)
        project_path.write_text(content)

        return True

    def write_files(self, project, files_content):
        """Write files.

        Args:
            project: Meltano Project instance.
            files_content: A dictionary of form {path: content} to write.

        Returns:
            List of paths of written files.
        """
        return [
            relative_path
            for relative_path, content in files_content.items()
            if self.write_file(project, relative_path, content)
        ]

    def files_to_create(self, project, paths_to_update):
        """Determine files to create.

        Args:
            project: Meltano Project instance.
            paths_to_update: Filter to specified paths.

        Returns:
            A dictionary of form {path: content} to write.
        """

        def rename_if_exists(relative_path):
            if not project.root_dir(relative_path).exists():
                return relative_path

            click.echo(f"File {relative_path} already exists, keeping both versions")
            return relative_path.with_name(
                f"{relative_path.stem} ({self.name}){relative_path.suffix}"
            )

        return {
            rename_if_exists(relative_path): content
            for relative_path, content in self.project_file_contents(
                project, paths_to_update
            ).items()
        }

    def files_to_update(self, project, paths_to_update):
        """Determine files to update.

        Args:
            project: Meltano Project instance.
            paths_to_update: Filter to specified paths.

        Returns:
            A dictionary of form {path: content} to write.
        """
        return {
            relative_path: content
            for relative_path, content in self.project_file_contents(
                project, paths_to_update
            ).items()
            if str(relative_path) in paths_to_update
        }

    def create_files(self, project, paths_to_update=None):
        """Create files.

        Args:
            project: Meltano Project instance.
            paths_to_update: (optional) paths to update.

        Returns:
            List of paths of written files.
        """
        return self.write_files(
            project, self.files_to_create(project, paths_to_update or [])
        )

    def update_files(self, project, paths_to_update=None):
        """Update files.

        Args:
            project: Meltano Project instance.
            paths_to_update: (optional) paths to update.

        Returns:
            List of paths of written files.
        """
        return self.write_files(
            project, self.files_to_update(project, paths_to_update or [])
        )

    @hook("after_install")
    async def after_install(
        self,
        installer: PluginInstallService,
        plugin: ProjectPlugin,
        reason: PluginInstallReason,
    ):
        """Trigger after install tasks.

        Args:
            installer: Plugin installer.
            plugin: The plugin to install.
            reason: Reason of install.
        """
        project = installer.project
        plugins_service = installer.plugins_service

        plugin_settings_service = PluginSettingsService(
            project, plugin, plugins_service=plugins_service
        )
        update_config = plugin_settings_service.get("_update")
        paths_to_update = [pth for pth, to_update in update_config.items() if to_update]

        if reason is PluginInstallReason.ADD:
            click.echo(f"Adding '{plugin.name}' files to project...")

            for create_path in self.create_files(project, paths_to_update):
                click.echo(f"Created {create_path}")
        elif reason is PluginInstallReason.UPGRADE:
            click.echo(f"Updating '{plugin.name}' files in project...")

            updated_paths = self.update_files(project, paths_to_update)
            if not updated_paths:
                click.echo("Nothing to update")
                return

            for update_path in updated_paths:
                click.echo(f"Updated {update_path}")
        else:
            click.echo(
                f"Run `meltano upgrade files` to update your project's '{plugin.name}' files."
            )
