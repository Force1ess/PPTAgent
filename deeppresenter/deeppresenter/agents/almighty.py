import asyncio
from pathlib import Path

from deeppresenter.agents.agent import Agent
from deeppresenter.utils.typings import InputRequest


class Almighty(Agent):
    async def loop(self, request: InputRequest):
        while True:
            agent_message = await self.action(prompt=request.deepresearch_prompt)
            yield agent_message
            outcome = await self.execute(self.chat_history[-1].tool_calls)
            if isinstance(outcome, list):
                for item in outcome:
                    yield item
            else:
                break

        yield outcome
