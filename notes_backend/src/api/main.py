from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


def _now_iso() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _NoteRecord:
    """Internal representation of a Note in the in-memory store."""

    id: int
    title: str
    content: str
    created_at: str
    updated_at: str


class Note(BaseModel):
    """Public Note model returned by the API."""

    id: int = Field(..., description="Unique identifier of the note.")
    title: str = Field(..., min_length=1, description="Short title for the note.")
    content: str = Field(..., min_length=1, description="Full content/body of the note.")
    created_at: str = Field(..., description="ISO timestamp when the note was created (UTC).")
    updated_at: str = Field(..., description="ISO timestamp when the note was last updated (UTC).")


class NoteCreate(BaseModel):
    """Request model for creating a note."""

    title: str = Field(..., min_length=1, description="Short title for the note.")
    content: str = Field(..., min_length=1, description="Full content/body of the note.")


class NoteUpdate(BaseModel):
    """Request model for updating a note (partial updates are allowed)."""

    title: Optional[str] = Field(None, min_length=1, description="Updated title for the note.")
    content: Optional[str] = Field(None, min_length=1, description="Updated content/body of the note.")


openapi_tags = [
    {"name": "Health", "description": "Service health and basic diagnostics."},
    {"name": "Notes", "description": "Create, read, update, and delete notes."},
]

app = FastAPI(
    title="Simple Notes API",
    description=(
        "A minimal Notes API used by the React frontend.\n\n"
        "Default dev ports:\n"
        "- Backend: http://localhost:3001\n"
        "- Frontend: http://localhost:3000\n"
    ),
    version="0.1.0",
    openapi_tags=openapi_tags,
)

# CORS: allow the React dev server (port 3000) to call backend (port 3001).
# Keep localhost + 127.0.0.1 variants for convenience.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class _NotesStore:
    """In-memory notes store with simple auto-increment ID generation."""

    def __init__(self) -> None:
        self._notes: Dict[int, _NoteRecord] = {}
        self._next_id: int = 1
        self._seed_if_empty()

    def _seed_if_empty(self) -> None:
        if self._notes:
            return
        self.create(
            NoteCreate(
                title="Welcome",
                content="This is a simple notes app. Create, edit, and delete notes!",
            )
        )
        self.create(
            NoteCreate(
                title="Tip",
                content="Click a note in the list to edit it. Use the Delete button to remove it.",
            )
        )

    def _to_model(self, rec: _NoteRecord) -> Note:
        return Note(
            id=rec.id,
            title=rec.title,
            content=rec.content,
            created_at=rec.created_at,
            updated_at=rec.updated_at,
        )

    def list(self) -> List[Note]:
        # Stable ordering by id ascending.
        return [self._to_model(self._notes[nid]) for nid in sorted(self._notes.keys())]

    def get(self, note_id: int) -> Note:
        rec = self._notes.get(note_id)
        if rec is None:
            raise KeyError(note_id)
        return self._to_model(rec)

    def create(self, payload: NoteCreate) -> Note:
        now = _now_iso()
        note_id = self._next_id
        self._next_id += 1
        rec = _NoteRecord(
            id=note_id,
            title=payload.title,
            content=payload.content,
            created_at=now,
            updated_at=now,
        )
        self._notes[note_id] = rec
        return self._to_model(rec)

    def update(self, note_id: int, payload: NoteUpdate) -> Note:
        rec = self._notes.get(note_id)
        if rec is None:
            raise KeyError(note_id)

        if payload.title is None and payload.content is None:
            # Nothing to update; still return current.
            return self._to_model(rec)

        if payload.title is not None:
            rec.title = payload.title
        if payload.content is not None:
            rec.content = payload.content

        rec.updated_at = _now_iso()
        self._notes[note_id] = rec
        return self._to_model(rec)

    def delete(self, note_id: int) -> None:
        if note_id not in self._notes:
            raise KeyError(note_id)
        del self._notes[note_id]


_STORE = _NotesStore()


@app.get(
    "/",
    tags=["Health"],
    summary="Health check",
    operation_id="health_check",
)
def health_check() -> dict:
    """Return a simple health response used for diagnostics."""
    return {"message": "Healthy"}


@app.get(
    "/notes",
    response_model=List[Note],
    tags=["Notes"],
    summary="List notes",
    operation_id="list_notes",
)
def list_notes() -> List[Note]:
    """Return all notes."""
    return _STORE.list()


@app.post(
    "/notes",
    response_model=Note,
    status_code=201,
    tags=["Notes"],
    summary="Create a note",
    operation_id="create_note",
)
def create_note(payload: NoteCreate) -> Note:
    """Create a new note."""
    return _STORE.create(payload)


@app.get(
    "/notes/{note_id}",
    response_model=Note,
    tags=["Notes"],
    summary="Get a note",
    operation_id="get_note",
)
def get_note(
    note_id: int = Path(..., ge=1, description="ID of the note to fetch."),
) -> Note:
    """Fetch a single note by id."""
    try:
        return _STORE.get(note_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Note not found") from exc


@app.put(
    "/notes/{note_id}",
    response_model=Note,
    tags=["Notes"],
    summary="Update a note",
    operation_id="update_note",
)
def update_note(
    payload: NoteUpdate,
    note_id: int = Path(..., ge=1, description="ID of the note to update."),
) -> Note:
    """Update an existing note by id (partial update allowed)."""
    try:
        return _STORE.update(note_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Note not found") from exc


@app.delete(
    "/notes/{note_id}",
    status_code=204,
    tags=["Notes"],
    summary="Delete a note",
    operation_id="delete_note",
)
def delete_note(
    note_id: int = Path(..., ge=1, description="ID of the note to delete."),
) -> None:
    """Delete a note by id."""
    try:
        _STORE.delete(note_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Note not found") from exc
    return None
