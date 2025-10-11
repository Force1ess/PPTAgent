"""PPTAgent: Generating and Evaluating Presentations Beyond Text-to-Slides.

This package provides tools to automatically generate presentations from documents,
following a two-phase approach of Analysis and Generation.

For more information, visit: https://github.com/icip-cas/PPTAgent
"""

__version__ = "0.2.0"
__author__ = "Hao Zheng"
__email__ = "wszh712811@gmail.com"


# Check the version of python and python-pptx

from packaging.version import Version
from pptx import __version__ as PPTXVersion

try:
    PPTXVersion, Mark = PPTXVersion.split("+")
    assert Version(PPTXVersion) >= Version("1.0.4") and Mark == "PPTAgent"
except Exception as _:
    raise ImportError(
        "You should install the customized `python-pptx` for this project, see https://github.com/Force1ess/python-pptx"
    )

# __init__.py
from .document import Document
from .llms import LLM, AsyncLLM
from .mcp_server import PPTAgentServer
from .model_utils import ModelManager
from .multimodal import ImageLabler
from .pptgen import PPTAgent
from .presentation import Presentation
from .utils import Config, Language

__all__ = [
    "__version__",
    "__author__",
    "__email__",
    "PPTAgent",
    "PPTAgentServer",
    "Document",
    "Presentation",
    "Config",
    "Language",
    "ModelManager",
    "ImageLabler",
    "LLM",
    "AsyncLLM",
]
