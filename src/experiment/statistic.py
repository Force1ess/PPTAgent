import json
from collections import defaultdict
from glob import glob

import jsonlines
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scienceplots
import seaborn as sns
from scipy.stats import pearsonr, spearmanr

from apis import HistoryMark

DIMENSION_MAPPING = {"content": "Content", "vision": "Design", "logic": "Coherence"}
MAPPING = {"ppl": "PPL", "fid": "FID", "rouge-l": "ROUGE-L"}


def merge_evals(eval_files: list[str], print_avg: bool = True):
    evals = defaultdict(list)
    for eval_file in eval_files:
        sub_eval = json.load(open(eval_file))
        for dimension in sub_eval:
            if dimension not in DIMENSION_MAPPING:
                evals[MAPPING.get(dimension, dimension)].append(sub_eval[dimension])
            elif "score" in sub_eval[dimension]:
                evals[DIMENSION_MAPPING[dimension]].append(sub_eval[dimension]["score"])
            elif isinstance(sub_eval[dimension], dict):
                sorted_scores = [
                    v["score"] for _, v in sorted(sub_eval[dimension].items())
                ]
                evals[DIMENSION_MAPPING[dimension]].extend(sorted_scores)
    if print_avg:
        print("Performance of cluster", eval_file)
        for dimension, values in evals.items():
            print(dimension, np.mean([i for i in values if not pd.isna(i)]))
    return evals


def statistic_humaneval(eval_file: str, print_diff: bool = False):
    llm_eval = json.load(open(eval_file))
    llm_data = []
    for dimension, files in llm_eval.items():
        for filename, values in files.items():
            try:
                setting, basename = filename.split("/", 2)[1:]
                basename = basename.split("/")[0]
                if not isinstance(values["score"], int):
                    raise ValueError(f"score is not int: {values['score']}")
                llm_data.append(
                    {
                        "setting": setting,
                        "sample": basename,
                        "dimension": dimension,
                        "score": values["score"],
                    }
                )
            except:
                continue

    file_path = "human_eval/human_scores_2024-12-13.xlsx"
    human_eval = pd.read_excel(file_path).to_dict("records")
    human_data = []
    for record in human_eval:
        setting = record.get("setting")
        score = record[dimension]
        basename = record["PPT"]
        try:
            score = int(score)
        except:
            continue
        human_data.append(
            {
                "setting": setting,
                "sample": basename,
                "dimension": dimension,
                "score": score,
            }
        )

    # Compare and output differences between human and llm evaluations
    llm = pd.DataFrame(llm_data)
    human = pd.DataFrame(human_data)
    merged = pd.merge(
        llm,
        human,
        on=["setting", "sample", "dimension"],
        suffixes=("_llm", "_human"),
        how="outer",
        indicator=True,
    )
    # Calculate and print correlation coefficients for common records
    common_records = merged[merged["_merge"] == "both"].drop(columns=["_merge"])
    dimensions = common_records["dimension"].unique()

    for dimension in dimensions:
        scores_human = common_records[common_records["dimension"] == dimension][
            "score_human"
        ]
        scores_llm = common_records[common_records["dimension"] == dimension][
            "score_llm"
        ]
        pearson_correlation = pearsonr(scores_human, scores_llm)
        spearman_correlation = spearmanr(scores_human, scores_llm)
        print(
            f"{dimension}, pearson: {pearson_correlation}, spearman: {spearman_correlation}"
        )
        if print_diff:
            difference = common_records[
                common_records["score_human"] != common_records["score_llm"]
            ]
            for _, row in difference.iterrows():
                print(row)


def statistic_ppteval():
    data = []
    eval_files = glob("./data/evals/PPTCrew*")
    for eval_file in eval_files:
        setting = eval_file.split("/")[-1].removesuffix(".json")
        eval_stats = json.load(open(eval_file))
        for dimension, files in eval_stats.items():
            if dimension == "vision":
                dimension = "design"
            for filename, score in files.items():
                domain = filename.split("/")[1]
                if isinstance(score, dict):
                    score = score["score"]
                if isinstance(score, str):
                    continue
                if score > 5000 or score < 0:
                    continue
                data.append(
                    {
                        "setting": setting,
                        "dimension": dimension,
                        "sample": filename,
                        "score": score,
                        "domain": domain,
                    }
                )
    return pd.DataFrame(data)


