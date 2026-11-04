"""Controlled file search and safe file deletion with confirmation."""
import os
import glob
import logging
from typing import Optional, List
from pathlib import Path
from pydantic import BaseModel, Field
import send2trash

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.config.settings import settings, BASE_DIR

logger = logging.getLogger("DADUS.Files")

# ==========================================
# Tool: search_files
# ==========================================
class SearchFilesInput(BaseModel):
    query: str = Field(description="Filename pattern or query to search for, e.g. '*.pdf', 'budget.xlsx'")
    directory: Optional[str] = Field(
        default=None,
        description="Directory path to search within. If omitted, searches standard user directories."
    )

class SearchFilesTool(BaseTool):
    name = "search_files"
    description = "Searches for files matching a name pattern in user documents or a directory."
    permission_level = PermissionLevel.SAFE
    args_schema = SearchFilesInput

    def execute(self, query: str, directory: Optional[str] = None) -> ToolResult:
        if directory:
            resolved_dir = Path(directory).resolve()
            # Enforce that directory is not a sensitive operating system root
            forbidden_roots = [
                Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve(),
                Path(os.environ.get("ProgramFiles", r"C:\Program Files")).resolve(),
                Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")).resolve(),
            ]
            if any(resolved_dir == r or r in resolved_dir.parents for r in forbidden_roots):
                logger.warning(f"Restricted search directory attempted: {directory}")
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    message=f"Access to system directory '{directory}' is restricted for security.",
                    error="PERMISSION_DENIED"
                )
            search_dirs = [str(resolved_dir)]
        else:
            search_dirs = settings.ALLOWED_SEARCH_ROOTS

        matches: List[str] = []

        is_latest_req = "latest" in query.lower()
        clean_q = query.lower().replace("latest", "").strip(" .?!*")
        if not clean_q and is_latest_req:
            clean_q = ""

        for sdir in search_dirs:
            if not sdir or not os.path.exists(sdir):
                continue
            try:
                # Walk with depth limit of 3 to stay fast and responsive
                for root, _, files in os.walk(sdir):
                    rel_depth = len(Path(root).relative_to(Path(sdir)).parts)
                    if rel_depth > 3:
                        continue
                    for f in files:
                        if not clean_q or clean_q in f.lower():
                            matches.append(os.path.join(root, f))
                            if len(matches) >= 30:
                                break
                    if len(matches) >= 30:
                        break
            except (PermissionError, OSError) as ex:
                logger.debug(f"Skipping directory {sdir} due to access limit: {ex}")
                continue

        if matches:
            # If latest was requested, sort by modification time descending
            if is_latest_req:
                try:
                    matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                except Exception:
                    pass

            top_name = Path(matches[0]).name
            detail_msg = f"Found {len(matches)} matching files, boss. Most recent: '{top_name}'."
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=detail_msg,
                data={"matches": matches[:15], "latest": matches[0]}
            )
        else:
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Boss, I couldn't find any files matching '{query}'.",
                data={"matches": []}
            )

# ==========================================
# Tool: delete_file_or_folder
# ==========================================
class DeleteFileInput(BaseModel):
    path: str = Field(description="Full path to the file or directory to delete.")

class DeleteFileOrFolderTool(BaseTool):
    name = "delete_file_or_folder"
    description = "Deletes a file or directory. Requires user confirmation before execution."
    permission_level = PermissionLevel.CONFIRMATION_REQUIRED
    args_schema = DeleteFileInput

    def execute(self, path: str) -> ToolResult:
        logger.info(f"Executing confirmed deletion of: {path}")
        target = Path(path).resolve()

        # Prevent deletion of protected roots or user home directory root
        forbidden_targets = [
            Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve(),
            Path.home().resolve(),
            Path(BASE_DIR).resolve(),
        ]
        if target in forbidden_targets or any(target == f for f in forbidden_targets):
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Deletion of protected root or system directory '{target.name}' is prohibited.",
                error="PERMISSION_DENIED"
            )

        if not target.exists():
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Boss, I couldn't find '{path}'.",
                error="PATH_NOT_FOUND"
            )

        try:
            # Move safely to Recycle Bin rather than hard permanent deletion
            send2trash.send2trash(str(target))
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Successfully moved '{target.name}' to the Recycle Bin, boss.",
                data={"path": str(target), "status": "recycled"}
            )
        except Exception as ex:
            logger.error(f"Failed to delete {path}: {ex}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Boss, failed to delete '{path}'.",
                error=str(ex)
            )
