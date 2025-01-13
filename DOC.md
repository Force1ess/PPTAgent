# Documentation 📝

This documentation provides an overview of the project structure, setup instructions, usage guidelines, and steps for reproducing experiments.

Table of Contents
=================
- [File Structure 📂](#file-structure-)
- [Quick Start 🚀](#quick-start-)
  - [Setup 🛠](#setup-)
  - [Usage 🖥️](#usage-️)
- [Experiments Reproduction 🔍 (WIP)](#experiments-reproduction--wip)
  - [Generation 🧪](#generation-)
  - [Evaluation 📊](#evaluation-)

## File Structure 📂

```
PPTAgent/
|-- data/                       # Data for the project, saved like data/topic/filetype/filename/original.filetype
├── src/
│   ├── apis.py                 # API and CodeExecutor of PPTAgent
│   ├── backend.py              # Backend server
│   ├── crawler.py              # Data crawler
│   ├── preprocess.py           # Data preprocessing
│   ├── llms.py                 # LLM services initialization
│   ├── presentation.py         # PPTX parsing and manipulation
│   ├── multimodal.py           # Image information extraction
│   ├── induct.py               # Presentation analysis (Stage Ⅰ)
│   ├── pptgen.py               # Presentation generation (Stage Ⅱ)
│   ├── model_utils.py          # Machine Learning utilities
│   ├── utils.py                # General utilities
├── pptagent_ui/                # Frontend code
├── roles/                      # Role definitions in PPTAgent
├── prompts/                    # Project prompts
```

## Quick Start 🚀

### Setup 🛠

- **Install prerequisites:**

```sh
# Python dependencies
pip install -r requirements.txt

# LibreOffice for PPT processing
sudo apt install libreoffice  # Linux
# brew install libreoffice    # macOS

# Poppler utils for PDF processing
sudo apt install poppler-utils  # Linux
# brew install poppler         # macOS
```

- Optional: Install LaTeX for baseline comparison

```sh
# sudo apt install texlive     # Linux
# brew install texlive         # macOS
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
  yarn serve
  ```

- **With Code:**
  ```python
  ppt_gen("2024-12-27|5215990c-9d9e-4f50-b7bc-d8633f072e6b", True)
  ```

- Refer to `experiments.py` for large-scale generation.

## Experiments Reproduction 🔍 (WIP)

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
