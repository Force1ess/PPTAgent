from document import Document, Table
from llms import language_model, vision_model
import json

# 表格的提取效果不够好
def test_document():
    document = Document.from_dict(
        json.load(open("resource/test/test_pdf/refined_doc.json")), "resource/test/test_pdf", False
    )
    medias = list(document.iter_medias())
    document.overview
    document.metainfo
    document.index({"Experiment": ["Dataset"]})
    assert len(medias) == 7
    assert sum(isinstance(media, Table) for media in medias) == 3

