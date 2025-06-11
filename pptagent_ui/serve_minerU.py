import logging
import os
import re
import shutil
import tempfile
import uuid

import magic_pdf.model as model_config
import werkzeug.utils
from flask import Flask, jsonify, request, send_file
from magic_pdf.config.enums import SupportedPdfParseMethod
from magic_pdf.data.data_reader_writer import FileBasedDataReader, FileBasedDataWriter
from magic_pdf.data.dataset import PymuDocDataset
from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

model_config.__use_inside_model__ = True

app = Flask(__name__)
HOST = "0.0.0.0"
PORT = 9608

# 使用临时目录，程序结束时自动清理
TEMP_DIR = tempfile.mkdtemp(prefix="mineru_")
INPUT_BASE_DIR = os.path.join(TEMP_DIR, "input")
OUTPUT_BASE_DIR = os.path.join(TEMP_DIR, "output")
os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)
os.makedirs(INPUT_BASE_DIR, exist_ok=True)


def safe_filename(filename):
    """生成安全的文件名"""
    # 保留原始扩展名，但使用UUID作为文件名
    ext = os.path.splitext(filename)[1]
    safe_name = str(uuid.uuid4()) + ext
    return werkzeug.utils.secure_filename(safe_name)


def cleanup_temp_files(*file_paths):
    """清理临时文件"""
    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                if os.path.isfile(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
        except Exception as e:
            logger.warning(f"Failed to cleanup {file_path}: {e}")


def fix_markdown(md_path):
    """修复markdown中的图片链接"""
    try:
        file_name, extension = os.path.splitext(os.path.basename(md_path))
        with open(md_path, encoding="utf-8") as file:
            content = file.read()
        pattern = r"!\[(.*?)\]\((.*?)\)"

        def replace_match(match):
            img_url = f"http://{HOST}:{PORT}/img/{file_name}/{match.group(2)}"
            logger.debug(f"Replacing image URL: {match.group(2)} -> {img_url}")
            return f"![{match.group(1)}]({img_url})"

        new_content = re.sub(pattern, replace_match, content)
        return new_content
    except Exception as e:
        logger.error(f"Error fixing markdown: {e}")
        raise


def fix_img_dir(content):
    """修复图片目录路径"""
    try:
        img_pattern = r"(!\[.*?\]\()(.*?)(\))"

        def replace_image(match):
            prefix = match.group(1)
            original_path = match.group(2)
            suffix = match.group(3)

            logger.debug(f"Original path: {original_path}")
            filename = os.path.basename(original_path)
            result = f"{prefix}{filename}{suffix}"
            logger.debug(f"Fixed path: {result}")
            return result

        return re.sub(img_pattern, replace_image, content)
    except Exception as e:
        logger.error(f"Error fixing image directory: {e}")
        raise


def mineru(pdf_path, save_folder, original_filename):
    """处理PDF文件转换"""
    try:
        os.makedirs(save_folder, exist_ok=True)

        # 使用原始文件名（去掉不安全字符）用于输出目录
        name_without_extension = os.path.splitext(
            werkzeug.utils.secure_filename(original_filename)
        )[0]
        save_md_dir = os.path.join(save_folder, name_without_extension)
        save_image_dir = os.path.join(save_md_dir)

        image_writer = FileBasedDataWriter(save_image_dir)
        md_writer = FileBasedDataWriter(save_md_dir)

        reader1 = FileBasedDataReader("")
        pdf_bytes = reader1.read(pdf_path)

        ds = PymuDocDataset(pdf_bytes)

        if ds.classify() == SupportedPdfParseMethod.OCR:
            logger.info("Using OCR mode")
            infer_result = ds.apply(doc_analyze, ocr=True)
            pipe_result = infer_result.pipe_ocr_mode(image_writer)
        else:
            logger.info("Using text mode")
            infer_result = ds.apply(doc_analyze, ocr=False)
            pipe_result = infer_result.pipe_txt_mode(image_writer)

        md_content = pipe_result.get_markdown(save_image_dir)
        pipe_result.dump_md(md_writer, f"{name_without_extension}.md", save_image_dir)
        pipe_result.dump_content_list(
            md_writer, f"{name_without_extension}_content_list.json", save_image_dir
        )
        pipe_result.dump_middle_json(md_writer, f"{name_without_extension}_middle.json")

        # 修复图片路径
        md_content = fix_img_dir(md_content)
        md_file_path = os.path.join(save_md_dir, name_without_extension + ".md")
        with open(md_file_path, "w", encoding="utf-8") as file:
            file.write(md_content)

        return str(md_content)
    except Exception as e:
        logger.error(f"Error in mineru processing: {e}")
        raise


@app.route("/mineru_pdf2zip", methods=["POST"])
def convert_pdf_to_zip():
    pdf_path = None
    output_file = None
    output_zip = None

    try:
        # 验证请求
        if "pdf" not in request.files:
            return jsonify({"error": "No PDF file provided"}), 400

        pdf_file = request.files["pdf"]
        if pdf_file.filename == "":
            return jsonify({"error": "Empty filename"}), 400

        if not pdf_file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "File must be a PDF"}), 400

        # 保存上传文件
        original_filename = pdf_file.filename
        safe_name = safe_filename(original_filename)
        pdf_path = os.path.join(INPUT_BASE_DIR, safe_name)
        pdf_file.save(pdf_path)
        logger.info(f"PDF saved to: {pdf_path}")

        # 处理PDF
        mineru(
            pdf_path=pdf_path,
            save_folder=OUTPUT_BASE_DIR,
            original_filename=original_filename,
        )

        # 创建ZIP文件
        output_name = os.path.splitext(
            werkzeug.utils.secure_filename(original_filename)
        )[0]
        output_file = os.path.join(OUTPUT_BASE_DIR, output_name)
        output_zip = os.path.join(OUTPUT_BASE_DIR, f"{output_name}.zip")

        if not os.path.exists(output_file):
            return (
                jsonify({"error": "Processing failed - output directory not found"}),
                500,
            )

        shutil.make_archive(output_zip[:-4], "zip", output_file)

        if not os.path.exists(output_zip):
            return jsonify({"error": "Failed to create ZIP file"}), 500

        logger.info(f"ZIP file created: {output_zip}")
        return send_file(
            output_zip,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{output_name}.zip",
        )

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return jsonify({"error": "Required file not found"}), 404
    except PermissionError as e:
        logger.error(f"Permission error: {e}")
        return jsonify({"error": "Permission denied"}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        # 清理临时文件
        cleanup_temp_files(pdf_path, output_file, output_zip)


@app.teardown_appcontext
def cleanup_temp_dir(_):
    """应用上下文结束时清理临时目录"""
    cleanup_temp_files(TEMP_DIR)


if __name__ == "__main__":
    try:
        app.run(host=HOST, port=PORT, debug=False)
    finally:
        # 程序结束时清理临时目录
        cleanup_temp_files(TEMP_DIR)
