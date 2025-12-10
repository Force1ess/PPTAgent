from deeppresenter.utils.typings import InputRequest

from .agent import Agent


class Research(Agent):
    async def loop(self, req: InputRequest):
        while True:
            agent_message = await self.action(
                prompt=req.deepresearch_prompt,
                attachments=req.attachments,
            )
            yield agent_message
            outcome = await self.execute(agent_message.tool_calls, limit_len=True)
            if isinstance(outcome, list):
                for item in outcome:
                    yield item
            else:
                yield outcome
                break
