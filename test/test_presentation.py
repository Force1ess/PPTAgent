from presentation import Presentation, Config


def test_presentation():
    config = Config("/tmp")
    presentation = Presentation.from_file("test.pptx", config)
    assert len(presentation.slides) == 84
    for sld in presentation.slides:
        sld.to_html(show_image=False)
