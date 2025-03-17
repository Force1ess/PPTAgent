import asyncio
import hashlib
import importlib
import itertools
import json
import os
import sys
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from typing import Dict, List

import PIL.Image
import torch
from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.logger import logger
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from jinja2 import Template
from marker.models import create_model_dict

import induct
import llms
import pptgen
from model_utils import get_image_model, parse_pdf
from multimodal import ImageLabler
from presentation import Presentation
from utils import Config, is_image_path, pjoin, ppt_to_images

# constants
DEBUG = True if len(sys.argv) == 1 else False
RUNS_DIR = "runs"
STAGES = [
    "PPT Parsing",
    "PDF Parsing",
    "PPT Analysis",
    "PPT Generation",
    "Success!",
]
NUM_MODELS = 1 if len(sys.argv) == 1 else int(sys.argv[1])
DEVICE = (
    "cuda"
    if torch.cuda.is_available()
    else "mps" if torch.backends.mps.is_available() else "cpu"
)
REFINE_TEMPLATE = Template(open("prompts/document_refine.txt").read())

# models
image_model = get_image_model(device=DEVICE)
marker_model = create_model_dict(device=DEVICE, dtype=torch.float16)

# server
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
progress_store: Dict[str, Dict] = {}
active_connections: Dict[str, WebSocket] = {}
executor = ThreadPoolExecutor(max_workers=NUM_MODELS)


class ProgressManager:
    def __init__(self, task_id: str, stages: List[str], debug: bool = True):
        self.task_id = task_id
        self.stages = stages
        self.debug = debug
        self.socket = active_connections.get(task_id)
        self.failed = False
        self.current_stage = 0
        self.total_stages = len(stages)

    def run_stage(self, func, *args, **kwargs):
        if self.task_id not in active_connections:
            self.failed = True
        if self.failed:
            return
        try:
            self.report_progress()
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            self.fail_stage(str(e))

    def report_progress(self):
        self.current_stage += 1
        progress = int((self.current_stage / self.total_stages) * 100)
        asyncio.run(
            send_progress(
                self.socket,
                f"Stage: {self.stages[self.current_stage - 1]}",
                progress,
            )
        )

    def fail_stage(self, error_message: str):
        asyncio.run(
            send_progress(
                self.socket,
                f"{self.stages[self.current_stage]} Error: {error_message}",
                100,
            )
        )
        self.failed = True
        active_connections.pop(self.task_id, None)
        if self.debug:
            logger.error(
                f"{self.task_id}: {self.stages[self.current_stage]} Error: {error_message}"
            )


@app.post("/api/upload")
async def create_task(
    pptxFile: UploadFile = File(None),
    pdfFile: UploadFile = File(None),
    topic: str = Form(None),
    numberOfPages: int = Form(...),
    selectedModel: str = Form(...),
):
    task_id = datetime.now().strftime("20%y-%m-%d") + "/" + str(uuid.uuid4())
    logger.info(f"task created: {task_id}")
    os.makedirs(pjoin(RUNS_DIR, task_id))
    task = {
        "numberOfPages": numberOfPages,
        "pptx": "default_template",
        "model": selectedModel,
    }
    if pptxFile is not None:
        pptx_blob = await pptxFile.read()
        pptx_md5 = hashlib.md5(pptx_blob).hexdigest()
        task["pptx"] = pptx_md5
        pptx_dir = pjoin(RUNS_DIR, "pptx", pptx_md5)
        if not os.path.exists(pptx_dir):
            os.makedirs(pptx_dir, exist_ok=True)
            with open(pjoin(pptx_dir, "source.pptx"), "wb") as f:
                f.write(pptx_blob)
    if pdfFile is not None:
        pdf_blob = await pdfFile.read()
        pdf_md5 = hashlib.md5(pdf_blob).hexdigest()
        task["pdf"] = pdf_md5
        pdf_dir = pjoin(RUNS_DIR, "pdf", pdf_md5)
        if not os.path.exists(pdf_dir):
            os.makedirs(pdf_dir, exist_ok=True)
            with open(pjoin(pdf_dir, "source.pdf"), "wb") as f:
                f.write(pdf_blob)
    if topic is not None:
        task["pdf"] = topic
    progress_store[task_id] = task
    executor.submit(ppt_gen, task_id)
    return {"task_id": task_id.replace("/", "|")}


async def send_progress(websocket: WebSocket, status: str, progress: int):
    if websocket is None:
        logger.info(f"websocket is None, status: {status}, progress: {progress}")
        return
    await websocket.send_json({"progress": progress, "status": status})


