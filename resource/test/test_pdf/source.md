# *PPTAgent*: Generating and Evaluating Presentations Beyond Text-to-Slides

Hao Zheng1,2,*, Xinyan Guan1,2,∗ , Hao Kong3 , Jia Zheng1 , Hongyu Lin1

Yaojie Lu1 , Ben He1,2 , Xianpei Han1 , Le Sun1

1Chinese Information Processing Laboratory, Institute of Software, Chinese Academy of Sciences

2University of Chinese Academy of Sciences

3Shanghai Jiexin Technology

{zhenghao2022,guanxinyan2022,zhengjia,hongyu,luyaojie}@iscas.ac.cn

{xianpei,sunle}@iscas.ac.cn haokong@knowuheart.com

# Abstract

arXiv:2501.03936v1 [cs.AI] 7 Jan 2025

Automatically generating presentations from documents is a challenging task that requires balancing content quality, visual design, and structural coherence. Existing methods primarily focus on improving and evaluating the content quality in isolation, often overlooking visual design and structural coherence, which limits their practical applicability. To address these limitations, we propose*PPTAgent*, which comprehensively improves presentation generation through a two-stage, edit-based approach inspired by human workflows. *PPTAgent* first analyzes reference presentations to understand their structural patterns and content schemas, then drafts outlines and generates slides through code actions to ensure consistency and alignment. To comprehensively evaluate the quality of generated presentations, we further introduce *PPTEval*, an evaluation framework that assesses presentations across three dimensions: Content, Design, and Coherence. Experiments show that*PPTAgent* significantly outperforms traditional automatic presentation generation methods across all three dimensions. The code and data are available at https://github.com/icip-cas/PPTAgent.

# 1 Introduction

Presentations are a widely used medium for information delivery, valued for their visual effectiveness in engaging and communicating with audiences. However, creating high-quality presentations requires a captivating storyline, visually appealing layouts, and rich, impactful content (Fu et al., 2022). Consequently, creating well-rounded presentations requires advanced presentation skills and significant effort. Given the inherent complexity of presentation creation, there is growing interest in automating the presentation generation process (Mondal et al., 2024; Maheshwari et al.,

![](_page_0_Figure_14.jpeg)

Figure 1: Comparison between our*PPTAgent* approach (left) and the conventional abstractive summarization method (right). Our method, which begins by editing a reference slide, aligns more closely with the human presentation creation process.

2024) by leveraging the generalization capabilities of large language models (LLM).

Existing approaches often adopt an end-to-end text-generation paradigm, focusing solely on textual content while neglecting layout design and presentation structures, making them impractical for real-world applications. For example, as shown in Figure 1, prior studies (Mondal et al., 2024; Sefid et al., 2021) treat presentation generation as an abstractive summarization task, focus primarily on textual content while overlooking the interactive nature of presentations. This results in simplistic and visually uninspiring outputs that fail to engage audiences.

However, automatically creating visually rich and structurally clear presentations remains challenging due to the complexity of data formats and the lack of effective evaluation frameworks. First, most presentations are saved in PowerPoint's XML format, which is inherently tedious and redundant (Gryk, 2022). This complex format poses signifi-

<sup>*</sup> These authors contributed equally

![](_page_1_Figure_0.jpeg)

*Stage Ⅰ: Presentation Analysis*

*Stage Ⅱ: Presentation Generation*

Figure 2: Overview of the *PPTAgent* workflow. *Stage I: Presentation Analysis* involves analyzing the input presentation to cluster slides into groups and extract their content schemas. *Stage II: Presentation Generation* generates new presentations guided by the outline, incorporating feedback mechanisms to ensure robustness.

cant challenges for LLMs in interpreting the presentation layout and structure, let alone generating appealing slides in an end-to-end fashion. Second, and more importantly, the absence of comprehensive evaluation frameworks exacerbates this issue. Current metrics like perplexity and ROUGE (Lin, 2004) fail to capture essential aspects of presentation quality such as narrative flow, visual design, and content impact. Moreover, ROUGE-based evaluation tends to reward excessive textual alignment with input documents, undermining the brevity and clarity crucial for effective presentations. These limitations highlight the urgent need for advancements in automated presentation generation, particularly in enhancing visual design and developing comprehensive evaluation frameworks.

