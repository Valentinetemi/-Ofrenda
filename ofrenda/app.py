"""HTTP API and the single page. Nothing here talks to a cloud model."""

from __future__ import annotations

import io
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles

from ofrenda.config import ROOT, Settings, get_settings
from ofrenda.extract import ExtractionError, extract_story
from ofrenda.ghost import GHOST_VERSION, MOTION
from ofrenda.llm import StorytellerError, completer_for, ollama_status
from ofrenda.merge import (
    describe_merge,
    link_parent,
    link_sibling,
    link_spouse,
    merge_extraction,
    remove_person,
    unlink,
)
from ofrenda.names import display_name, normalize_name
from ofrenda.schemas import FamilyTree, Person
from ofrenda.seed import ensure_seed, reset_to_sample
from ofrenda.segment import ghost_sprite, mediapipe_runtime_status
from ofrenda.store import Store
from ofrenda.suggest import review_with_model, suggestions_from_tree

logger = logging.getLogger("ofrenda")

_YEAR_MIN = 1800
_YEAR_MAX = 2100


class StoryIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class PersonBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    origin: str | None = None
    birth_year: int | None = None
    death_year: int | None = None
    gender: str | None = None
    bio: str = ""
    memories: list[str] = Field(default_factory=list)
    parent_id: str | None = None
    spouse_id: str | None = None


class RelationIn(BaseModel):
    kind: str
    other_id: str


def _clean_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    if not text:
        return None
    return text[:limit]


def _gender(value: str | None) -> str | None:
    if value in {"female", "male"}:
        return value
    return None


def _check_years(birth: int | None, death: int | None) -> None:
    for year in (birth, death):
        if year is not None and not (_YEAR_MIN <= year <= _YEAR_MAX):
            raise HTTPException(status_code=422, detail="Years need to sit between 1800 and 2100.")
    if birth is not None and death is not None and death < birth:
        raise HTTPException(status_code=422, detail="The death year is earlier than the birth year.")


def _memories(values: list[str]) -> list[str]:
    kept: list[str] = []
    for value in values:
        text = _clean_text(value, 400)
        if text and text not in kept:
            kept.append(text)
        if len(kept) == 12:
            break
    return kept


def _portrait_path(settings: Settings, person: Person) -> Path | None:
    if not person.photo:
        return None
    name = Path(person.photo).name
    if not name or name in {".", ".."}:
        return None
    root = settings.portrait_dir.resolve()
    path = (root / name).resolve()
    if path.parent != root:
        return None
    return path


def _public_person(settings: Settings, person: Person) -> dict:
    payload = person.model_dump()
    photo = _portrait_path(settings, person)
    if photo and photo.is_file():
        payload["photo_url"] = f"/api/people/{person.id}/photo"
        payload["ghost_url"] = f"/api/people/{person.id}/ghost.png"
        payload["photo_mtime"] = photo.stat().st_mtime_ns
    else:
        payload["photo_url"] = None
        payload["ghost_url"] = None
        payload["photo_mtime"] = None
    return payload


def _public_tree(settings: Settings, tree: FamilyTree) -> dict:
    return {
        "narrator_id": tree.narrator_id,
        "sample": tree.sample,
        "people": [_public_person(settings, person) for person in tree.people],
    }


