"""
Base class for all walkscore metrics
"""

from abc import ABC, abstractmethod

class BaseMetric(ABC):

    def __init__(self, name, weight=1.0):
        self.name = name
        self.weight = weight

    @abstractmethod
    def calculate(self, grid_gdf, data):
        #Calculate metric for each hexagon in the grid
        pass