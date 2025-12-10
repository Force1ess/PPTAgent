"""DeepPresenter - AI-powered presentation generation system"""

import os

from .utils.config import GLOBAL_CONFIG

__version__ = "0.1.0"
__all__ = ["GLOBAL_CONFIG"]

assert os.name == "posix", "DeepPresenter only supports Linux and macOS"
