import json
import os
import random
import re
import sys
from collections import defaultdict
from functools import partial
from glob import glob
from typing import List

import func_argparse
import jieba
import torch
from jinja2 import Template
from rouge_chinese import Rouge

rouge = Rouge()

FASTER_FID = "evaluation/faster-pytorch-fid"
if os.path.exists(FASTER_FID + "/fid_score_gpu.py"):
    sys.path.append(FASTER_FID)
    import fid_score_gpu as fid
else:
    import pytorch_fid.fid_score as fid
    from pytorch_fid.fid_score import calculate_frechet_distance

from rich import print
from tqdm import tqdm
from transformers import AutoModelForCausalLM, AutoTokenizer

import llms
from presentation import Picture, Presentation
from utils import Config, pdirname, pexists, pjoin

fid.tqdm = lambda x: x
fid.print = lambda x: x
judges = [
    (llms.gpt4o, llms.gpt4o, "gpt4o"),
    (llms.qwen2_5, llms.qwen_vl, "Qwen"),
    (llms.qwen_vl, llms.qwen_vl, "qwen_vl"),
]

PPL_MODEL = "/141nfs/zhenghao2022/PPTAgent/Llama-3-8B"
DEVICES = torch.cuda.device_count()


def get_eval(prs_source: str):
    evals = defaultdict(dict)
    eval_file = pjoin(pdirname(prs_source), "evals.json")
    if pexists(eval_file):
        with open(eval_file, "r") as f:
            evals |= json.load(f)
    return evals, eval_file


def get_rouge(prs_text: str, prs_source: str) -> float:
    md_file = pjoin(pdirname(pdirname(pdirname(prs_source))), "source.md")
    if not pexists(md_file):
        source, _, _, pdf, _ = prs_source.rsplit("/", 4)
        md_file = pjoin(source.replace("pptx", "pdf"), pdf, "source.md")
    reference = open(md_file).read()
    reference = " ".join(jieba.cut(str(reference)))
    hypothesis = " ".join(jieba.cut(str(prs_text)))
    return rouge.get_scores(hypothesis, reference)[0]["rouge-l"]["f"]


