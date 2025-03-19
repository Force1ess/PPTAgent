from document import Document, Table
from llms import language_model, vision_model
import json

# 表格的提取效果不够好
def test_document():
    document = Document.from_dict(
        json.load(open("resource/test/test_pdf/refined_doc.json")), "resource/test/test_pdf", False
    )
    document.overview
    document.metainfo
    document.index({"Abstract": ["Introduction to PPTAgent"]})
    medias = list(document.iter_medias())
    assert len(medias) == 8
    assert sum(isinstance(media, Table) for media in medias) == 0
    for media in document.iter_medias():
        assert media.caption is not None
