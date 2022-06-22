"""Env Vars Service."""
import os

from meltano.core.config_service import ConfigService
from meltano.core.plugin.plugin_settings_service import PluginSettingsService
from meltano.core.project import Project
from meltano.core.project_settings_service import ProjectSettingsService


class EnvVarsService:
    """Service for retrieving and collating environment variables."""

    def __init__(
        self,
        project: Project,
        plugin,
        config_service: ConfigService | None = None,
        plugin_settings_service: PluginSettingsService | None = None,
    ):
        self.project = project
        self.plugin = plugin
        self.config_service = config_service or ConfigService(project=Project)

        if plugin_settings_service:
            self.plugin_settings_service = plugin_settings_service
        else:
            self.plugin_settings_service = PluginSettingsService(
                project=self.project, plugin=self.plugin
            )
        self.project_settings_service = (
            self.plugin_settings_service.project_settings_service
        )

    def get_terminal_env_vars(self):
        """Get terminal environment variables."""
        return os.environ

    def get_project_static_env_vars(self):
        """Get static, project level environment variables.

        e.g. MELTANO_ENVIRONMENT
        """
        return self.project.env

    def get_project_env_vars(self):
        """Get environment variables stored under the `env:` key in meltano.yml"""
        return self.config_service.env

    def get_dotenv_env_vars(self):
        """Get environment variables stored in the .env file."""
        return self.project.dotenv_env

    def get_environment_env_vars(self):
        """Get variables stored under the `env:` key of the active Meltano Environment."""
        if self.project.active_environment:
            return self.project.active_environment.env
        return {}

    def get_plugin_settings_env_vars(self):
        """Get plugin settings env vars.

        e.g. TAP_GITLAB_API_URL
        """
        return self.plugin_settings_service.as_env()

    def get_plugin_info_env(self):
        """Get plugin info as environment variables.

        e.g. MELTANO_EXTRACT_NAME
        """
        return self.plugin.info_env

    def get_plugin_env(self):
        """Get environment variables stored under the `env:` key of the plugin definition."""
        return self.plugin.env
