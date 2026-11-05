"""Car data for Need for Speed: Underground (PS2).

Source: https://nfs.fandom.com/wiki/Need_for_Speed:_Underground/Cars (retrieved 2026-11-04).
Ratings are the wiki's (acceleration, top speed, handling) stock values.
"""
from typing import NamedTuple, Optional, Tuple


class CarData(NamedTuple):
    name: str
    unlock_event: Optional[int]   # None = available from the start (starter car)
    price: int                    # Bank
    rating: Tuple[float, float, float]


CARS: Tuple[CarData, ...] = (
    # Starter cars
    CarData("Dodge Neon", None, 8500, (0.7, 1.7, 2.7)),
    CarData("Honda Civic Si", None, 10000, (0.5, 1.4, 3.2)),
    CarData("Mazda MX-5", None, 9500, (0.7, 1.4, 4.1)),
    CarData("Peugeot 206", None, 8500, (0.7, 1.1, 2.8)),
    CarData("Volkswagen Golf GTI", None, 8000, (0.3, 0.4, 2.3)),
    # Unlocked by Underground Mode events
    CarData("Mitsubishi Lancer ES", 4, 10500, (0.3, 0.7, 2.0)),
    CarData("Ford Focus ZX3", 8, 9000, (0.5, 1.1, 3.1)),
    CarData("Hyundai Tiburon GT V6", 17, 8500, (1.8, 3.6, 3.1)),
    CarData("Subaru Impreza 2.5 RS", 22, 10000, (0.8, 2.0, 2.7)),
    CarData("Nissan Sentra SE-R Spec V", 24, 20000, (0.9, 2.6, 2.2)),
    CarData("Nissan 240SX", 33, 18000, (0.9, 1.7, 2.6)),
    CarData("Toyota Celica GT-S", 41, 19500, (1.3, 2.6, 4.0)),
    CarData("Acura RSX Type-S", 46, 21000, (1.1, 3.3, 2.8)),
    CarData("Acura Integra Type-R", 53, 19000, (1.4, 0.7, 3.3)),
    CarData("Mitsubishi Eclipse GSX", 58, 20500, (1.0, 3.6, 3.3)),
    CarData("Toyota Supra", 64, 22500, (1.0, 3.9, 1.9)),
    CarData("Honda S2000", 69, 28000, (0.8, 2.0, 2.6)),
    CarData("Mazda RX-7", 73, 30000, (2.3, 3.9, 3.1)),
    CarData("Nissan 350Z", 75, 35000, (1.5, 3.6, 1.9)),
    CarData("Nissan Skyline GT-R (R34)", 79, 80000, (2.6, 5.8, 3.2)),
)

STARTER_CARS = tuple(c.name for c in CARS if c.unlock_event is None)
UNLOCKABLE_CARS = tuple(c for c in CARS if c.unlock_event is not None)