def setting_perfomance(df: pd.DataFrame):
    df = df.drop(columns=["domain"])
    for setting, dimension in df[["setting", "dimension"]].drop_duplicates().values:
        avg_score = df[(df["setting"] == setting) & (df["dimension"] == dimension)][
            "score"
        ].mean()
        print(f"{setting}, {dimension}, {avg_score}")


def plot_correlation(eval_files: list[str], required_dimensions: list[str]):
    evals = defaultdict(list)
    for eval_file in eval_files:
        sub_eval = json.load(open(eval_file))
        for dimension in required_dimensions:
            if dimension not in DIMENSION_MAPPING:
                evals[MAPPING.get(dimension, dimension)].append(sub_eval[dimension])
            elif "score" in sub_eval[dimension]:
                evals[DIMENSION_MAPPING[dimension]].append(sub_eval[dimension]["score"])
            elif isinstance(sub_eval[dimension], dict):
                sorted_scores = [
                    v["score"] for _, v in sorted(sub_eval[dimension].items())
                ]
                evals[DIMENSION_MAPPING[dimension]].append(
                    sum(sorted_scores) / len(sorted_scores)
                )

    corr = pd.DataFrame(evals).corr()
    plt.figure(figsize=(10, 8))
    sns.heatmap(
        corr,
        annot=True,
        cmap="viridis",
        fmt=".2f",
        linewidths=0.5,
        vmin=-1,
        vmax=1,
    )
    plt.savefig("correlation.pdf", bbox_inches="tight")


def domain_perfomance(df: pd.DataFrame):
    df = df[df["setting"] == "PPTCrew-gpt-4o+gpt-4o+gpt-4o"]
    for domain, scores in df.groupby("domain")["score"]:
        print(f"{domain}, {scores.mean()}")


def quantitative_analysis(
    setting_evals: dict[str, list[dict[str, int]]],
    required_dimensions: list[str],
    colors: list[str],
):
    hist_data = {
        dim: {setting: {} for setting in setting_evals} for dim in required_dimensions
    }
    settings = ["PPTAgent", "DocPres", "KCTV"]

    for setting, evals in setting_evals.items():
        for dimension in required_dimensions:
            unique, counts = np.unique(evals[dimension], return_counts=True)
            hist_data[dimension][setting] = dict(zip(unique, counts / counts.sum()))

    _, axes = plt.subplots(1, 3, figsize=(16, 3.7), sharey=True)

    for ax, category in zip(axes, required_dimensions):
        scores = [
            list(map(int, hist_data[category][method].keys())) for method in settings
        ]
        weights = [list(hist_data[category][method].values()) for method in settings]

        ax.hist(
            scores,
            bins=np.arange(7) - 0.5,
            weights=weights,
            color=colors,
            alpha=0.7,
            label=settings,
            edgecolor="black",
        )

        ax.set_xlabel(category.capitalize())
        ax.set_xticks(np.arange(1, 6))
        ax.legend()
        ax.set_xlim(0.5, 5.5)

    axes[0].set_ylabel("Proportion")
    plt.tight_layout()
    plt.savefig("quantitative.pdf", bbox_inches="tight")


