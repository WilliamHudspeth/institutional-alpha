from abc import ABC, abstractmethod
from typing import Any


class IA_LensPlugin(ABC):
    @abstractmethod
    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        pass


class IA_FactorPlugin(ABC):
    @abstractmethod
    def calculate(self, data: dict[str, Any]) -> dict[str, Any]:
        pass


class IA_DataAdapter(ABC):
    @abstractmethod
    def fetch(self, source: str, **kwargs) -> Any:
        pass
