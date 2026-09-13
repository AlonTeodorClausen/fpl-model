from dataclasses import dataclass

@dataclass
class XPComponents:
    appearance: float = 0.0
    goals: float = 0.0
    assists: float = 0.0
    clean_sheet: float = 0.0
    saves: float = 0.0
    defcon: float = 0.0
    bonus: float = 0.0
    cards: float = 0.0
    conceded: float = 0.0

    @property
    def total(self) -> float:
        return sum(self.__dict__.values())
