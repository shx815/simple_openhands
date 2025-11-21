from dataclasses import dataclass

from simple_openhands.events.event import Event


@dataclass
class Observation(Event):
    content: str
