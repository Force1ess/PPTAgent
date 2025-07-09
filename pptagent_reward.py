import json
from copy import deepcopy
from glob import glob
from os.path import basename, join

from rouge_score import rouge_scorer

from pptagent.apis import CodeExecutor
from pptagent.document import Document
from pptagent.multimodal import ImageLabler
from pptagent.presentation import Presentation, SlidePage
from pptagent.utils import Config

scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
ppts = {}
for ppt in glob("data/*/pptx/*"):
    config = Config(ppt)
    ppts[basename(ppt)] = Presentation.from_file(join(ppt, "source.pptx"), config)
    image_labler = ImageLabler(ppts[basename(ppt)], config)
    image_states = json.load(open(join(ppt, "image_stats.json")))
    image_labler.apply_stats(image_states)


def rouge_score(gen_slide: SlidePage, gt_slide: SlidePage):
    return scorer.score(gen_slide.to_text(True), gt_slide.to_text(True))[
        "rougeL"
    ].fmeasure


# here we should create pseudo images
def slide_execute(commands: str, slide: SlidePage, doc: Document):
    try:
        code_executor = CodeExecutor(retry_times=1)
        ret = code_executor.execute_actions(commands, slide, doc)
        assert ret is None, "Error occurs when executing the commands"
    except:
        return False
    return True


def compute_reward(
    source_pptx: str,
    source_pdf: str,
    template_id: int,
    gt_commands: str,
    response: str,
):
    doc_path = glob(join("data", "*", "pdf", source_pdf, "refined_doc.json"))[0]
    doc = Document(**json.load(open(doc_path)))
    source_slide = deepcopy(ppts[source_pptx].slides[template_id - 1])

    gen_slide = deepcopy(source_slide)
    exec_result = slide_execute(response, gen_slide, doc)

    gt_slide = deepcopy(source_slide)
    slide_execute(gt_commands, gt_slide, doc)

    if exec_result:
        return rouge_score(gen_slide, gt_slide)
    else:
        return 0


if __name__ == "__main__":
    import pandas as pd

    pseudo_code = ""

    df = pd.read_parquet("data_dataset.parquet")
    row = df.iloc[0].to_dict()
    compute_reward(
        row["source_pptx"],
        row["source_pdf"],
        row["template_id"],
        row["gt_response"],
        pseudo_code,
    )
