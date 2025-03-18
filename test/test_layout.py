import json

from layout import Layout

def test_layout():
    template = json.load(open("resource/test/test_ppt/induct_cache.json"))
    layout = Layout.from_dict(template["opening:text"])
    layout.content_schema
    layout.get_old_data()
