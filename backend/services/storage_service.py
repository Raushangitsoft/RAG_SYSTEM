import hashlib
import shutil
from pathlib import Path
from typing import Optional

import aiofiles
import structlog

from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class StorageService:
    """Local disk document storage service (replaces MinIO)."""

    def __init__(self):
        self.base_path = Path(settings.documents_base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def get_document_path(self, department: str, doc_id: str, version: int, filename: str) -> Path:
        """Get the storage path for a document."""
        folder = self.base_path / department / str(doc_id)
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"v{version}_{filename}"

    async def save_file(
        self,
        file_content: bytes,
        department: str,
        doc_id: str,
        version: int,
        filename: str,
    ) -> tuple[str, str]:
        """
        Save file to local disk.
        Returns (file_path, content_hash)
        """
        file_path = self.get_document_path(department, doc_id, version, filename)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)

        content_hash = hashlib.sha256(file_content).hexdigest()
        logger.info("File saved", path=str(file_path), size=len(file_content))
        return str(file_path), content_hash

    async def read_file(self, file_path: str) -> bytes:
        """Read a file from local disk."""
        async with aiofiles.open(file_path, "rb") as f:
            return await f.read()

    def delete_file(self, file_path: str) -> bool:
        """Delete a file from local disk."""
        path = Path(file_path)
        if path.exists():
            path.unlink()
            # Remove empty parent dirs
            try:
                path.parent.rmdir()
            except OSError:
                pass
            logger.info("File deleted", path=file_path)
            return True
        return False

    def file_exists(self, file_path: str) -> bool:
        return Path(file_path).exists()

    def get_file_size(self, file_path: str) -> Optional[int]:
        path = Path(file_path)
        return path.stat().st_size if path.exists() else None

    async def compute_hash(self, file_content: bytes) -> str:
        return hashlib.sha256(file_content).hexdigest()

    def list_department_files(self, department: str) -> list[str]:
        """List all files in a department folder."""
        dept_path = self.base_path / department
        if not dept_path.exists():
            return []
        return [str(p) for p in dept_path.rglob("*") if p.is_file()]


_storage_service = None


def get_storage_service() -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
