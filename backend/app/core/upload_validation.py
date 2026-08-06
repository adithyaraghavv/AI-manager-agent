"""Upload validation: file type + size limits.

Was previously unenforced — any file of any size could be uploaded. These
limits mirror what the team's existing document tooling already enforces.
"""
ALLOWED_EXTENSIONS = {"docx", "doc", "pdf", "xlsx", "pptx", "txt"}
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


class InvalidUpload(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def validate_upload(content: bytes, extension: str) -> None:
    ext = extension.lstrip(".").lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidUpload(
            f"File type '.{ext}' is not allowed. Accepted types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    if len(content) == 0:
        raise InvalidUpload("Uploaded file is empty.")
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        max_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
        raise InvalidUpload(f"File too large. Maximum allowed size is {max_mb} MB.")
