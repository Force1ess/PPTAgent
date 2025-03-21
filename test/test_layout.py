from pptagent.layout import Layout
from test.conftest import test_config


def test_layout():
    template = test_config.get_slide_induction()
    layout = Layout.from_dict(template["opening:text"])
    layout.content_schema
    layout.get_old_data()
