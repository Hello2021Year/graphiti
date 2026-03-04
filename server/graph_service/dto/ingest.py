from pydantic import BaseModel, Field

from graph_service.dto.common import Message


class AddMessagesRequest(BaseModel):
    group_id: str = Field(..., description='The group id of the messages to add')
    messages: list[Message] = Field(..., description='The messages to add')


class AddEntityNodeRequest(BaseModel):
    uuid: str = Field(..., description='The uuid of the node to add')
    group_id: str = Field(..., description='The group id of the node to add')
    name: str = Field(..., description='The name of the node to add')
    summary: str = Field(default='', description='The summary of the node to add')


class FileIngestResponse(BaseModel):
    """Response for POST /ingest/file."""

    message: str = Field(..., description='Status message')
    success: bool = Field(..., description='Whether the request was accepted')
    filename: str = Field(..., description='Original filename')
    graphiti_id: str | None = Field(default=None, description='Graph/group id used for ingest (if provided)')
