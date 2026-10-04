class ProvenanceTracker:
    def __init__(self):
        self.lineage: dict[str, list[str]] = {}

    def add_source(self, metric_id: str, source_tag: str):
        if metric_id not in self.lineage:
            self.lineage[metric_id] = []
        if source_tag not in self.lineage[metric_id]:
            self.lineage[metric_id].append(source_tag)

    def get_sources(self, metric_id: str) -> list[str]:
        return self.lineage.get(metric_id, [])
