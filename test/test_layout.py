import json

from layout import Layout

def test_layout():
    template = json.load(
        open("runs/pptx/default_template/template_induct/backend/induct_cache.json")
    )
    layout = Layout.from_dict(template["opening:text"])
    layout.content_schema
    layout.get_old_data()
