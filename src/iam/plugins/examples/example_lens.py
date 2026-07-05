from typing import Dict, Any
from iam.plugins.interfaces import IA_LensPlugin

class ExampleLens(IA_LensPlugin):
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "analyzed", "input": data}
