import os
import asyncio
import logging
import sys
from io import StringIO

from . import Runner, RunnerError
from meltano.core.error import SubprocessError
from meltano.core.project import Project
from meltano.core.plugin import PluginType
from meltano.core.plugin_invoker import PluginInvoker
from meltano.core.db import project_engine
from meltano.core.logging import capture_subprocess_output
from meltano.core.elt_context import ELTContext


class DbtRunner(Runner):
    def __init__(self, elt_context: ELTContext):
        self.context = elt_context

    @property
    def project(self):
        return self.context.project

    @property
    def plugin_context(self):
        return self.context.transformer

    async def invoke(self, dbt: PluginInvoker, cmd, *args, log=None, **kwargs):
        log = log or sys.stderr

        try:
            handle = await dbt.invoke_async(
                cmd,
                *args,
                **kwargs,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as err:
            raise RunnerError(f"Cannot start dbt: {err}") from err

        await asyncio.wait(
            [
                capture_subprocess_output(handle.stdout, log),
                capture_subprocess_output(handle.stderr, log),
                handle.wait(),
            ],
            return_when=asyncio.ALL_COMPLETED,
        )

        exitcode = handle.returncode
        if exitcode:
            raise RunnerError(
                f"`dbt {cmd}` failed", {PluginType.TRANSFORMERS: exitcode}
            )

    async def run(self, log=None):
        dbt = self.context.transformer_invoker()

        with dbt.prepared(self.context.session):
            await self.invoke(dbt, "clean", log=log)
            await self.invoke(dbt, "deps", log=log)

            cmd = "compile" if self.context.dry_run else "run"
            await self.invoke(
                dbt,
                cmd,
                "--models",
                str(self.plugin_context.get_config("models")),
                log=log,
            )
