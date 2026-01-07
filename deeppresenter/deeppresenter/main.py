import json
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Literal

from deeppresenter.agents.design import Design
from deeppresenter.agents.env import AgentEnv
from deeppresenter.agents.pptagent import PPTAgent
from deeppresenter.agents.research import Research
from deeppresenter.utils import DeepPresenterConfig
from deeppresenter.utils.config import GLOBAL_CONFIG
from deeppresenter.utils.constants import WORKSPACE_BASE
from deeppresenter.utils.log import debug, error, info, set_logger, timer
from deeppresenter.utils.typings import ChatMessage, ConvertType, InputRequest, Role
from deeppresenter.utils.webview import convert_html_to_pptx


class AgentLoop:
    def __init__(
        self,
        config: DeepPresenterConfig = GLOBAL_CONFIG,
        session_id: str | None = None,
        workspace: Path = None,
        language: Literal["zh", "en"] = "zh",
    ):
        self.config = config
        self.language = language
        if session_id is None:
            session_id = str(uuid.uuid4())[:8]
        self.workspace = workspace or WORKSPACE_BASE / session_id
        self.intermediate_output = {}
        set_logger(
            f"deeppresenter-loop-{self.workspace.stem}",
            self.workspace / "history" / "deeppresenter-loop.log",
        )
        debug(f"Initialized AgentLoop with workspace={self.workspace}")
        debug(f"Config: {self.config.model_dump_json(indent=2)}")

    @timer("DeepPresenter Loop")
    async def run(
        self,
        request: InputRequest,
        hci_enable: bool = False,
    ) -> AsyncGenerator[str | ChatMessage, None]:
        with open(self.workspace / "input_request.json", "w") as f:
            json.dump(request.model_dump(), f, ensure_ascii=False, indent=2)
        async with AgentEnv(self.workspace, hci_enable) as agent_env:
            self.agent_env = agent_env
            request.copy_to_workspace(self.workspace)
            hello_message = f"DeepPresenter running in {self.workspace}, with {len(request.attachments)} attachments, prompt={request.instruction}"
            info(hello_message)
            yield ChatMessage(role=Role.SYSTEM, content=hello_message)
            self.research_agent = Research(
                self.config, agent_env, self.workspace, language=self.language
            )
            try:
                async for msg in self.research_agent.loop(request):
                    if isinstance(msg, str):
                        md_file = Path(msg)
                        if not md_file.is_absolute():
                            md_file = self.workspace / md_file
                        self.intermediate_output["manuscript"] = md_file
                        msg = str(md_file)
                        break
                    yield msg
            except Exception as e:
                error_message = f"Research agent failed with error: {e}"
                error(error_message)
                yield ChatMessage(role=Role.SYSTEM, content=error_message)
                raise e
            finally:
                self.research_agent.save_history()
            if request.convert_type == ConvertType.PPTAGENT:
                self.pptagent = PPTAgent(
                    self.config, agent_env, self.workspace, language=self.language
                )
                try:
                    async for msg in self.pptagent.loop(request, md_file):
                        if isinstance(msg, str):
                            pptx_file = Path(msg)
                            if not pptx_file.is_absolute():
                                pptx_file = self.workspace / pptx_file
                            self.intermediate_output["pptx"] = pptx_file
                            msg = str(pptx_file)
                            break
                        yield msg
                except Exception as e:
                    error_message = f"PPTAgent failed with error: {e}"
                    error(error_message)
                    yield ChatMessage(role=Role.SYSTEM, content=error_message)
                    raise e
                finally:
                    self.pptagent.save_history()
            else:
                self.designagent = Design(
                    self.config, agent_env, self.workspace, language=self.language
                )
                try:
                    async for msg in self.designagent.loop(request, md_file):
                        if isinstance(msg, str):
                            slide_html_dir = Path(msg)
                            if not slide_html_dir.is_absolute():
                                slide_html_dir = self.workspace / slide_html_dir
                            self.intermediate_output["slide_html_dir"] = slide_html_dir
                            break
                        yield msg
                except Exception as e:
                    error_message = f"Design agent failed with error: {e}"
                    error(error_message)
                    yield ChatMessage(role=Role.SYSTEM, content=error_message)
                    raise e
                finally:
                    self.designagent.save_history()
                pptx_path = self.workspace / f"{md_file.stem}.pptx"
                convert_html_to_pptx(
                    slide_html_dir,
                    pptx_path,
                    aspect_ratio=request.aspect_ratio,
                )
                self.intermediate_output["pptx"] = pptx_path
                msg = pptx_path
            with open(self.workspace / "intermediate_output.json", "w") as f:
                json.dump(
                    {k: str(v) for k, v in self.intermediate_output.items()},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            info(f"DeepPresenter run completed, output saved to {msg}")
            yield msg
