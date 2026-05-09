"""Signal interface."""
from __future__ import annotations
from abc import ABC, abstractmethod
import pandas as pd


class Signal(ABC):
    name: str

    @abstractmethod
    def compute(self, prices: pd.DataFrame) -> pd.DataFrame:
        ...
