import importlib.util
import inspect
import threading
import logging
import os
from pathlib import Path
from typing import Dict, List, Type

from .interfaces import IA_DataAdapter, IA_FactorPlugin, IA_LensPlugin

logger = logging.getLogger(__name__)


class PluginManager:
    def __init__(self):
        self.lens_plugins: Dict[str, Type[IA_LensPlugin]] = {}
        self.factor_plugins: Dict[str, Type[IA_FactorPlugin]] = {}
        self.data_adapters: Dict[str, Type[IA_DataAdapter]] = {}

    def discover_plugins(self, plugin_dir: str):
        plugin_path = Path(plugin_dir).resolve()
        if not plugin_path.exists():
            return

        for root, _, files in os.walk(plugin_path):
            for file in files:
                if file.endswith('.py') and not file.startswith('__'):
                    file_path = os.path.join(root, file)
                    module_name = os.path.splitext(os.path.basename(file))[0]

                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        try:
                            spec.loader.exec_module(module)
                            self._register_from_module(module)
                        except Exception as e:
                            logger.warning("Failed to load plugin from %s: %s", file_path, e)

    def _register_from_module(self, module):
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if inspect.isabstract(obj):
                continue
            if issubclass(obj, IA_LensPlugin) and obj is not IA_LensPlugin:
                self.lens_plugins[name] = obj
            if issubclass(obj, IA_FactorPlugin) and obj is not IA_FactorPlugin:
                self.factor_plugins[name] = obj
            if issubclass(obj, IA_DataAdapter) and obj is not IA_DataAdapter:
                self.data_adapters[name] = obj

    # ------------------------------------------------------------------
    # Explicit registration (programmatic alternative to discover_plugins)
    # ------------------------------------------------------------------
    def register_lens(self, plugin_cls: Type[IA_LensPlugin]) -> None:
        """Register an IA_LensPlugin subclass by its class name."""
        if not (inspect.isclass(plugin_cls) and issubclass(plugin_cls, IA_LensPlugin)):
            raise TypeError(f"{plugin_cls!r} is not an IA_LensPlugin subclass")
        self.lens_plugins[plugin_cls.__name__] = plugin_cls

    def register_factor(self, plugin_cls: Type[IA_FactorPlugin]) -> None:
        """Register an IA_FactorPlugin subclass by its class name."""
        if not (inspect.isclass(plugin_cls) and issubclass(plugin_cls, IA_FactorPlugin)):
            raise TypeError(f"{plugin_cls!r} is not an IA_FactorPlugin subclass")
        self.factor_plugins[plugin_cls.__name__] = plugin_cls

    def register_adapter(self, plugin_cls: Type[IA_DataAdapter]) -> None:
        """Register an IA_DataAdapter subclass by its class name."""
        if not (inspect.isclass(plugin_cls) and issubclass(plugin_cls, IA_DataAdapter)):
            raise TypeError(f"{plugin_cls!r} is not an IA_DataAdapter subclass")
        self.data_adapters[plugin_cls.__name__] = plugin_cls

    # ------------------------------------------------------------------
    # Instantiation helpers (consumed by the valuation pipeline)
    # ------------------------------------------------------------------
    def create_lens_instances(self) -> Dict[str, IA_LensPlugin]:
        """Instantiate every registered lens plugin; skip (and log) failures."""
        return self._instantiate(self.lens_plugins)

    def create_factor_instances(self) -> Dict[str, IA_FactorPlugin]:
        """Instantiate every registered factor plugin; skip (and log) failures."""
        return self._instantiate(self.factor_plugins)

    @staticmethod
    def _instantiate(registry: Dict[str, type]) -> Dict[str, object]:
        instances: Dict[str, object] = {}
        for name, cls in registry.items():
            try:
                instances[name] = cls()
            except Exception as e:
                logger.warning("Could not instantiate plugin %s: %s", name, e)
        return instances

    def list_plugins(self) -> List[str]:
        """Names of every registered plugin (lenses, factors, adapters)."""
        return sorted(
            set(self.lens_plugins) | set(self.factor_plugins) | set(self.data_adapters)
        )


# ----------------------------------------------------------------------
# Process-wide default manager. The valuation pipeline consults this unless
# an explicit PluginManager is injected, so plugins registered here (by the
# UI, a script, or discover_plugins) genuinely affect valuation runs.
# ----------------------------------------------------------------------
_default_manager: PluginManager | None = None
_manager_lock = threading.Lock()


def get_plugin_manager() -> PluginManager:
    """Return the process-wide default PluginManager (created on first use).

    Note: no automatic discovery happens — callers opt in via
    ``get_plugin_manager().discover_plugins(path)`` or ``register_*``.
    """
    global _default_manager
    if _default_manager is None:
        with _manager_lock:
            if _default_manager is None:
                _default_manager = PluginManager()
    return _default_manager


def reset_plugin_manager() -> None:
    """Discard the process-wide default manager (primarily for tests)."""
    global _default_manager
    _default_manager = None