@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    task_id = task_id.replace("|", "/")
    if task_id in progress_store:
        await websocket.accept()
    else:
        raise HTTPException(status_code=404, detail="Task not found")
    active_connections[task_id] = websocket
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("websocket disconnected", task_id)
        active_connections.pop(task_id, None)


def topic_generate(topic: str):
    prompt = (
        "Please generate a detailed presentation planning document about "
        + topic
        + ", detail to 1000 words."
        + "Follow the format of the example output.\n"
        + """
{
    "title": "title of document",
    "sections": [
        {
            "title": "title of section1",
            "subsections": [
                {
                    "title": "title of subsection1.1",
                    "content": "content of subsection1.1"
                },
                {
                    "title": "title of subsection1.2",
                    "content": "content of subsection1.2"
                }
            ]
        },
        {
            "title": "title of section2",
            "subsections": [
                {
                    "title": "title of subsection2.1",
                    "content": "content of subsection2.1"
                }
            ]
        }
    ]
}
"""
    )
    text = llms.language_model(prompt, return_json=True)
    assert isinstance(text, dict), "Text is not in JSON format"
    return text


@app.get("/api/download")
def download(task_id: str):
    task_id = task_id.replace("|", "/")
    if not os.path.exists(pjoin(RUNS_DIR, task_id)):
        raise HTTPException(status_code=404, detail="Task not created yet")
    file_path = pjoin(RUNS_DIR, task_id, "final.pptx")
    if os.path.exists(file_path):
        return FileResponse(
            file_path,
            media_type="application/pptx",
            headers={"Content-Disposition": f"attachment; filename=pptagent.pptx"},
        )
    raise HTTPException(status_code=404, detail="Task not finished yet")


@app.post("/api/feedback")
async def feedback(request: Request):
    body = await request.json()
    feedback = body.get("feedback")
    task_id = body.get("task_id")

    with open(f"runs/feedback/{task_id}.txt", "w") as f:
        f.write(feedback)
    return {"message": "Feedback submitted successfully"}


@app.get("/")
def hello():
    return {"message": "Hello, World!"}


