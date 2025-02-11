# Documentation 📝

This documentation provides an overview of the project structure, setup instructions, usage guidelines, and steps for reproducing experiments.

Table of Contents
=================
- [File Structure 📂](#file-structure-)
- [Quick Start 🚀](#quick-start-)
  - [Docker 🐳](#docker-)
  - [Setup 🛠](#setup-)
  - [Usage 🖥️](#usage-️)
- [FAQ ❓](#faq-)
- [Experiments Reproduction 🔍 (WIP)](#experiments-reproduction--wip)
  - [Generation 🧪](#generation-)
  - [Evaluation 📊](#evaluation-)

## File Structure 📂

```
PPTAgent/
|-- data/                       # Data for the project, saved like data/topic/filetype/filename/original.filetype
├── src/
│   ├── apis.py                 # API and CodeExecutor
│   ├── llms.py                 # LLM services initialization
│   ├── presentation.py         # PPTX parsing and manipulation
│   ├── multimodal.py           # Image information extraction
│   ├── induct.py               # Presentation analysis (Stage Ⅰ)
│   ├── pptgen.py               # Presentation generation (Stage Ⅱ)
│   ├── model_utils.py          # Machine Learning utilities
│   ├── utils.py                # General utilities
│   ├── experiment/             # Experiment scripts
├── pptagent_ui/                # UI for PPTAgent
|   ├── src/                    # Frontend source code
│   ├── backend.py              # Backend server
├── roles/                      # Role definitions in PPTAgent
├── prompts/                    # Project prompts
```

## Quick Start 🚀
For a quick test, use the example in `resource/` to save preprocessing time.

### Docker 🐳

> [!NOTE]
> When using a remote server, ensure both ports `8088` and `9297` are forwarded.

```bash
docker pull forceless/pptagent
docker run -dt --gpus all --ipc=host --name pptagent \
  -e OPENAI_API_KEY='your_key' \
  -p 9297:9297 \
  -p 8088:8088 \
  -v $HOME:/root \
  forceless/pptagent
```

You can monitor progress with `docker logs -f pptagent`.


### Setup 🛠

1. Install Python dependencies

```sh
# Python dependencies
pip install -r requirements.txt
```

2. Install system dependencies

> [!NOTE]
> You can skip this step to start quickly if you only want a quick test.

```sh
# LibreOffice for PPT processing
sudo apt install libreoffice

# Node.js v22.x for frontend, other versions may work but not tested
sudo apt install -y nodejs
# conda install -c conda-forge nodejs

# Poppler utils for PDF processing
sudo apt install poppler-utils
# conda install -c conda-forge poppler
```

3. Optional: Install LaTeX for baseline comparison

```sh
sudo apt install texlive
```

### Usage 🖥️

> [!IMPORTANT]
> You should initialize the language and vision models in `llms.py` and set `PYTHONPATH=PPTAgent/src:$PYTHONPATH`.

Example initialization:
```python
llms.language_model = LLM(model="gpt-4o-2024-08-06")  # OPENAI Service
# or use a model hosted by a serving framework
llms.language_model = LLM(
    model="Qwen2.5-72B-Instruct-GPTQ-Int4", api_base="http://124.16.138.143:7812/v1"
)
```



1. **Launch Backend:**

```sh
python backend.py
```

API Endpoints:
- `/api/upload`: POST, create a presentation generation task, returns task ID.
- `/api/download`: GET, download the generated presentation by task ID.
- `/`: GET, check backend status.

2. **Using PPTAgent:**

- **With Frontend:**
  - Update `axios.defaults.baseURL` in `src/main.js` as printed by `backend.py`.
  ```sh
  cd pptagent_ui
  npm install
  npm run serve
  ```

- **With Code:**
  ```python
  ppt_gen("2024-12-27|5215990c-9d9e-4f50-b7bc-d8633f072e6b", True)
  ```

- Refer to `experiments.py` for large-scale generation.

## FAQ ❓

1. **Presentation Parsing Error:**

    While complex shapes (e.g., freeforms) aren't fully supported, our program is designed to handle such cases gracefully.

2. **Generated Presentation Quality Issues:**

    This project focuses on transferring human expertise embedded in well-designed presentations to the generated output. To achieve this, it is crucial to ensure that the uploaded presentation is of high quality.

3. **Generation Failure:**
    Models with <30B parameters may not perform adequately. Refer to our paper for performance analysis.

4. **Platform Support**:
    Currently, only Linux is officially supported. Community contributions for other platforms are welcome.

For more technical issues, please first verify your Python and system environment, and check existing issues for similar reports.

If the problem persists, we will promptly respond to such issues when detailed program logs are provided.

## Experiments Reproduction 🔍 (WIP)

### Download Dataset 📥

```python
python src/experiment/download_dataset.py
```

### Generation 🧪

- **Generate from scratch:**
  ```sh
  python experiments.py
  ```

- **Rebuild from saved history:**
  ```sh
  python rebuild.py rebuild_all --out_filename "final.pptx"
  ```

### Evaluation 📊

1. **Convert PPTX to images for evaluation:**
   ```sh
   python evals.py pptx2images
   ```

2. **Evaluate generated presentations:**
   ```sh
   python evals.py eval_experiment -s 0 -j 0
   ```