def _find(tree: FamilyTree, person_id: str) -> Person:
    person = next((item for item in tree.people if item.id == person_id), None)
    if person is None:
        raise HTTPException(status_code=404, detail="That person isn't on the altar.")
    return person


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ensure_seed(app.state.settings)
        yield

    app = FastAPI(title="Ofrenda", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = Store(settings.tree_path)
    app.state.review_cache = {}
    app.state.segmenter_status = None

    def store() -> Store:
        return app.state.store

    @app.get("/api/health")
    def health():
        if app.state.segmenter_status is None:
            app.state.segmenter_status = mediapipe_runtime_status(settings.segmenter_model)
        status = ollama_status(settings)
        status["ok"] = True
        status["segmenter"] = app.state.segmenter_status
        return status

    @app.get("/api/tree")
    def get_tree():
        return _public_tree(settings, store().load())

    @app.get("/api/ghost/motion")
    def ghost_motion():
        return MOTION

    @app.get("/api/suggestions")
    def suggestions():
        tree = store().load()
        status = ollama_status(settings)
        llm = "ready" if status["model_ready"] else status["llm"]
        return {"suggestions": [item.model_dump() for item in suggestions_from_tree(tree)], "llm": llm}

    @app.post("/api/suggestions/review")
    def review_suggestions():
        tree = store().load()
        digest = tree.model_dump_json()
        cached = app.state.review_cache.get(digest)
        if cached is not None:
            return cached
        if settings.mock_llm or not ollama_status(settings)["model_ready"]:
            body = {
                "suggestions": [item.model_dump() for item in suggestions_from_tree(tree)],
                "source": "rules",
            }
            return body
        reviewed = review_with_model(tree, completer_for(settings))
        source = "gemma" if any(item.source == "gemma" for item in reviewed) else "rules"
        body = {"suggestions": [item.model_dump() for item in reviewed], "source": source}
        app.state.review_cache[digest] = body
        return body

    @app.post("/api/stories")
    def tell_story(body: StoryIn):
        try:
            extraction = extract_story(body.text, completer_for(settings))
        except ExtractionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except StorytellerError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        def apply(tree: FamilyTree):
            return merge_extraction(tree, extraction)

        result = store().update(apply)
        app.state.review_cache.clear()
        return {
            "message": describe_merge(result),
            "added": result.added,
            "updated": result.updated,
            "tree": _public_tree(settings, store().load()),
        }

    @app.post("/api/people")
    def create_person(body: PersonBody):
        name = display_name(body.name.strip())
        origin = _clean_text(body.origin, 80)
        _check_years(body.birth_year, body.death_year)
        gender = _gender(body.gender)

        def apply(tree: FamilyTree):
            if any(normalize_name(person.name) == normalize_name(name) for person in tree.people):
                raise HTTPException(status_code=409, detail="Someone with that name is already on the altar.")
            from ofrenda.merge import _unique_id

            person = Person(
                id=_unique_id(tree, name),
                name=name,
                origin=origin,
                birth_year=body.birth_year,
                death_year=body.death_year,
                gender=gender,  # type: ignore[arg-type]
                bio=_clean_text(body.bio, 1000) or "",
                memories=_memories(body.memories),
            )
            tree.people.append(person)
            if body.parent_id:
                _find(tree, body.parent_id)
                link_parent(tree, body.parent_id, person.id)
            if body.spouse_id:
                _find(tree, body.spouse_id)
                link_spouse(tree, person.id, body.spouse_id)
            return person.id

        try:
            person_id = store().update(apply)
        except HTTPException:
            raise
        app.state.review_cache.clear()
        return _public_person(settings, next(p for p in store().load().people if p.id == person_id))

    @app.patch("/api/people/{person_id}")
    def update_person(person_id: str, body: PersonBody):
        name = display_name(body.name.strip())
        _check_years(body.birth_year, body.death_year)

        def apply(tree: FamilyTree):
            person = _find(tree, person_id)
            if any(
                other.id != person.id and normalize_name(other.name) == normalize_name(name)
                for other in tree.people
            ):
                raise HTTPException(status_code=409, detail="Someone with that name is already on the altar.")
            person.name = name
            person.origin = _clean_text(body.origin, 80)
            person.birth_year = body.birth_year
            person.death_year = body.death_year
            person.gender = _gender(body.gender)  # type: ignore[assignment]
            person.bio = _clean_text(body.bio, 1000) or ""
            person.memories = _memories(body.memories)
            return person

        try:
            store().update(apply)
        except HTTPException:
            raise
        app.state.review_cache.clear()
        return _public_person(settings, next(p for p in store().load().people if p.id == person_id))

    @app.delete("/api/people/{person_id}")
    def delete_person(person_id: str):
        def apply(tree: FamilyTree):
            person = remove_person(tree, person_id)
            if person is None:
                raise HTTPException(status_code=404, detail="That person isn't on the altar.")
            return person

        person = store().update(apply)
        photo = _portrait_path(settings, person)
        if photo and photo.is_file():
            photo.unlink()
        _clear_ghost_cache(settings, person_id)
        app.state.review_cache.clear()
        return {"ok": True}

    @app.post("/api/people/{person_id}/relationships")
    def add_relationship(person_id: str, body: RelationIn):
        if body.kind not in {"parent", "child", "spouse", "sibling"}:
            raise HTTPException(status_code=422, detail="Relationship must be parent, child, spouse, or sibling.")

        def apply(tree: FamilyTree):
            person = _find(tree, person_id)
            other = _find(tree, body.other_id)
            if person.id == other.id:
                raise HTTPException(status_code=422, detail="A person can't be linked to themself.")
            if body.kind == "parent":
                linked = link_parent(tree, other.id, person.id)
            elif body.kind == "child":
                linked = link_parent(tree, person.id, other.id)
            elif body.kind == "spouse":
                linked = link_spouse(tree, person.id, other.id)
            else:
                linked = link_sibling(tree, person.id, other.id)
            if not linked:
                raise HTTPException(status_code=422, detail="That link is already there, or it would loop the tree.")
            return None

        store().update(apply)
        app.state.review_cache.clear()
        return _public_tree(settings, store().load())

    @app.delete("/api/people/{person_id}/relationships")
    def delete_relationship(person_id: str, body: RelationIn):
        def apply(tree: FamilyTree):
            _find(tree, person_id)
            _find(tree, body.other_id)
            if body.kind == "parent":
                changed = unlink(tree, "parent", body.other_id, person_id)
            elif body.kind == "child":
                changed = unlink(tree, "child", person_id, body.other_id)
            else:
                changed = unlink(tree, body.kind, person_id, body.other_id)
            if not changed:
                raise HTTPException(status_code=404, detail="That link isn't on the altar.")

        store().update(apply)
        app.state.review_cache.clear()
        return _public_tree(settings, store().load())

    @app.post("/api/people/{person_id}/photo")
    async def upload_photo(person_id: str, file: UploadFile = File(...)):
        raw = await file.read()
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="That photograph is larger than 8MB.")
        try:
            from PIL import Image, ImageOps

            image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
            image = image.convert("RGB")
        except Exception as exc:
            raise HTTPException(status_code=400, detail="I couldn't read that image.") from exc
        image.thumbnail((1400, 1400))
        settings.portrait_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{person_id}.png"
        destination = settings.portrait_dir / filename
        image.save(destination, format="PNG")

        def apply(tree: FamilyTree):
            person = _find(tree, person_id)
            person.photo = filename

        store().update(apply)
        _clear_ghost_cache(settings, person_id)
        return _public_person(settings, next(p for p in store().load().people if p.id == person_id))

    @app.get("/api/people/{person_id}/photo")
    def get_photo(person_id: str):
        tree = store().load()
        person = _find(tree, person_id)
        path = _portrait_path(settings, person)
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail="No photograph yet.")
        return FileResponse(path, media_type="image/png")

    @app.get("/api/people/{person_id}/ghost.png")
    def get_ghost(person_id: str):
        tree = store().load()
        person = _find(tree, person_id)
        path = _portrait_path(settings, person)
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail="Add a photograph before sitting with them.")
        png, method = _cached_ghost(settings, person_id, path)
        return Response(
            content=png,
            media_type="image/png",
            headers={"X-Segmenter": method, "Cache-Control": "no-store"},
        )

    @app.post("/api/reset")
    def reset():
        reset_to_sample(settings)
        app.state.store = Store(settings.tree_path)
        app.state.review_cache.clear()
        return _public_tree(settings, app.state.store.load())

    static_dir = ROOT / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")

    return app


def _clear_ghost_cache(settings: Settings, person_id: str) -> None:
    cache = settings.cache_dir
    if not cache.is_dir():
        return
    for path in cache.glob(f"{person_id}.*"):
        path.unlink(missing_ok=True)


def _cached_ghost(settings: Settings, person_id: str, photo: Path) -> tuple[bytes, str]:
    from PIL import Image

    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{GHOST_VERSION}:{photo.stat().st_mtime_ns}:{photo.stat().st_size}"
    sprite_path = settings.cache_dir / f"{person_id}.png"
    meta_path = settings.cache_dir / f"{person_id}.txt"
    if sprite_path.is_file() and meta_path.is_file():
        lines = meta_path.read_text(encoding="utf-8").splitlines()
        if lines and lines[0] == stamp:
            method = lines[1] if len(lines) > 1 else "cached"
            return sprite_path.read_bytes(), method
    image = Image.open(photo)
    sprite, method = ghost_sprite(image, settings.segmenter_model)
    buffer = io.BytesIO()
    sprite.save(buffer, format="PNG")
    data = buffer.getvalue()
    sprite_path.write_bytes(data)
    meta_path.write_text(f"{stamp}\n{method}\n", encoding="utf-8")
    return data, method


app = create_app()
