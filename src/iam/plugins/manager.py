import importlib.util
import inspect
import os
from typing import Dict, Type
from pathlib import Path

from .interfaces import IA_LensPlugin, IA_FactorPlugin, IA_DataAdapter

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
                            print(f"Failed to load plugin from {file_path}: {e}")

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
