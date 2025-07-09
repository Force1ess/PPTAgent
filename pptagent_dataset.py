from glob import glob
from os.path import join

import jsonlines
from datasets import Dataset

data = []
preference = []
ppts = glob("pptagent-veRL/*/*")
for ppt in ppts:
    base_ppt, base_pdf = ppt.split("/")[-2:]

    commands: list[list] = list(jsonlines.open(join(ppt, "command_list.jsonl")))
    api_history = list(jsonlines.open(join(ppt, "api_history.jsonl")))
    num_slides = len(commands)

    for idx in range(num_slides):
        prompt = commands[-1][-1]
        slide_apis = api_history[idx]
        base = {
            "source_pptx": base_ppt,
            "source_pdf": base_pdf,
            "template_id": slide_apis[-1][1],
            "system": "You are a Code Generator agent specializing in slide manipulation. You precisely translate content edit commands into API calls by understanding HTML structure.",
            "prompt": prompt,
        }
        if len(slide_apis) != 1 and slide_apis[-1][0] == "api_call_correct":
            preference.append(
                {
                    "chosen": slide_apis[-1][-1],
                    "reject": slide_apis[0][-1],
                    **base,
                }
            )
        if slide_apis[-1][0] == "api_call_correct":
            data.append(
                {
                    "gt_response": slide_apis[-1][-1],
                    **base,
                }
            )

preference_dataset = Dataset.from_list(preference)
data_dataset = Dataset.from_list(data)
preference_dataset.to_parquet("preference_dataset.parquet")
data_dataset.to_parquet("data_dataset.parquet")
