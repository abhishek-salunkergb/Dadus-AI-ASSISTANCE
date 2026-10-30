"""Project finding, folder opening, and GitHub repository navigation tools."""
import os
import subprocess
import webbrowser
import logging
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.tools.apps import AppDetector
from app.config.settings import settings

logger = logging.getLogger("DADUS.Projects")

def locate_project_folder(project_name: str) -> Optional[Path]:
    """Search common developer directories for a project folder matching name."""
    clean_target = project_name.strip().lower()

    # Priority locations to check
    search_roots = [
        Path.cwd(),
        Path(r"C:\Dadus AI Agent"),
        Path.home() / "Desktop",
        Path.home() / "Documents",
        Path.home() / "Projects",
        Path.home() / "source",
        Path.home()
    ]

    # 1. Exact match in search roots
    for root in search_roots:
        if root.exists():
            direct = root / project_name
            if direct.is_dir():
                return direct

    # 2. Walk with shallow depth (max depth 2) in developer locations
    for root in search_roots:
        if not root.exists():
            continue
        try:
            for item in root.iterdir():
                if item.is_dir() and clean_target in item.name.lower():
                    return item
        except (PermissionError, OSError):
            continue

    return None

def extract_github_url_from_repo(repo_path: Path) -> Optional[str]:
    """Parse .git/config in repo_path to find GitHub remote URL."""
    git_config = repo_path / ".git" / "config"
    if not git_config.exists():
        return None

    try:
        content = git_config.read_text(encoding="utf-8", errors="ignore")
        for line in content.splitlines():
            line_str = line.strip()
            if line_str.startswith("url ="):
                raw_url = line_str.split("=", 1)[1].strip()
                # Handle git@github.com:user/repo.git
                if "git@github.com:" in raw_url:
                    parts = raw_url.split("git@github.com:")[1]
                    clean = parts.rstrip(".git")
                    return f"https://github.com/{clean}"
                elif "github.com" in raw_url:
                    clean = raw_url.rstrip(".git")
                    if not clean.startswith("http"):
                        clean = f"https://{clean}"
                    return clean
    except Exception as ex:
        logger.debug(f"Failed to read git config: {ex}")
    return None

# ==========================================
# Tool: open_folder
# ==========================================
class OpenFolderInput(BaseModel):
    folder_path: str = Field(description="Path or name of the folder to open in Windows File Explorer")

class OpenFolderTool(BaseTool):
    name = "open_folder"
    description = "Opens a specific folder in Windows File Explorer."
    permission_level = PermissionLevel.SAFE
    args_schema = OpenFolderInput

    def execute(self, folder_path: str) -> ToolResult:
        target = Path(folder_path).resolve()
        if not target.exists():
            found = locate_project_folder(folder_path)
            if found:
                target = found
            else:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    message=f"Boss, I couldn't find the folder '{folder_path}'.",
                    error="FOLDER_NOT_FOUND"
                )

        try:
            os.startfile(str(target))
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Opening folder '{target.name}' in Explorer, boss.",
                data={"path": str(target)}
            )
        except Exception as ex:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Boss, failed to open '{folder_path}'.",
                error=str(ex)
            )

# ==========================================
# Tool: find_project_and_open
# ==========================================
class FindProjectAndOpenInput(BaseModel):
    project_name: str = Field(description="Name of the project to find, e.g. 'Django project', 'Python project'")
    editor: Optional[str] = Field(default="Visual Studio Code", description="Code editor to open project in")

class FindProjectAndOpenTool(BaseTool):
    name = "find_project_and_open"
    description = "Locates a project directory on your computer and opens it in your code editor (e.g. VS Code)."
    permission_level = PermissionLevel.SAFE
    args_schema = FindProjectAndOpenInput

    def execute(self, project_name: str, editor: Optional[str] = "Visual Studio Code") -> ToolResult:
        # Strip generic words
        clean_name = project_name.lower().replace("project", "").strip()
        folder = locate_project_folder(clean_name if clean_name else project_name)

        if not folder:
            # Fallback to current project root if matching Python/Dadus
            if any(w in project_name.lower() for w in ["python", "dadus", "agent"]):
                folder = Path.cwd()
            else:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    message=f"Boss, I couldn't locate your '{project_name}'.",
                    error="PROJECT_NOT_FOUND"
                )

        # Find Editor
        editor_info = AppDetector.find_app(editor or "VS Code")
        target_path = str(folder)

        try:
            if editor_info and os.path.exists(editor_info.executable_or_path):
                subprocess.Popen([editor_info.executable_or_path, target_path], shell=False)
            else:
                # Try code command or startfile
                subprocess.Popen(["code", target_path], shell=True)

            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Found '{folder.name}' and opened it in {editor or 'VS Code'}, boss.",
                data={"project_name": folder.name, "path": target_path, "editor": editor}
            )
        except Exception as ex:
            logger.error(f"Error opening project: {ex}")
            os.startfile(target_path)
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Located '{folder.name}' and opened it, boss.",
                data={"path": target_path}
            )

# ==========================================
# Tool: open_project_github
# ==========================================
class OpenProjectGitHubInput(BaseModel):
    project_name: str = Field(description="Name or path of the project to open GitHub repository for")

class OpenProjectGitHubTool(BaseTool):
    name = "open_project_github"
    description = "Opens the GitHub repository page corresponding to a project."
    permission_level = PermissionLevel.SAFE
    args_schema = OpenProjectGitHubInput

    def execute(self, project_name: str) -> ToolResult:
        clean_name = project_name.lower().replace("project", "").strip()
        folder = locate_project_folder(clean_name if clean_name else project_name) or Path.cwd()

        github_url = extract_github_url_from_repo(folder)
        if not github_url:
            # Fallback: search GitHub for project name
            github_url = f"https://github.com/search?q={project_name.strip()}"

        try:
            webbrowser.open(github_url)
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Opening GitHub repository for '{folder.name}', boss.",
                data={"project": folder.name, "url": github_url}
            )
        except Exception as ex:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, I couldn't open the GitHub repository.",
                error=str(ex)
            )
