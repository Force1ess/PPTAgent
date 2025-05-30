import tempfile
from glob import glob
from os.path import join as pjoin
from test.conftest import test_config

import pytest

from pptagent.model_utils import parse_pdf


@pytest.mark.parse
@pytest.mark.asyncio
async def test_parse_pdf():
    with tempfile.TemporaryDirectory() as temp_dir:
        await parse_pdf(
            pjoin(test_config.document, "source.pdf"),
            temp_dir,
        )
        assert len(glob(pjoin(temp_dir, "*.md")))
