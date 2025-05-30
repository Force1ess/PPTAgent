import json
import warnings

from pptagent.model_utils import ModelManager
from pptagent.utils import Config, pjoin


# warning of zipfile indicates that presentation save failed
def pytest_configure():
    warnings.filterwarnings("error", module=r"zipfile")


# Common test configuration
class TestConfig:
    def __init__(self):
        self.template = pjoin("runs", "pptx", "default_template")
        self.document = pjoin("runs", "pdf", "57b32a38d68d1e62908a3d4fe77441c2")
        self.ppt = pjoin("test", "test.pptx")
        self.models = ModelManager()

        # Configuration object
        self.config = Config(self.template)

    def get_slide_induction(self):
        """Load slide induction data"""
        return json.load(open(pjoin(self.template, "slide_induction.json")))

    def get_document_json(self):
        """Load document JSON"""
        return json.load(open(pjoin(self.document, "refined_doc.json")))

    def get_image_stats(self):
        """Load captions data"""
        return json.load(open(pjoin(self.template, "image_stats.json")))

    @property
    def language_model(self):
        return self.models.language_model

    @property
    def vision_model(self):
        return self.models.vision_model

    @property
    def image_model(self):
        return self.models.image_model

    @property
    def marker_model(self):
        return self.models.marker_model


# Create a global instance
test_config = TestConfig()