def error_analysis(settings: dict[str, str], colors: list[str]):
    setting_counts = {}
    for setting in settings:
        counts = defaultdict(int)
        for step_file in glob(f"data/*/pptx/*/{setting}/*/agent_steps.jsonl"):
            count = 0
            for step in jsonlines.open(step_file):
                if step[0] == HistoryMark.API_CALL_ERROR:
                    count += 1
                else:
                    counts[count] += 1
                    count = 0

            counts[count] += 1

        setting_counts[settings[setting]] = counts

    iters = sorted({it for model in setting_counts.values() for it in model.keys()})

    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    width = 0.3
    x = np.arange(len(iters))

    for i, (model, counts) in enumerate(setting_counts.items()):
        heights = [counts.get(it, 0) for it in iters]
        bars = ax.bar(x + i * width, heights, width, label=model, color=colors[i])

        for bar, height in zip(bars, heights):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                height,
                f"{height}",
                ha="center",
                va="bottom" if height > 10 else "top",
                fontsize=13,
            )

    ax.set_xticks(x + width)
    ax.set_xlabel("# Iterations")
    ax.set_ylabel("Counts")
    ax.legend()
    ax.set_yscale("log")
    ax.set_ylim([1, 13999])
    ax.set_xticklabels([0, 1, 2, "Failure"])
    ax.set_yticks([1, 10, 100, 1000])
    ax.minorticks_off()
    plt.savefig("./self-correction.pdf", bbox_inches="tight")


if __name__ == "__main__":
    # Merge eval result and print_mean
    kctv_qwen_files = sorted(glob("data/*/pdf/*/kctv/Qwen2.5/evals.json"))
    kctv_gpt_files = sorted(glob("data/*/pdf/*/kctv/gpt-4o/evals.json"))
    docpres_qwen_files = sorted(glob("data/*/pdf/*/docpres/Qwen2.5/evals.json"))
    docpres_gpt_files = sorted(glob("data/*/pdf/*/docpres/gpt-4o/evals.json"))
    pptcrew_qwen_files = sorted(
        glob("data/*/pptx/*/PPTCrew-Qwen2-VL+Qwen2-VL+Qwen2-VL/*/evals.json")
    )
    pptcrew_gpt_files = sorted(
        glob("data/*/pptx/*/PPTCrew-gpt-4o+gpt-4o+gpt-4o/*/evals.json")
    )
    pptcrew_mix_files = sorted(
        glob("data/*/pptx/*/PPTCrew-Qwen2.5+Qwen2.5+Qwen2-VL/*/evals.json")
    )

    kctv_qwen = merge_evals(kctv_qwen_files)
    kctv_gpt = merge_evals(kctv_gpt_files)
    docpres_qwen = merge_evals(docpres_qwen_files)
    docpres_gpt = merge_evals(docpres_gpt_files)
    pptcrew_qwen = merge_evals(pptcrew_qwen_files)
    pptcrew_gpt = merge_evals(pptcrew_gpt_files)
    pptcrew_mix = merge_evals(pptcrew_mix_files)

    plt.minorticks_off()
    chatdev_colors = ["#B56A65", "#E9C67E", "#3A7F9E"]

    # Plot correlation between ppl, fid, content, design

    with plt.style.context(["ieee", "grid", "no-latex"]):
        plt.rcParams.update({"font.size": 22})
        plot_correlation(
            pptcrew_mix_files, ["ppl", "rouge-l", "fid", "content", "vision"]
        )

    # # Quntitive Analysis

    # with plt.style.context(["ieee", "grid", "no-latex"]):
    #     plt.rcParams.update({"font.size": 16})
    #     quantitative_analysis(
    #         {"PPTAgent": pptcrew_mix, "KCTV": kctv_qwen, "DocPres": docpres_qwen},
    #         ["Content", "Design", "Coherence"],
    #         chatdev_colors,
    #     )

    # # Error Analysis

    # with plt.style.context(["ieee", "grid", "no-latex"]):
    #     plt.rcParams.update({"font.size": 16})
    #     error_analysis(
    #     {
    #         "PPTCrew-gpt-4o+gpt-4o+gpt-4o": "GPT-4o",
    #         "PPTCrew-Qwen2.5+Qwen2.5+Qwen2-VL": "Qwen2.5",
    #         "PPTCrew-Qwen2-VL+Qwen2-VL+Qwen2-VL": "Qwen2-VL",
    #     }, chatdev_colors)