def ppt_gen(task_id: str, rerun=False):
    if DEBUG:
        importlib.reload(induct)
        importlib.reload(pptgen)
    if rerun:
        task_id = task_id.replace("|", "/")
        active_connections[task_id] = None
        progress_store[task_id] = json.load(open(pjoin(RUNS_DIR, task_id, "task.json")))
    for _ in range(100):
        if task_id in active_connections:
            break
        time.sleep(0.02)
    else:
        progress_store.pop(task_id)
        return
    task = progress_store.pop(task_id)
    pptx_md5 = task["pptx"]
    pdf_md5 = task["pdf"]
    generation_config = Config(pjoin(RUNS_DIR, task_id))
    pptx_config = Config(pjoin(RUNS_DIR, "pptx", pptx_md5))
    json.dump(task, open(pjoin(generation_config.RUN_DIR, "task.json"), "w"))

    if len(pdf_md5) != 32:
        pdf_dir = pjoin(RUNS_DIR, "pdf", pdf_md5)
        if not os.path.exists(pdf_dir + "/refined_doc.json"):
            os.makedirs(pdf_dir, exist_ok=True)
            json.dump(
                topic_generate(task["pdf"]),
                open(pjoin(pdf_dir, "refined_doc.json"), "w"),
            )

    progress = ProgressManager(task_id, STAGES)
    parsedpdf_dir = pjoin(RUNS_DIR, "pdf", pdf_md5)
    ppt_image_folder = pjoin(pptx_config.RUN_DIR, "slide_images")

    asyncio.run(
        send_progress(active_connections[task_id], "task initialized successfully", 10)
    )

    try:
        # ppt parsing
        presentation = Presentation.from_file(
            pjoin(pptx_config.RUN_DIR, "source.pptx"), pptx_config
        )
        if not os.path.exists(ppt_image_folder) or len(
            os.listdir(ppt_image_folder)
        ) != len(presentation):
            ppt_to_images(pjoin(pptx_config.RUN_DIR, "source.pptx"), ppt_image_folder)
            assert len(os.listdir(ppt_image_folder)) == len(presentation) + len(
                presentation.error_history
            ), "Number of parsed slides and images do not match"

            for err_idx, _ in presentation.error_history:
                os.remove(pjoin(ppt_image_folder, f"slide_{err_idx:04d}.jpg"))
            for i, slide in enumerate(presentation.slides, 1):
                slide.slide_idx = i
                os.rename(
                    pjoin(ppt_image_folder, f"slide_{slide.real_idx:04d}.jpg"),
                    pjoin(ppt_image_folder, f"slide_{slide.slide_idx:04d}.jpg"),
                )

        labler = ImageLabler(presentation, pptx_config)
        progress.run_stage(labler.caption_images)

        # pdf parsing
        if not os.path.exists(pjoin(parsedpdf_dir, "source.md")) and not os.path.exists(
            pjoin(parsedpdf_dir, "refined_doc.json")
        ):
            text_content = progress.run_stage(
                parse_pdf,
                pjoin(RUNS_DIR, "pdf", pdf_md5, "source.pdf"),
                parsedpdf_dir,
                marker_model,
            )
        else:
            if not os.path.exists(pjoin(parsedpdf_dir, "refined_doc.json")):
                text_content = open(pjoin(parsedpdf_dir, "source.md")).read()
            progress.report_progress()

        # doc refine and caption
        if not os.path.exists(pjoin(parsedpdf_dir, "image_caption.json")):
            caption_prompt = open("prompts/caption.txt").read()
            images = {}
            for k in os.listdir(parsedpdf_dir):
                if is_image_path(k):
                    try:
                        images[pjoin(parsedpdf_dir, k)] = [
                            llms.vision_model(
                                caption_prompt, [pjoin(parsedpdf_dir, k)]
                            ),
                            PIL.Image.open(pjoin(parsedpdf_dir, k)).size,
                        ]
                    except Exception as e:
                        logger.error(f"Error captioning image {k}: {e}")
            json.dump(
                images,
                open(pjoin(parsedpdf_dir, "image_caption.json"), "w"),
                ensure_ascii=False,
                indent=4,
            )
        else:
            images = json.load(open(pjoin(parsedpdf_dir, "image_caption.json")))
        if not os.path.exists(pjoin(parsedpdf_dir, "refined_doc.json")):
            doc_json = llms.language_model(
                REFINE_TEMPLATE.render(markdown_document=text_content), return_json=True
            )
            json.dump(doc_json, open(pjoin(parsedpdf_dir, "refined_doc.json"), "w"))
        else:
            doc_json = json.load(open(pjoin(parsedpdf_dir, "refined_doc.json")))

        progress.report_progress()

        # Slide Induction
        if not os.path.exists(pptx_config.RUN_DIR + "/template_images") or len(
            os.listdir(pptx_config.RUN_DIR + "/template_images")
        ) != len(presentation):
            deepcopy(presentation).save(
                pjoin(pptx_config.RUN_DIR, "template.pptx"), layout_only=True
            )
            ppt_to_images(
                pjoin(pptx_config.RUN_DIR, "template.pptx"),
                pjoin(pptx_config.RUN_DIR, "template_images"),
            )
        slide_inducter = induct.SlideInducter(
            presentation,
            ppt_image_folder,
            pjoin(pptx_config.RUN_DIR, "template_images"),
            pptx_config,
            image_model,
            "backend",
        )
        slide_induction = slide_inducter.content_induct()

        # PPT Generation
        progress.run_stage(
            pptgen.PPTAgent(llms.embedding_model, error_exit=False, retry_times=5)
            .set_reference(
                config=generation_config,
                slide_induction=slide_induction,
                presentation=presentation,
            )
            .generate_pres,
            images=images,
            doc_json=doc_json,
            num_slides=task["numberOfPages"],
        )
        logger.info(task_id, "generation finished")
        progress.report_progress()
    except Exception as e:
        progress.fail_stage(str(e))
        traceback.print_exc()


def setup_models():
    if os.path.exists("serve.json"):
        serve_config = json.load(open("serve.json"))
        llms.language_model = llms.LLM(
            serve_config["language"]["model"], serve_config["language"]["url"]
        )
        llms.vision_model = llms.LLM(
            serve_config["vision"]["model"], serve_config["vision"]["url"]
        )
    if llms.language_model.test_connection() and llms.vision_model.test_connection():
        logger.info("Primary models connected successfully")
        return

    if llms.gpt4o.test_connection():
        logger.warn("Switching to OpenAI GPT-4o models as fallback")
        llms.language_model = llms.gpt4o
        llms.vision_model = llms.gpt4o
        return
    raise RuntimeError(
        "No working model connections available. Please check OpenAI API keys and connections."
    )


if __name__ == "__main__":
    import uvicorn

    setup_models()

    ip = "0.0.0.0"
    uvicorn.run(app, host=ip, port=9297)
