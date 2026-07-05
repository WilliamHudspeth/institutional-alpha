import pytest
from pathlib import Path
from iam.plugins.manager import PluginManager
from iam.plugins.interfaces import IA_LensPlugin

def test_discover_plugins():
    manager = PluginManager()
    
    # Path to the examples directory relative to the project root
    base_dir = Path(__file__).resolve().parent.parent.parent
    examples_dir = base_dir / "src" / "iam" / "plugins" / "examples"
    
    manager.discover_plugins(str(examples_dir))
    
    assert "ExampleLens" in manager.lens_plugins
    plugin_class = manager.lens_plugins["ExampleLens"]
    assert issubclass(plugin_class, IA_LensPlugin)
    
    # Test instantiation and method call
    plugin_instance = plugin_class()
    result = plugin_instance.analyze({"test": 123})
    assert result == {"status": "analyzed", "input": {"test": 123}}
