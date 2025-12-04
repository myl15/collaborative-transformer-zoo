"""
Input validation and sanitization for visualization requests.
"""
from pydantic import BaseModel, Field, field_validator
import re
import logging

logger = logging.getLogger(__name__)

class VisualizationRequest(BaseModel):
    """Validated request for creating a visualization."""
    model_name: str = Field(..., min_length=1, max_length=256)
    text: str = Field(..., min_length=1, max_length=2000)
    view_type: str = Field(default="head")

    @field_validator('model_name')
    @classmethod
    def validate_model_name(cls, v):
        """Ensure model_name is safe and reasonable."""
        # Allow alphanumeric, hyphens, underscores, and slashes (org/model format)
        if not re.match(r'^[a-zA-Z0-9/._-]+$', v):
            raise ValueError('model_name contains invalid characters')
        # Prevent path traversal
        if '..' in v or v.startswith('/'):
            raise ValueError('model_name contains invalid path')
        return v

    @field_validator('text')
    @classmethod
    def validate_text(cls, v):
        """Sanitize input text."""
        # Remove excessive whitespace
        v = re.sub(r'\s+', ' ', v).strip()
        # Check for suspicious patterns (sql injection, code injection attempts)
        dangerous_patterns = [r"';.*--", r"\".*--", r"<script", r"javascript:", r"\$\{.*\}"]
        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError('text contains suspicious patterns')
        return v

    @field_validator('view_type')
    @classmethod
    def validate_view_type(cls, v):
        """Ensure view_type is one of the allowed options."""
        allowed = ['head', 'model']
        if v not in allowed:
            raise ValueError(f'view_type must be one of {allowed}')
        return v


def validate_and_sanitize(model_name: str, text: str, view_type: str) -> VisualizationRequest:
    """Validate and sanitize all inputs for visualization request."""
    try:
        request = VisualizationRequest(
            model_name=model_name,
            text=text,
            view_type=view_type
        )
        logger.info(f"Validated request for model '{request.model_name}' with text length {len(request.text)}")
        return request
    except ValueError as e:
        logger.warning(f"Validation failed: {e}")
        raise ValueError(f"Invalid request: {e}")
