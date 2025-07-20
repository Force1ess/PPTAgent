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

docs = {}
for doc_path in glob("data/*/pdf/*/refined_doc.json"):
    doc = Document(**json.load(open(doc_path)))
    docs[basename(doc_path.replace("/refined_doc.json", ""))] = doc

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


def compute_score(
    data_source, solution_str, ground_truth, extra_info:dict[str, str], format_score=0.1
):
    
    doc = docs[extra_info["source_pdf"]]
    source_slide = deepcopy(ppts[extra_info["source_pptx"]].slides[extra_info["template_id"] - 1])

    gen_slide = deepcopy(source_slide)
    exec_result = slide_execute(solution_str, gen_slide, doc)

    gt_slide = deepcopy(source_slide)
    if not slide_execute(ground_truth, gt_slide, doc):
        raise ValueError("Ground truth is not executable")

    if exec_result:
        return rouge_score(gen_slide, gt_slide)
    else:
        return 0


if __name__ == "__main__":
    import pandas as pd

    pseudo_code = ""

    df = pd.read_parquet("pptagent-code26k/data/train-00000-of-00001.parquet")
    for row in df.to_dict(orient="records"):
        compute_score(row["data_source"], pseudo_code, row["reward_model"]["ground_truth"], row["extra_info"])
