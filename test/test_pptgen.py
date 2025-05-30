from test.conftest import test_config

import pytest

from pptagent.document import Document
from pptagent.multimodal import ImageLabler
from pptagent.pptgen import PPTAgent
from pptagent.presentation import Presentation
from pptagent.utils import pjoin


@pytest.mark.asyncio
@pytest.mark.llm
async def test_pptgen():
    pptgen = PPTAgent(
        language_model=test_config.language_model,
        vision_model=test_config.vision_model,
    ).set_reference(
        config=test_config.config,
        presentation=Presentation.from_file(
            pjoin(test_config.template, "source.pptx"), test_config.config
        ),
        slide_induction=test_config.get_slide_induction(),
    )
    labeler = ImageLabler(pptgen.presentation, pptgen.config)
    labeler.apply_stats(test_config.get_image_stats())

    document = Document(**test_config.get_document_json())
    await pptgen.generate_pres(document, 3)
