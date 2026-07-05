from abc import ABC, abstractmethod
from typing import Any, Dict

class IA_LensPlugin(ABC):
    @abstractmethod
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pass

class IA_FactorPlugin(ABC):
    @abstractmethod
    def calculate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pass

class IA_DataAdapter(ABC):
    @abstractmethod
    def fetch(self, source: str, **kwargs) -> Any:
        pass
