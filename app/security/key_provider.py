from __future__ import annotations

from abc import ABC, abstractmethod


class KeyProvider(ABC):
    @abstractmethod
    def get_master_key(self) -> bytes:
        raise NotImplementedError
