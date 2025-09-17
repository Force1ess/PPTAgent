import os
from random import shuffle
from pptagent.pptgen import PPTAgent
from pptagent.llms import AsyncLLM
from pptagent.presentation.layout import Layout
from pptagent.response.pptgen import (
    EditorOutput,
    LayoutChoice,
    SlideElement,
    TemplateChoice,
)
from pptagent.utils import Config, package_join
from pptagent.presentation import Presentation
from glob import glob
from os.path import join, basename
import json
from fastmcp import FastMCP
from pptagent.utils import get_logger

logger = get_logger(__name__)


class PPTAgentServer(PPTAgent):
    roles = [
        "template_selector",
        "layout_selector",
        "coder",
    ]

    def __init__(self):
        self.mcp = FastMCP("PPTAgent")
        self.layout: Layout | None = None
        self.slides = []
        model = AsyncLLM(
            os.getenv("PPTAGENT_MODEL"),
            os.getenv("PPTAGENT_API_BASE"),
            os.getenv("PPTAGENT_API_KEY"),
        )
        if not model.to_sync().test_connection():
            msg = "Unable to connect to the model, please set the PPTAGENT_MODEL, PPTAGENT_API_BASE, and PPTAGENT_API_KEY environment variables correctly"
            logger.error(msg)
            raise Exception(msg)
        super().__init__(language_model=model, vision_model=model)
        # load templates, a directory containing pptx, json, and description for each template
        templates = glob(package_join("templates", "*/"))
        self.templates_options = []
        for template in templates:
            self.templates_options.append(
                f"<template_name>{basename(template)}</template_name>\n"
            )
            self.templates_options[-1] += (
                f"<template_description>{open(join(template, 'description.txt')).read()}</template_description>\n"
            )

        logger.info(f"{len(templates)} templates loaded")

    def register_tools(self):
        @self.mcp.tool()
        def set_template(template_name: str = "default"):
            """Select a PowerPoint template by name.

            Args:
                template_name: The name of the template to select. If no specific requirement is provided, use "default"
            """
            template_folder = package_join("templates", template_name)
            prs_config = Config(template_folder)
            prs = Presentation.from_file(
                join(template_folder, "template.pptx"), prs_config
            )
            self.set_reference(
                slide_induction=json.load(
                    open(join(template_folder, "slide_induction.json"))
                ),
                presentation=prs,
            )
            self._initialized = True

        @self.mcp.tool()
        async def retrieve_template(prs_requirements: str):
            """Retrieve the most suitable template based on presentation requirements.

            Args:
                prs_requirements: Description of the presentation requirements, could be the target audience, and the desired style of the presentation, etc.

            Returns:
                The name of the recommended template
            """
            if len(self.templates_options) == 0:
                return "default"
            _, template_selection = await self.staffs["template_selector"](
                prs_requirements=prs_requirements,
                available_templates=self.templates_options,
                response_format=TemplateChoice.response_model(self.templates_options),
            )
            return template_selection["template"]

        @self.mcp.tool()
        async def select_layout(slide_content: str, image_captions: list[str]):
            """Select the optimal layout for a slide based on given content.

            Args:
                slide_content: The abstract of the slide
                image_captions: List of image captions to be included in the slide

            Returns:
                The content schema for the selected layout
            """
            assert self._initialized, (
                "PPTAgent is not initialized, please call `set_reference` before selecting layout"
            )
            assert self.layout is None, (
                "Layout is already selected, please call `generate_slide` after selecting layout"
            )
            layouts = self.text_layouts
            if len(image_captions) > 0:
                slide_content += "\nImages:\n" + "\n".join(image_captions)
                layouts = self.multimodal_layouts

            shuffle(layouts)
            _, layout_selection = await self.staffs["layout_selector"](
                slide_content=slide_content,
                available_layouts=layouts,
                response_format=LayoutChoice.response_model(layouts),
            )
            self.layout = self.layouts[layout_selection["layout"]]
            return self.layout.content_schema

        @self.mcp.tool()
        async def generate_slide(structured_slide_content: list[SlideElement]):
            """Generate a PowerPoint slide from structured slide elements.

            Args:
                structured_slide_content: List of slide elements with their content
                should follow the content schema and adhere to
                [
                    {
                        "name": "element_name",
                        "data": ["content1", "content2", "..."]
                        // Array of strings for text elements
                        // OR array of image paths for image elements: ["/path/to/image1.jpg", "/path/to/image2.png"]
                    }
                ]

            Returns:
                Success message with slide number
            """
            assert self.layout is not None, (
                "Layout is not selected, please call `select_layout` before generating slide"
            )
            editor_output = EditorOutput(
                elements=[SlideElement(**e) for e in structured_slide_content]
            )
            self.layout.validate(editor_output, ["all"])
            if self.length_factor is not None:
                await self.layout.length_rewrite(
                    editor_output, self.length_factor, self.language_model
                )
            command_list, template_id = self._generate_commands(
                editor_output, self.layout
            )
            slide, _ = await self._edit_slide(command_list, template_id)
            self.slides.append(slide)
            return f"Slide {len(self.slides):02d} generated successfully"

        @self.mcp.tool()
        async def save_generated_slides(pptx_path: str):
            """Save the generated slides to a PowerPoint file.

            Args:
                pptx_path: The path to save the PowerPoint file
            """
            assert len(self.slides), (
                "No slides generated, please call `generate_slide` first"
            )
            os.makedirs(os.path.dirname(pptx_path), exist_ok=True)
            self.empty_prs.slides = self.slides
            self.empty_prs.save(pptx_path)
            self.slides = []
            self.layout = None
            self._initialized = False
            return f"total {len(self.empty_prs.slides)} slides saved to {pptx_path}"


def main():
    server = PPTAgentServer()
    server.register_tools()
    server.mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
