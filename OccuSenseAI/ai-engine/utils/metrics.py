from typing import Dict
import time

class MetricsStore:
    def __init__(self):
        self.counters: Dict[str, int] = {}
        self.histograms: Dict[str, list] = {}
        
    def inc(self, metric: str, amount: int = 1):
        self.counters[metric] = self.counters.get(metric, 0) + amount
        
    def observe(self, metric: str, value: float):
        if metric not in self.histograms:
            self.histograms[metric] = []
        self.histograms[metric].append(value)
        if len(self.histograms[metric]) > 1000:
            self.histograms[metric] = self.histograms[metric][-1000:]

metrics = MetricsStore()
