from dataclasses import dataclass

from simple_openhands.events.event import Event
from simple_openhands.events.action import Action
from simple_openhands.events.observation import Observation
from . import agentskills
from ..requirement import Plugin, PluginRequirement
from .agentskills import *


@dataclass
class AgentSkillsRequirement(PluginRequirement):
    name: str = 'agent_skills'
    documentation: str = agentskills.DOCUMENTATION


class AgentSkillsPlugin(Plugin):
    name: str = 'agent_skills'

    async def initialize(self, username: str) -> None:
        """Initialize the plugin."""
        pass

    async def run(self, action: Action) -> Observation:
        """Run the plugin for a given action."""
        raise NotImplementedError('AgentSkillsPlugin does not support run method')