Rather than creating complex presentations from scratch in a single pass, presentations are typically created by selecting exemplary slides as references and then summarizing and transferring key content onto them (Duarte, 2010). Inspired by this process, we design *PPTAgent* to decompose presentation generation into an iterative, edit-based workflow, as illustrated in Figure 2. In the first stage, given a document and a reference presentation,*PPTAgent* analyzes the reference presentations to extract semantic information, providing the textual description that identifies the purpose and data model of each slide. In the Presentation Generation stage, *PPTAgent* generates a detailed

presentation outline and assigns specific document sections and reference slides to each slide. For instance, the framework selects the opening slide as the reference slide to present meta-information, such as the title and icon. *PPTAgent* offers a suite of editing action APIs that empower LLMs to dynamically modify the reference slide. By breaking down the process into discrete stages rather than end-to-end generation, this approach ensures consistency, adaptability, and seamless handling of complex formats.

To comprehensively evaluate the quality of generated presentations, we propose *PPTEval*, a multidimensional evaluation framework. Inspired by Chen et al. (2024a) and Kwan et al. (2024),*PPTEval* leverages the MLLM-as-a-judge paradigm to enable systematic and scalable evaluation. Drawing from Duarte (2010), we categorized presentation quality into three dimensions: Content, Design, and Coherence, providing both quantitative scores and qualitative feedback for each dimension. Our human evaluation studies validated the reliability and effectiveness of*PPT Eval* PPT .

Results demonstrate that our method effectively generates high-quality presentations, achieving an average score of 3.67 across the three dimensions evaluated by *PPTEval*. These results, covering a diverse range of domains, highlight a high success rate of 97.8%, showcasing the versatility and robustness of our approach.

Our main contributions can be summarized as follows:

- We propose *PPTAgent*, a novel framework that redefines automatic presentation generation as an edit-based workflow guided by reference presentations.
- We introduce *PPTEval*, the first comprehensive evaluation framework that assesses presentations across three key dimensions: Content, Design, and Coherence.
- We publicly released the *PPTAgent* and *PPTEval* codebase, along with a curated presentation dataset, to facilitate future research in automatic presentation generation.

# 2 PPTAgent

In this section, we first establish the formulation of the presentation generation task. Subsequently, we describe the framework of our proposed*PPTAgent*, which operates in two distinct stages. In stage I, we analyze the reference presentation by clustering similar slides and extracting their content schemas. This process aims to enhance the expressiveness of the reference presentation, thereby facilitating subsequent presentation generation. In stage II, given an input document and the analyzed reference presentation, we aim to select the most suitable slides and generate the target presentation through an interactive editing process based on the selected slides. An overview of our proposed workflow is illustrated in Figure 2.

### 2.1 Problem Formulation

*PPTAgent* is designed to generate an engaging presentation via an edit-based process. We will provide formal definitions for both*PPTAgent* and the conventional method, illustrating their divergence.

The conventional method for creating each slide S can be described in Equation 1, where n represents the number of elements on the slide, and C denotes the source content composed of sections and figures. Each element on the slide, ei , is defined by its type, content, and styling attributes, such as (Textbox, "Hello", {border,size, position, . . . }).

$${\mathbf{S}}=\sum_{i=1}^{n}e_{i}=f(C)\qquad\qquad(1)$$

Compared to the conventional method, *PPTAgent* adopts an edit-based generation

paradigm for creating new slides, addressing challenges in processing spatial relationships and designing styles. This approach generates a sequence of actions to modify existing slides. Within this paradigm, both the input document and the reference presentation serve as inputs. This process can be described as Equation 2, where m represents the number of generated actions. Each action ai represents a line of executable code, and Rj is the reference slide being edited.

$$A=\sum_{i=1}^{m}a_{i}=f\left(C\mid R_{j}\right)\qquad\qquad(2)$$

#### 2.2 Stage I: Presentation Analysis

To facilitate presentation generation, we first cluster slides in the reference presentation and extract their content schemas. This structured semantic representation helps LLMs determine which slides to edit and what content to convey in each slide.

Slide Clustering Slides can be categorized into two main types based on their functionalities: slides that support the structure of the presentation (e.g., opening slides) and slides that convey specific content (e.g., bullet-point slides). We employ different clustering algorithms to effectively cluster slides in the presentation based on their textual or visual characteristics. For structural slides, we leverage LLMs to infer the functional role of each slide and group them accordingly, as these slides often exhibit distinctive textual features. For the remaining slides, which primarily focus on presenting specific content, we employ a hierarchical clustering approach leveraging image similarity. For each cluster, we infer the layout patterns of each cluster using MLLMs. Further details regarding this method can be found in Appendix C.

