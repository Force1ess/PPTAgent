#!/usr/bin/env python3
"""DeepPresenter CLI - Terminal interface for PPT generation"""

import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Annotated

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from deeppresenter.main import AgentLoop, InputRequest
from deeppresenter.utils.config import DeepPresenterConfig
from deeppresenter.utils.constants import PACKAGE_DIR

app = typer.Typer(help="DeepPresenter - Agentic PowerPoint Generation")
console = Console()

CONFIG_DIR = Path.home() / ".config" / "deeppresenter"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
MCP_FILE = CONFIG_DIR / "mcp.json"


def ensure_config_dir():
    """Ensure config directory exists"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def is_onboarded() -> bool:
    """Check if user has completed onboarding"""
    return CONFIG_FILE.exists() and MCP_FILE.exists()


def load_example_configs() -> tuple[dict, list]:
    """Load example config files from package"""
    config_example = PACKAGE_DIR / "config.yaml.example"
    mcp_example = PACKAGE_DIR / "mcp.json"

    with open(config_example) as f:
        config_data = yaml.safe_load(f)

    with open(mcp_example) as f:
        mcp_data = json.load(f)

    return config_data, mcp_data


def prompt_llm_config(name: str, optional: bool = False) -> dict | None:
    """Prompt user for LLM configuration"""
    if optional:
        if not Confirm.ask(f"Configure {name}?", default=False):
            return None

    console.print(f"\n[bold cyan]Configuring {name}[/bold cyan]")

    base_url = Prompt.ask("Base URL")
    model = Prompt.ask("Model name")
    api_key = Prompt.ask("API key", password=True)

    config = {
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
    }

    return config


def check_playwright_browsers():
    """Check if Playwright browsers are installed, install if not"""
    import subprocess

    console.print("\n[bold cyan]Checking Playwright browsers...[/bold cyan]")

    try:
        # Try to run playwright install
        result = subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode == 0:
            console.print("[green]✓[/green] Playwright browsers installed")
            return True
        else:
            console.print(
                f"[yellow]⚠[/yellow] Failed to install Playwright browsers: {result.stderr}"
            )
            return False

    except subprocess.TimeoutExpired:
        console.print("[yellow]⚠[/yellow] Playwright installation timed out")
        return False
    except FileNotFoundError:
        console.print(
            "[yellow]⚠[/yellow] Playwright not found. Installing browsers may fail."
        )
        return False
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Error installing Playwright browsers: {e}")
        return False


def check_docker_image():
    """Check if deeppresenter-sandbox image exists, pull if not"""
    import subprocess

    console.print("\n[bold cyan]Checking Docker sandbox image...[/bold cyan]")

    try:
        # Check if image exists
        result = subprocess.run(
            ["docker", "images", "-q", "deeppresenter-sandbox:0.1.0"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0 and result.stdout.strip():
            console.print(
                "[green]✓[/green] Docker image deeppresenter-sandbox:0.1.0 found"
            )
            return True

        # Image not found, try to pull
        console.print(
            "[yellow]Docker image not found, pulling from forceless/deeppresenter-sandbox...[/yellow]"
        )

        pull_result = subprocess.run(
            ["docker", "pull", "forceless/deeppresenter-sandbox:0.1.0"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if pull_result.returncode == 0:
            # Tag the pulled image
            subprocess.run(
                [
                    "docker",
                    "tag",
                    "forceless/deeppresenter-sandbox:0.1.0",
                    "deeppresenter-sandbox:0.1.0",
                ],
                capture_output=True,
                timeout=10,
            )
            console.print(
                "[green]✓[/green] Successfully pulled and tagged Docker image"
            )
            return True
        else:
            console.print(
                f"[yellow]⚠[/yellow] Failed to pull Docker image: {pull_result.stderr}"
            )
            console.print(
                "[yellow]Sandbox functionality may not work. You can pull it manually:[/yellow]"
            )
            console.print("  docker pull forceless/deeppresenter-sandbox:0.1.0")
            console.print(
                "  docker tag forceless/deeppresenter-sandbox:0.1.0 deeppresenter-sandbox:0.1.0"
            )
            return False

    except subprocess.TimeoutExpired:
        console.print("[yellow]⚠[/yellow] Docker command timed out")
        return False
    except FileNotFoundError:
        console.print(
            "[yellow]⚠[/yellow] Docker not found. Please install Docker to use sandbox features."
        )
        return False
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Error checking Docker image: {e}")
        return False


@app.command()
def onboard():
    """Configure DeepPresenter (config.yaml and mcp.json)"""
    ensure_config_dir()

    # Check if already configured
    if is_onboarded():
        console.print("[yellow]Configuration already exists.[/yellow]")
        console.print(f"Config: {CONFIG_FILE}")
        console.print(f"MCP: {MCP_FILE}")

        if not Confirm.ask(
            "\nDo you want to reconfigure (existing config will be backed up)?",
            default=False,
        ):
            console.print("[green]Keeping existing configuration.[/green]")
            return

        # Backup existing config
        import shutil
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = CONFIG_DIR / f"backup_{timestamp}"
        backup_dir.mkdir(exist_ok=True)
        shutil.copy(CONFIG_FILE, backup_dir / "config.yaml")
        shutil.copy(MCP_FILE, backup_dir / "mcp.json")
        console.print(f"[green]✓[/green] Backed up to {backup_dir}")

    console.print(
        Panel.fit(
            "[bold green]Welcome to DeepPresenter![/bold green]\n"
            "Let's configure your environment.",
            title="Onboarding",
        )
    )

    # Check Docker sandbox image
    check_docker_image()

    # Check and install Playwright browsers
    check_playwright_browsers()

    # Check if config files exist in current directory
    local_config = Path.cwd() / "deeppresenter" / "deeppresenter" / "config.yaml"
    local_mcp = Path.cwd() / "deeppresenter" / "deeppresenter" / "mcp.json"

    config_data = None
    mcp_data = None

    if local_config.exists() and local_mcp.exists():
        console.print("\n[cyan]Found existing config in current directory:[/cyan]")
        console.print(f"  • {local_config}")
        console.print(f"  • {local_mcp}")

        if Confirm.ask("\nDo you want to reuse these configurations?", default=True):
            console.print("[green]✓[/green] Reusing existing configurations")
            with open(local_config) as f:
                config_data = yaml.safe_load(f)
            with open(local_mcp) as f:
                mcp_data = json.load(f)

    # Load example configs if not reusing
    if config_data is None or mcp_data is None:
        config_data, mcp_data = load_example_configs()

        # Configure required LLMs
        console.print("\n[bold yellow]Required LLM Configurations[/bold yellow]")

        config_data["research_agent"] = prompt_llm_config("Research Agent")
        config_data["design_agent"] = prompt_llm_config("Design Agent")
        config_data["long_context_model"] = prompt_llm_config("Long Context Model")
        config_data["vision_model"] = prompt_llm_config("Vision Model")

        # Optional T2I model
        console.print("\n[bold yellow]Optional Configurations[/bold yellow]")
        t2i_config = prompt_llm_config("Text-to-Image Model", optional=True)
        if t2i_config:
            config_data["t2i_model"] = t2i_config

        # Configure MCP (optional Tavily API key)
        console.print("\n[bold cyan]MCP Configuration[/bold cyan]")
        if Confirm.ask("Configure Tavily API key for web search?", default=True):
            tavily_key = Prompt.ask("Tavily API key", password=True)
            # Update tavily key in mcp config
            for server in mcp_data:
                if server.get("name") == "search":
                    server["env"]["TAVILY_API_KEY"] = tavily_key
                    break
            else:
                raise ValueError("search server not found in mcp.json")

        # Configure MinerU API key
        if Confirm.ask("Configure MinerU API key for PDF parsing?", default=False):
            mineru_key = Prompt.ask("MinerU API key", password=True)
            for server in mcp_data:
                if server.get("name") == "any2markdown":
                    server["env"]["MINERU_API_KEY"] = mineru_key
                    break
            else:
                raise ValueError("any2markdown server not found in mcp.json")

    # Save configs
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)

    with open(MCP_FILE, "w") as f:
        json.dump(mcp_data, f, indent=2, ensure_ascii=False)

    console.print(f"\n[bold green]✓[/bold green] Configuration saved to {CONFIG_DIR}")

    # Validate LLMs
    console.print("\n[bold cyan]Validating LLM configurations...[/bold cyan]")
    try:
        config = DeepPresenterConfig.load_from_file(str(CONFIG_FILE))
        asyncio.run(config.validate_llms())
        console.print("[bold green]✓[/bold green] All LLMs validated successfully!")
    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Validation failed: {e}")
        console.print("Please check your configuration and try again.")
        sys.exit(1)


@app.command()
def generate(
    prompt: Annotated[str, typer.Argument(help="Presentation prompt/instruction")],
    files: Annotated[
        list[Path], typer.Option("--file", "-f", help="Attachment files")
    ] = None,
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Output directory")
    ] = None,
    pages: Annotated[
        str, typer.Option("--pages", "-p", help="Number of pages (e.g., '8', '5-10')")
    ] = None,
    aspect_ratio: Annotated[
        str,
        typer.Option("--aspect", "-a", help="Aspect ratio (16:9, 4:3, A1, A3, A2, A4)"),
    ] = "16:9",
    language: Annotated[
        str, typer.Option("--lang", "-l", help="Language (en/zh)")
    ] = "en",
):
    """Generate a presentation from prompt and optional files"""

    # Check onboarding
    if not is_onboarded():
        console.print(
            "[bold red]Error:[/bold red] Please run 'deeppresenter onboard' first"
        )
        sys.exit(1)

    # Validate files
    attachments = []
    if files:
        for f in files:
            if not f.exists():
                console.print(f"[bold red]Error:[/bold red] File not found: {f}")
                sys.exit(1)
            attachments.append(str(f.resolve()))

    # Create request
    request = InputRequest(
        instruction=prompt,
        attachments=attachments,
        num_pages=pages or "about 8 pages",
        powerpoint_type=aspect_ratio,
    )

    # Load config
    config = DeepPresenterConfig.load_from_file(str(CONFIG_FILE))
    config.mcp_config_file = str(MCP_FILE)

    # Run generation
    async def run():
        import uuid

        session_id = str(uuid.uuid4())[:8]

        loop = AgentLoop(
            config=config,
            session_id=session_id,
            workspace=output,
            language=language,
        )

        console.print(
            Panel.fit(
                f"[bold]Prompt:[/bold] {prompt}\n"
                f"[bold]Attachments:[/bold] {len(attachments)}\n"
                f"[bold]Workspace:[/bold] {loop.workspace}",
                title="Generation Task",
            )
        )

        try:
            async for msg in loop.run(request):
                if isinstance(msg, (str, Path)):
                    console.print(f"\n[bold green]✓[/bold green] Generated: {msg}")
                    return str(msg)
        except Exception as e:
            console.print(f"[bold red]✗[/bold red] Generation failed: {e}")
            raise

    try:
        result = asyncio.run(run())
        console.print(f"\n[bold green]Success![/bold green] Output: {result}")
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Failed:[/bold red] {e}")
        sys.exit(1)


@app.command()
def config():
    """Show current configuration"""
    if not is_onboarded():
        console.print(
            "[bold red]Not configured.[/bold red] Run 'deeppresenter onboard' first."
        )
        return

    console.print(f"\n[bold]Config file:[/bold] {CONFIG_FILE}")
    console.print(f"[bold]MCP file:[/bold] {MCP_FILE}")

    with open(CONFIG_FILE) as f:
        config_data = yaml.safe_load(f)

    console.print("\n[bold cyan]LLM Configuration:[/bold cyan]")
    for key in [
        "research_agent",
        "design_agent",
        "long_context_model",
        "vision_model",
        "t2i_model",
    ]:
        if key in config_data:
            llm = config_data[key]
            if isinstance(llm, dict):
                console.print(f"  {key}: {llm.get('model', 'N/A')}")


@app.command()
def reset():
    """Reset configuration (delete config files)"""
    if Confirm.ask(f"Delete configuration at {CONFIG_DIR}?", default=False):
        if CONFIG_DIR.exists():
            shutil.rmtree(CONFIG_DIR)
            console.print("[bold green]✓[/bold green] Configuration reset")
        else:
            console.print("[yellow]No configuration found[/yellow]")


def main():
    """Entry point for uvx"""
    app()


if __name__ == "__main__":
    main()
