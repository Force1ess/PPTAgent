from deeppresenter.agents.agent import Agent
from deeppresenter.utils.typings import InputRequest


class PPTAgent(Agent):
    async def loop(self, req: InputRequest, markdown_file: str):
        while True:
            agent_message = await self.action(
                markdown_file=markdown_file, prompt=req.pptagent_prompt
            )
            yield agent_message
            outcome = await self.execute(agent_message.tool_calls)
            if isinstance(outcome, list):
                for item in outcome:
                    yield item
            else:
                yield outcome
                break