Schema Extraction After clustering slides to facilitate the selection of slide references, we further analyzed their content schemas to ensure purposeful alignment of the editing. Given the complexity and fragmentation of real-world slides, we utilized the context perception capabilities of LLMs (Chen et al., 2024a) to extract diverse content schemas. Specifically, we defined an extraction framework where each element is represented by its category, modality, and content. Based on this framework, the schema of each slide was extracted through LLMs' instruction-following and structured output capabilities. Detailed instructions are provided in Appendix E.

### 2.3 Stage II: Presentation Generation

In this stage, we begin by generating an outline that specifies the reference slide and relevant content for each slide in the new presentation. For each slide, LLMs iteratively edit the reference slide using interactive executable code actions to complete the generation process.

Outline Generation Following human preferences, we instruct LLMs to create a structured outline composed of multiple entries. Each entry specifies the reference slide, relevant document section indices, as well as the title and description of the new slide. By utilizing the planning and summarizing capabilities of LLMs, we provide both the document and semantic information extracted from the reference presentation to generate a coherent and engaging outline for the new presentation, which subsequently orchestrates the generation process.

Slide Generation Guided by the outline, the slide generation process iteratively edits a reference slide to produce the new slide. To enable precise manipulation of slide elements, we implement five specialized APIs that allow LLMs to edit, remove, and duplicate text elements, as well as edit and remove visual elements. To further enhance the comprehension of slide structure, inspired by Feng et al. (2024) and Tang et al. (2023), we convert slides from their raw XML format into an HTML representation, which is more interpretable for LLMs. For each slide, LLMs receive two types of input: text retrieved from the source document based on section indices, and captions of available images. The new slide content is then generated following the guidance of the content schema.

Subsequently, LLMs leverage the generated content, HTML representation of the reference slide, and API documentation to produce executable editing actions. These actions are executed in a REPL1 environment, where the system detects errors during execution and provides real-time feedback for self-correction. The self-correction mechanism leverages intermediate results to iteratively refine the editing actions, enhancing the robustness of the generation process.

Figure 3: This figure illustrates the evaluation process in*PPTEval*, which assesses three key dimensions: content, design, and coherence. Content evaluates the quality of text and images within the slides. Design examines the visual consistency and appeal. Coherence focuses on the logical flow of the presentation. Each dimension is rated on a scale from 1 to 5, with detailed feedback provided for improvement.

# 3 Experiment

# 3.1 Dataset

Data Collection Existing presentation datasets, such as Mondal et al. (2024); Sefid et al. (2021); Sun et al. (2021); Fu et al. (2022), have two main issues. First, they are mostly stored in PDF or JSON formats, which leads to a loss of semantic information, such as structural relationships and styling attributes of elements. Additionally, these datasets are primarily derived from academic reports, limiting their diversity. To address these limitations, we introduce *Zenodo10K*, a new dataset sourced from Zenodo (European Organization For Nuclear Research and OpenAIRE, 2013), an open digital repository hosting diverse artifacts from different domains. We have curated 10,448 presentations from this source and made them publicly available to support further research. Following Mondal et al. (2024), we sampled 50 presentations across five domains to serve as reference presentations. Additionally, we collected 50 documents from the same domains to be used as input documents. Details of the sampling criteria are provided in Appendix A.

Data Preprocessing We utilized VikParuchuri (2023) to extract both textual and visual content from the documents. The extracted textual content was then organized into sections using Qwen2.5- 72B-Instruct (Yang et al., 2024). For the visual content, captions were generated using Qwen2-VL-72B-Instruct (Wang et al., 2024a). To minimize redundancy, we identified and removed duplicate images if their image embeddings had a cosine sim-

| Domain | Document |  |  | Presentation |  |
| --- | --- | --- | --- | --- | --- |
|  | #Chars | #Figs | #Chars | #Figs | #Pages |
| Culture | 12,708 | 2.9 | 6,585 | 12.8 | 14.3 |
| Education | 12,305 | 5.5 | 3,993 | 12.9 | 13.9 |
| Science | 16,661 | 4.8 | 5,334 | 24.0 | 18.4 |
| Society | 13,019 | 7.3 | 3,723 | 9.8 | 12.9 |
| Tech | 18,315 | 11.4 | 5,325 | 12.9 | 16.8 |

Table 1: Statistics of the dataset used in our experiments, detailing the number of characters ('#Chars') and figures ('#Figs'), as well as the number of pages ('#Pages').
