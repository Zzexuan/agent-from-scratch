from abc import ABC, abstractmethod


class BaseMemory(ABC):
    @abstractmethod
    def load_context(self, query=None, k=5):
        ...

    @abstractmethod
    def save(self, messages):
        ...
