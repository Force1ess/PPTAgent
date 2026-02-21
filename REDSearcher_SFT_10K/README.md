---
dataset_info:
  features:
  - name: meta
    struct:
    - name: question
      dtype: string
    - name: answer
      dtype: string
    - name: language
      dtype: string
  - name: messages
    list:
    - name: role
      dtype: string
    - name: content
      dtype: string
  - name: system_prompt
    dtype: string
  splits:
  - name: train
    num_bytes: 2152970840
    num_examples: 10001
  download_size: 1017289914
  dataset_size: 2152970840
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*
---