def get_ppl(inputs: List[str], model: AutoModelForCausalLM, tokenizer: AutoTokenizer):
    ppl = []
    for sl_text in inputs:
        tokenized = tokenizer(sl_text, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outputs = model(tokenized.input_ids, labels=tokenized.input_ids)
            loss = outputs.loss
            perplexity = torch.exp(loss)
            ppl.append(perplexity.item())
    return sum(ppl) / len(ppl)


def parse_beamer(tex_file: str):
    slides = []
    current = []
    tex = open(tex_file).read()
    lines = tex.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if r"\begin{frame}" in line:
            current = []
            continue

        if r"\end{frame}" in line:
            if current:
                slides.append(current)
            continue

        if r"\frametitle" in line:
            title = re.search(r"\{(.*?)\}", line)
            if title:
                current.append(title.group(1))
            continue

        if r"\item" in line:
            item = re.search(r"\\item\s+(.*?)$", line)
            if item:
                current.append(item.group(1))

    if r"\titlepage" in tex:
        title = re.search(r"\\title\{(.*?)\}", tex)
        author = re.search(r"\\author\{(.*?)\}", tex)
        if title:
            slides[0].append(title.group(1))
            if author:
                slides[0].append(author.group(1))

    return ["\n".join(s) for s in slides]


def eval_general(prs_files: list[str]):
    tmp_config = Config("/tmp")
    for prs_source in tqdm(prs_files, desc="General Scoring"):
        evals, eval_file = get_eval(prs_source)
        if prs_source.endswith(".pptx"):
            prs = Presentation.from_file(prs_source, tmp_config)
            evals["pages"] = len(prs)
            evals["characters"] = sum([len(slide.to_text()) for slide in prs.slides])
            evals["figures"] = sum(
                [len(list(slide.shape_filter(Picture))) for slide in prs.slides]
            )
            evals["rouge-l"] = get_rouge(prs.to_text(), prs_source)
        else:
            slide_texts = parse_beamer(prs_source.replace(".pdf", ".tex"))
            evals["characters"] = sum([len(s) for s in slide_texts])
            evals["figures"] = len(
                re.findall(
                    r"\!\[.*?\]\(.*?\)", open(prs_source.replace(".pdf", ".tex")).read()
                )
            )
            evals["rouge-l"] = get_rouge(slide_texts, prs_source)
        with open(eval_file, "w") as f:
            json.dump(evals, f, indent=4)


def eval_fid(setting: str):
    device = f"cuda:{random.randint(0, DEVICES - 1)}"
    if FASTER_FID in sys.path:
        calculate_frechet_distance = partial(
            fid.calculate_frechet_distance, device=device
        )
    model = fid.InceptionV3([fid.InceptionV3.BLOCK_INDEX_BY_DIM[64]]).to(device)
    for ppt_folder in tqdm(sorted(glob(f"data/*/pptx/*/")), desc="FID Scoring"):
        source_folder = pjoin(ppt_folder, "source_slides")
        m1, s1 = fid.compute_statistics_of_path(source_folder, model, 128, 64, device)
        for result_folder in glob(pjoin(ppt_folder, f"final_images/{setting}/*")):
            if len(os.listdir(result_folder)) < 3:
                continue
            try:
                m2, s2 = fid.compute_statistics_of_path(
                    result_folder, model, 32, 64, device
                )
                fid_value = calculate_frechet_distance(m1, s1, m2, s2)
                source, _, _, pdf = result_folder.rsplit("/", 3)
                evals, eval_file = get_eval(pjoin(source, setting, pdf, "final.pptx"))
                evals["fid"] = fid_value
                with open(eval_file, "w") as f:
                    json.dump(evals, f, indent=4)
            except Exception as e:
                print(e, "\n", "happended in ", ppt_folder, "on:", setting)


def eval_ppl(
    prs_files: list[str],
):
    tmp_config = Config("/tmp")
    device = f"cuda:{random.randint(0, DEVICES - 1)}"
    model = AutoModelForCausalLM.from_pretrained(PPL_MODEL, device_map=device)
    tokenizer = AutoTokenizer.from_pretrained(PPL_MODEL)
    for prs_source in tqdm(prs_files, desc="PPL Scoring"):
        evals, eval_file = get_eval(prs_source)
        if evals.get("ppl", None):
            continue
        if prs_source.endswith(".pptx"):
            prs = Presentation.from_file(prs_source, tmp_config)
            slide_texts = [slide.to_text() for slide in prs.slides]
        elif prs_source.endswith(".pdf"):
            slide_texts = parse_beamer(prs_source.replace(".pdf", ".tex"))
        try:
            evals["ppl"] = get_ppl(slide_texts, model, tokenizer)
            with open(eval_file, "w") as f:
                json.dump(evals, f, indent=4)
        except Exception as e:
            print(e, "\n", "happended in ", prs_source)


def slide_score(prs_source: str, slide_folder: str):
    evals, eval_file = get_eval(prs_source)
    text_scorer = Template(open("prompts/ppteval_content.txt", "r").read())
    vision_scorer = Template(open("prompts/ppteval_style.txt", "r").read())
    style_descriptor = open("prompts/ppteval_describe_style.txt", "r").read()
    content_descriptor = open("prompts/ppteval_describe_content.txt", "r").read()
    for slide_image in glob(pjoin(slide_folder, "slide_*.jpg")):
        slide_descr = slide_image.replace(".jpg", ".json")
        if not os.path.exists(slide_descr):
            style_descr = llms.vision_model(style_descriptor, slide_image)
            content_descr = llms.vision_model(content_descriptor, slide_image)
            with open(slide_descr, "w") as f:
                json.dump(
                    {"content": content_descr, "style": style_descr},
                    f,
                    indent=4,
                )
        else:
            descr = json.load(open(slide_descr))
            style_descr = descr["style"]
            content_descr = descr["content"]
        if slide_image not in evals["vision"]:
            evals["vision"][slide_image] = llms.language_model(
                vision_scorer.render(descr=style_descr), return_json=True
            )
        if slide_image not in evals["content"]:
            evals["content"][slide_image] = llms.language_model(
                text_scorer.render(descr=content_descr), return_json=True
            )
    with open(eval_file, "w") as f:
        json.dump(evals, f)


def pres_score(prs_source: str):
    tmp_config = Config("/tmp")
    slide_folder = pdirname(prs_source)
    evals, eval_file = get_eval(prs_source)
    if "logic" in evals:
        return
    slide_descr = pjoin(slide_folder, "extracted.json")
    if not pexists(slide_descr):
        if prs_source.endswith(".pptx"):
            presentation = Presentation.from_file(prs_source, tmp_config).to_text()
        elif prs_source.endswith(".pdf"):
            presentation = ""
            for idx, sl in enumerate(parse_beamer(prs_source.replace(".pdf", ".tex"))):
                presentation += f"slide {idx+1}\n{sl}\n"

        ppt_extractor = Template(open("prompts/ppteval_extract.txt", "r").read())
        extracted = llms.language_model(
            ppt_extractor.render(presentation=presentation),
            return_json=True,
        )
        with open(slide_descr, "w") as f:
            json.dump(extracted, f, indent=4)
    else:
        extracted = json.load(open(slide_descr))
    logic_scorer = Template(open("prompts/ppteval_coherence.txt", "r").read())
    evals["logic"] = llms.language_model(
        logic_scorer.render(
            presentation=extracted,
        ),
        return_json=True,
    )
    with open(eval_file, "w") as f:
        json.dump(evals, f, indent=4)


def eval_ppt(prs_files: list[str], slide_folders: list[str]):
    for prs_file in tqdm(prs_files, desc="PPT Scoring"):
        pres_score(prs_file)
    for prs_file, slide_folder in tqdm(
        list(zip(prs_files, slide_folders)), desc="Slide Scoring"
    ):
        slide_score(prs_file, slide_folder)


# ppt eval
def eval_experiment(
    setting: str,
    general_eval: bool = False,
    ppl_eval: bool = False,
    fid_eval: bool = False,
    ppt_eval: bool = False,
):
    prs_files = glob(f"data/*/pptx/*/{setting}/*/final.pptx")
    slide_folders = glob(f"data/*/pptx/*/final_images/{setting}/*")

    if general_eval:
        eval_general(prs_files)

    if ppl_eval:
        eval_ppl(prs_files)

    if fid_eval:
        eval_fid(setting)

    if ppt_eval:
        eval_ppt(prs_files, slide_folders)


def eval_docpres(
    general_eval: bool = False,
    ppl_eval: bool = False,
    ppt_eval: bool = False,
):
    prs_files = glob(f"data/*/pdf/*/docpres/*/final.pptx")
    slide_folders = [pdirname(i) + "/slide_images" for i in prs_files]

    if general_eval:
        eval_general(prs_files)
    if ppl_eval:
        eval_ppl(prs_files)
    if ppt_eval:
        eval_ppt(prs_files, slide_folders)


def eval_kctv(
    general_eval: bool = False,
    ppl_eval: bool = False,
    ppt_eval: bool = False,
):
    prs_files = glob(f"data/*/pdf/*/kctv/*/final.pdf")
    slide_folders = [pdirname(i) + "/slide_images" for i in prs_files]

    if general_eval:
        eval_general(prs_files)

    if ppl_eval:
        eval_ppl(prs_files)

    if ppt_eval:
        eval_ppt(prs_files, slide_folders)


if __name__ == "__main__":
    llms.language_model, llms.vision_model, _ = judges[0]
    func_argparse.main(
        eval_experiment,
        eval_docpres,
        eval_kctv,
        pres_score,
        slide_score,
    )
