"""Minimal IA_LensPlugin stub used by the plugin-discovery unit test.

For a realistic, pipeline-influencing example see ``fcf_yield_lens.py`` in
this directory — it returns the dict shape the valuation pipeline's plugin
bridge converts into a LensResult.
"""

from typing import Any, Dict

from iam.plugins.interfaces import IA_LensPlugin


class ExampleLens(IA_LensPlugin):
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "analyzed", "input": data}
