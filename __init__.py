"""Reelwright — MiniMax H3 timeline editor for ComfyUI."""

from .reelwright import routes  # noqa: F401  registers the /reelwright HTTP routes
from .reelwright.node import ReelwrightExtension

WEB_DIRECTORY = "./web"


async def comfy_entrypoint() -> ReelwrightExtension:
    return ReelwrightExtension()


__all__ = ["WEB_DIRECTORY", "comfy_entrypoint"]
