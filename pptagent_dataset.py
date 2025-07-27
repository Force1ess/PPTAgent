from glob import glob
from os.path import exists, join

import jsonlines
from datasets import Dataset

data = []
ppts = glob("pptagent-veRL/*/*")
for ppt in ppts:
    base_ppt, base_pdf = ppt.split("/")[-2:]

    if not exists(join(ppt, "command_list.jsonl")):
        continue
    api_history = list(jsonlines.open(join(ppt, "api_history.jsonl")))
    commands: list[list] = list(jsonlines.open(join(ppt, "command_list.jsonl")))
    num_slides = len(commands)

    for idx in range(num_slides):
        prompt = commands[-1][-1]
        slide_apis = api_history[idx]
        if slide_apis[-1][0] != "api_call_correct":
            continue
        response: str = slide_apis[-1][-1]
        response = response[response.find("```python") :]
        if len(response) < 50:
            continue
        messages = [
            {
                "role": "system",
                "content": "You are a Code Generator agent specializing in slide manipulation. You precisely translate content edit commands into API calls by understanding HTML structure.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]
        extra_info = {
            "source_pptx": base_ppt,
            "source_pdf": base_pdf,
            "template_id": slide_apis[-1][1],
        }
        data.append(
            {
                "data_source": "pptagent-code26k",
                "prompt": messages,
                "reward_model": {"style": "rule", "ground_truth": response},
                "extra_info": extra_info,
            }
        )

data_dataset = Dataset.from_list(data)
dataset_dict = data_dataset.train_test_split(test_size=0.1)
dataset_dict.push_to_hub("pptagent-code26k", private=True)
# dataset_dict["train"].to_parquet("train.parquet")
# dataset_dict["test"].to_parquet("val.parquet")
