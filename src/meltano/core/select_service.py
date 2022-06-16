"""Select Service."""
import json
from typing import TYPE_CHECKING

from meltano.core.plugin import PluginType
from meltano.core.plugin.base import PluginRef
from meltano.core.plugin.error import PluginExecutionError
from meltano.core.plugin.plugin_settings_service import PluginSettingsService
from meltano.core.plugin.project_plugin import ProjectPlugin
from meltano.core.plugin.singer.catalog import ListSelectedExecutor
from meltano.core.plugin_invoker import invoker_factory
from meltano.core.project_plugins_service import ProjectPluginsService

from .project import Project

if TYPE_CHECKING:
    from typing import List


class SelectService:
    """Select Service."""

    def __init__(
        self,
        project: Project,
        extractor: str,
        plugins_service: ProjectPluginsService = None,
    ):
        """Instantiate SelectService instance.

        Args:
            project: Meltano Project instance.
            extractor: Extractor ProjectPlugin instance.
            plugins_service: (optional) ProjectPluginsService to use.
        """
        self.project = project
        self.plugins_service = plugins_service or ProjectPluginsService(project)
        self._extractor = self.plugins_service.find_plugin(
            extractor, PluginType.EXTRACTORS
        )

    @property
    def extractor(self) -> ProjectPlugin:
        """Retrieve extractor ProjectPlugin object.

        Returns:
            The extractor associated with this SelectService instance.
        """
        return self._extractor

    @property
    def current_select(self) -> List[str]:
        """Return current select filters.

        Returns:
            A list of current select filters.
        """
        plugin_settings_service = PluginSettingsService(
            self.project,
            self.extractor,
            plugins_service=self.plugins_service,
        )
        return plugin_settings_service.get("_select")

    async def load_catalog(self, session) -> dict:
        """Load the catalog.

        Args:
            session: Database session.

        Returns:
            A dictionary with catalog contents.
        """
        invoker = invoker_factory(
            self.project,
            self.extractor,
            plugins_service=self.plugins_service,
        )

        async with invoker.prepared(session):
            catalog_json = await invoker.dump("catalog")

        return json.loads(catalog_json)

    async def list_all(self, session) -> ListSelectedExecutor:
        """List all select.

        Args:
            session: Database session.

        Raises:
            PluginExecutionError: if catalog file not found.

        Returns:
            A ListSelectedExecutor instance.
        """
        try:
            catalog = await self.load_catalog(session)
        except FileNotFoundError as err:
            raise PluginExecutionError(
                "Could not find catalog. Verify that the tap supports discovery mode and advertises the `discover` capability as well as either `catalog` or `properties`"
            ) from err

        list_all = ListSelectedExecutor()
        list_all.visit(catalog)

        return list_all

    def update(
        self,
        entities_filter: str,
        attributes_filter: str,
        exclude: bool,
        remove: bool = False,
    ):
        """Update plugins' select patterns.

        Args:
            entities_filter: Entities filter string.
            attributes_filter: Attributes filter string.
            exclude: Whether to exclude matches.
            remove: Whether to remove resulting pattern.
        """
        plugin: PluginRef

        if self.project.active_environment is None:
            plugin = self.extractor
        else:
            plugin = self.project.active_environment.get_plugin_config(
                self.extractor.type, self.extractor.name
            )

        this_pattern = self._get_pattern_string(
            entities_filter, attributes_filter, exclude
        )
        patterns = plugin.extras.get("select", [])
        if remove:
            patterns.remove(this_pattern)
        else:
            patterns.append(this_pattern)
        plugin.extras["select"] = patterns

        if self.project.active_environment is None:
            self.plugins_service.update_plugin(plugin)
        else:
            self.plugins_service.update_environment_plugin(plugin)

    @staticmethod
    def _get_pattern_string(
        entities_filter: str, attributes_filter: str, exclude: bool
    ) -> str:
        """Return a select pattern in string form.

        Args:
            entities_filter: Entities filter string.
            attributes_filter: Attributes filter string.
            exclude: Whether to exclude matches (bool).

        Returns:
            A select pattern in string form.
        """
        exclude = "!" if exclude else ""
        return f"{exclude}{entities_filter}.{attributes_filter}"
