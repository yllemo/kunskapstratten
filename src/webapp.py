"""Lokalt webb-GUI: bläddra i kunskapsbanken, köra bearbetningsskills,
chatta mot innehållet och redigera Markdown direkt - allt via samma
lokala AI-inställningar (config.yaml -> ai.*) som resten av tratten
använder. Ingen separat AI-konfiguration i webbläsaren.

Körs helt lokalt (127.0.0.1 som standard).
"""
from __future__ import annotations

import logging
import re
import unicodedata
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import markdown as md_lib
import yaml
from flask import (
    Flask, Response, jsonify, redirect, render_template, request, send_file,
    send_from_directory, stream_with_context, url_for,
)
from werkzeug.utils import secure_filename

from .ai_client import build_openai_client
from .config import Config
from .converter import Converter
from .docstore import all_tags, list_documents, load_document, parse_markdown_file
from .pipeline import Pipeline
from .skillbuilder import create_custom_skill, list_custom_skills

logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = (
    "Du är en assistent som svarar på frågor enbart utifrån de dokument "
    "som användaren har lagt till i kontexten nedan, hämtade ur dennes "
    "lokala kunskapsbank. Om svaret inte finns i det tillagda innehållet, "
    "säg det tydligt istället för att gissa. Hänvisa gärna till vilket "
    "dokument informationen kommer ifrån. Svara på svenska om inget annat "
    "efterfrågas.\n\n=== KONTEXT ===\n{context}"
)


def _search_excerpt(body: str, query: str, radius: int = 90) -> str:
    """Returnerar ett kort textutdrag runt första sökträffen."""
    compact = re.sub(r"\s+", " ", body).strip()
    if not compact:
        return ""
    positions = [compact.casefold().find(term.casefold()) for term in query.split()]
    positions = [position for position in positions if position >= 0]
    start = max(0, min(positions) - radius) if positions else 0
    end = min(len(compact), start + radius * 2)
    return ("…" if start else "") + compact[start:end] + ("…" if end < len(compact) else "")


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")


def _build_chat_context(
    config: Config,
    context_paths: list[str],
    temporary_documents: list[dict] | None = None,
) -> str:
    kb_root = config.paths.output.resolve()
    blocks = []
    for rel in context_paths:
        if not isinstance(rel, str):
            continue
        full_path = (kb_root / rel).resolve()
        if kb_root != full_path and kb_root not in full_path.parents:
            continue
        if not full_path.exists() or full_path.suffix != ".md":
            continue
        doc = load_document(kb_root, full_path)
        blocks.append(f"--- {rel} ---\nTitel: {doc.title}\n\n{doc.body}")
    for item in temporary_documents or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "Tillfälligt dokument")[:200]
        body = str(item.get("body") or "")[:2_000_000]
        if body:
            blocks.append(f"--- TILLFÄLLIG FIL: {name} ---\n\n{body}")
    return "\n\n".join(blocks) if blocks else "(inga dokument tillagda i kontexten)"


def create_app(config: Config) -> Flask:
    config.paths.ensure_exist()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

    @app.route("/")
    def index():
        return browse()

    @app.route("/browse")
    def browse():
        all_docs = list_documents(config.paths.output)
        docs = all_docs
        q = request.args.get("q", "").strip()
        tag = request.args.get("tag", "").strip()
        source_type = request.args.get("type", "").strip()
        sort = request.args.get("sort", "title").strip()

        if q:
            terms = q.casefold().split()
            matched = []
            for doc in docs:
                haystack = " ".join((doc.title, doc.summary, " ".join(doc.tags), doc.body)).casefold()
                if all(term in haystack for term in terms):
                    doc.search_excerpt = _search_excerpt(doc.body, q)
                    matched.append(doc)
            docs = matched
        if tag:
            docs = [d for d in docs if tag in d.tags]
        if source_type:
            docs = [d for d in docs if (d.source_type or "md") == source_type]

        sorters = {
            "title": lambda d: d.title.casefold(),
            "newest": lambda d: -d.modified_at,
            "oldest": lambda d: d.modified_at,
            "path": lambda d: d.rel_path.casefold(),
        }
        if sort not in sorters:
            sort = "title"
        docs.sort(key=sorters[sort])

        return render_template(
            "browse.html",
            docs=docs,
            tags=all_tags(all_docs),
            q=q,
            active_tag=tag,
            active_type=source_type,
            source_types=sorted({d.source_type or "md" for d in all_docs}),
            sort=sort,
            total_docs=len(all_docs),
            result_count=len(docs),
        )

    def _resolve_doc_path(relpath: str):
        kb_root = config.paths.output.resolve()
        full_path = (kb_root / relpath).resolve()
        if kb_root != full_path and kb_root not in full_path.parents:
            return None
        if not full_path.exists() or full_path.suffix != ".md":
            return None
        return full_path

    def _resolve_skill_path(relpath: str):
        skills_root = config.paths.skills.resolve()
        full_path = (skills_root / relpath).resolve()
        if skills_root != full_path and skills_root not in full_path.parents:
            return None
        try:
            relative_parts = full_path.relative_to(skills_root).parts
        except ValueError:
            return None
        if not relative_parts or relative_parts[0] != "_custom":
            return None
        if not full_path.exists() or full_path.name != "SKILL.md":
            return None
        return full_path

    @app.route("/doc/<path:relpath>")
    def view_doc(relpath):
        full_path = _resolve_doc_path(relpath)
        if full_path is None:
            return "Ogiltig sökväg eller dokumentet hittades inte", 404

        doc = load_document(config.paths.output.resolve(), full_path)
        frontmatter, _ = parse_markdown_file(full_path)
        html_body = md_lib.markdown(doc.body, extensions=["fenced_code", "tables"])
        return render_template(
            "doc.html",
            doc=doc,
            html_body=html_body,
            relpath=relpath,
            frontmatter=frontmatter,
        )

    @app.route("/doc/<path:relpath>/download")
    def download_doc(relpath):
        full_path = _resolve_doc_path(relpath)
        if full_path is None:
            return "Ogiltig sökväg eller dokumentet hittades inte", 404
        return send_file(full_path, as_attachment=True, download_name=full_path.name)

    @app.route("/new", methods=["GET", "POST"])
    def new_doc():
        if request.method == "GET":
            return render_template("new.html")

        title = request.form.get("title", "").strip()
        folder = request.form.get("folder", "").strip().replace("\\", "/").strip("/")
        tags = [tag.strip().lstrip("#") for tag in request.form.get("tags", "").split(",") if tag.strip()]
        body = request.form.get("body", "").strip()
        if not title:
            return render_template("new.html", error="Titel måste anges.", form=request.form), 400

        folder_parts = [_slugify(part) for part in folder.split("/") if part]
        folder_parts = [part for part in folder_parts if part]
        filename = _slugify(title)
        if not filename:
            return render_template("new.html", error="Titeln måste innehålla bokstäver eller siffror.", form=request.form), 400

        relative = Path(*folder_parts, f"{filename}.md")
        target = config.paths.output.resolve() / relative
        if target.exists():
            return render_template("new.html", error=f"Dokumentet {relative.as_posix()} finns redan.", form=request.form), 409

        meta = {
            "title": title,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tags": tags,
            "source_type": "md",
        }
        raw = f"---\n{yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)}---\n\n{body}\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(raw, encoding="utf-8")
        return redirect(url_for("view_doc", relpath=relative.as_posix()))

    @app.route("/upload", methods=["GET", "POST"])
    def upload_documents():
        if request.method == "GET":
            return render_template("upload.html", supported=config.supported_extensions)

        uploads = [item for item in request.files.getlist("files") if item and item.filename]
        folder = request.form.get("folder", "").strip().replace("\\", "/").strip("/")
        folder_parts = [_slugify(part) for part in folder.split("/") if _slugify(part)]
        destination = config.paths.inbox.joinpath(*folder_parts)
        allowed = {extension.casefold() for extension in config.supported_extensions}
        if not uploads:
            return render_template("upload.html", supported=config.supported_extensions,
                                   error="Välj minst en fil."), 400

        saved = []
        rejected = []
        destination.mkdir(parents=True, exist_ok=True)
        for upload in uploads:
            original = Path(upload.filename).name
            extension = Path(original).suffix.casefold()
            if extension not in allowed:
                rejected.append(f"{original} (filtypen stöds inte)")
                continue
            safe_name = secure_filename(original)
            if not safe_name:
                rejected.append(f"{original} (ogiltigt filnamn)")
                continue
            target = destination / safe_name
            counter = 2
            while target.exists():
                target = destination / f"{Path(safe_name).stem}-{counter}{Path(safe_name).suffix}"
                counter += 1
            upload.save(target)
            saved.append(target.relative_to(config.paths.inbox).as_posix())

        status = 200 if saved else 400
        return render_template(
            "upload.html", supported=config.supported_extensions,
            saved=saved, rejected=rejected, error=None if saved else "Inga filer kunde laddas upp."
        ), status

    @app.route("/skills/new", methods=["GET", "POST"])
    def new_skill():
        docs = list_documents(config.paths.output)
        if request.method == "GET":
            return render_template("new_skill.html", docs=docs)

        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        instructions = request.form.get("instructions", "").strip()
        if not name or not description:
            return render_template(
                "new_skill.html", docs=docs, form=request.form,
                error="Namn och beskrivning måste anges."
            ), 400
        try:
            create_custom_skill(
                config, name=name, description=description,
                instructions=instructions,
            )
        except (ValueError, FileExistsError) as exc:
            return render_template(
                "new_skill.html", docs=docs, form=request.form, error=str(exc),
            ), 409
        return redirect(url_for("skills_page"))

    @app.route("/doc/<path:relpath>/edit")
    def edit_doc(relpath):
        full_path = _resolve_doc_path(relpath)
        if full_path is None:
            return "Ogiltig sökväg eller dokumentet hittades inte", 404
        raw = full_path.read_text(encoding="utf-8")
        return render_template("edit.html", relpath=relpath, raw=raw)

    @app.route("/skills/edit/<path:relpath>")
    def edit_skill(relpath):
        full_path = _resolve_skill_path(relpath)
        if full_path is None:
            return "Ogiltig sökväg eller skillen hittades inte", 404
        raw = full_path.read_text(encoding="utf-8")
        return render_template("edit_skill.html", relpath=relpath, raw=raw)

    @app.route("/api/doc/<path:relpath>", methods=["POST"])
    def save_doc(relpath):
        full_path = _resolve_doc_path(relpath)
        if full_path is None:
            return jsonify({"error": "Ogiltig sökväg eller dokumentet hittades inte."}), 404

        data = request.get_json(force=True, silent=True) or {}
        content = data.get("content")
        if content is None:
            return jsonify({"error": "Inget innehåll skickades."}), 400

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    yaml.safe_load(parts[1])
                except yaml.YAMLError as exc:
                    return jsonify({"error": f"Ogiltig YAML i frontmatter: {exc}"}), 400

        full_path.write_text(content, encoding="utf-8")
        return jsonify({"ok": True})

    @app.route("/api/skill/<path:relpath>", methods=["POST"])
    def save_skill(relpath):
        full_path = _resolve_skill_path(relpath)
        if full_path is None:
            return jsonify({"error": "Ogiltig sökväg eller skillen hittades inte."}), 404
        data = request.get_json(force=True, silent=True) or {}
        content = data.get("content")
        if not isinstance(content, str):
            return jsonify({"error": "Inget innehåll skickades."}), 400
        if not content.startswith("---"):
            return jsonify({"error": "SKILL.md måste börja med YAML-frontmatter (---)."}), 400
        parts = content.split("---", 2)
        if len(parts) < 3:
            return jsonify({"error": "YAML-frontmatter saknar avslutande ---."}), 400
        try:
            meta = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError as exc:
            return jsonify({"error": f"Ogiltig YAML i frontmatter: {exc}"}), 400
        if not isinstance(meta, dict) or not meta.get("name") or not meta.get("description"):
            return jsonify({"error": "Frontmatter måste innehålla name och description."}), 400
        full_path.write_text(content, encoding="utf-8")
        return jsonify({"ok": True})

    @app.route("/images/<path:filename>")
    def serve_image(filename):
        return send_from_directory(config.paths.images, filename)

    @app.route("/skills")
    def skills_page():
        return render_template("skills.html", custom_skills=list_custom_skills(config))

    @app.route("/skills/run/<slug>")
    def run_skill_page(slug):
        skill = next((item for item in list_custom_skills(config) if item["slug"] == slug), None)
        if skill is None:
            return "Skillen hittades inte", 404
        return render_template(
            "run_skill.html", skill=skill, docs=list_documents(config.paths.output),
            ai_configured=bool(config.ai.enabled and config.ai.model),
        )

    @app.route("/api/skills/run", methods=["POST"])
    def run_skill_api():
        data = request.get_json(force=True, silent=True) or {}
        slug = str(data.get("skill") or "")
        selected_paths = data.get("document_paths") or []
        task = str(data.get("task") or "").strip()
        skill = next((item for item in list_custom_skills(config) if item["slug"] == slug), None)
        if skill is None:
            return jsonify({"error": "Skillen hittades inte."}), 404
        if not isinstance(selected_paths, list) or not selected_paths:
            return jsonify({"error": "Välj minst ett dokument."}), 400
        if not (config.ai.enabled and config.ai.model):
            return jsonify({"error": "Ingen lokal AI är konfigurerad."}), 400

        context = _build_chat_context(config, selected_paths)
        system_prompt = (
            f"Du kör bearbetningsskillen '{skill['name']}'.\n\n"
            f"BESKRIVNING:\n{skill['description']}\n\n"
            f"INSTRUKTIONER:\n{skill['instructions']}\n\n"
            "Bearbeta endast underlaget nedan. Var tydlig när information saknas. "
            "Returnera resultatet som välstrukturerad Markdown.\n\n"
            f"=== VALDA DOKUMENT ===\n{context}"
        )
        user_prompt = task or "Kör skillen enligt dess instruktioner på de valda dokumenten."

        def generate_skill_result():
            try:
                client = build_openai_client(config.ai)
                stream = client.chat.completions.create(
                    model=config.ai.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                    stream=True,
                )
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skill-körning misslyckades: %s", exc)
                yield f"\n\n[FEL] Kunde inte köra skillen: {exc}"

        return Response(stream_with_context(generate_skill_result()), mimetype="text/plain")

    @app.route("/api/skills/save-result", methods=["POST"])
    def save_skill_result():
        data = request.get_json(force=True, silent=True) or {}
        title = str(data.get("title") or "").strip()
        body = str(data.get("body") or "").strip()
        skill_slug = _slugify(str(data.get("skill") or "skill")) or "skill"
        if not title or not body:
            return jsonify({"error": "Titel och resultat måste finnas."}), 400
        filename = _slugify(title)
        folder = config.paths.output / "skill-resultat"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{filename}.md"
        counter = 2
        while target.exists():
            target = folder / f"{filename}-{counter}.md"
            counter += 1
        meta = {
            "title": title,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tags": ["skill-resultat", skill_slug],
            "source_type": "md",
            "generated_by_skill": skill_slug,
        }
        target.write_text(
            f"---\n{yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)}---\n\n{body}\n",
            encoding="utf-8",
        )
        relpath = target.relative_to(config.paths.output).as_posix()
        return jsonify({"ok": True, "url": url_for("view_doc", relpath=relpath)})

    @app.route("/chat")
    def chat_page():
        docs = list_documents(config.paths.output)
        chat_skills = list_custom_skills(config)

        chat_data = {
            "docs": [
                {"rel_path": d.rel_path, "title": d.title, "tags": d.tags, "body": d.body}
                for d in docs
            ],
            "skills": [
                {
                    "slug": skill["slug"], "name": skill["name"],
                    "description": skill["description"],
                    "instructions": skill["instructions"],
                }
                for skill in chat_skills
            ],
            "context_window": config.ai.context_window,
        }

        initial_paths: list[str] = []
        doc_q = request.args.get("doc")
        if doc_q:
            initial_paths.append(doc_q)

        ai_configured = bool(config.ai.enabled and config.ai.model)
        ai_model_label = (
            f"Lokal AI: {config.ai.model} ({config.ai.base_url})"
            if ai_configured else
            "Ingen lokal AI konfigurerad - se ai i config.yaml"
        )

        return render_template(
            "chat.html",
            docs=docs,
            skill_nodes=[],
            chat_skills=chat_skills,
            supported_extensions=config.supported_extensions,
            chat_data=chat_data,
            initial_paths=sorted(set(initial_paths)),
            ai_configured=ai_configured,
            ai_model_label=ai_model_label,
        )

    @app.route("/api/chat/temp-file", methods=["POST"])
    def chat_temp_file():
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return jsonify({"error": "Ingen fil skickades."}), 400
        original = Path(upload.filename).name
        extension = Path(original).suffix.casefold()
        if extension not in {ext.casefold() for ext in config.supported_extensions}:
            return jsonify({"error": f"Filtypen {extension or '(saknas)'} stöds inte."}), 400
        safe_name = secure_filename(original)
        if not safe_name:
            return jsonify({"error": "Ogiltigt filnamn."}), 400
        try:
            with tempfile.TemporaryDirectory(prefix="kunskapsbank-chat-") as temp_dir:
                temp_root = Path(temp_dir)
                source = temp_root / safe_name
                upload.save(source)
                if extension in {".txt", ".md", ".csv", ".json", ".xml"}:
                    markdown_body = source.read_text(encoding="utf-8", errors="replace")
                else:
                    markdown_body = Converter(config).convert(source, temp_root / "images").markdown
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tillfällig chattfil kunde inte konverteras: %s", exc)
            return jsonify({"error": f"Kunde inte läsa filen: {exc}"}), 400
        return jsonify({"name": original, "body": markdown_body[:2_000_000]})

    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        data = request.get_json(force=True, silent=True) or {}
        messages = data.get("messages")
        context_paths = data.get("context_paths") or []
        temporary_documents = data.get("temporary_documents") or []
        skill_slug = str(data.get("skill") or "")
        if not messages or not isinstance(messages, list):
            return jsonify({"error": "Inga meddelanden skickades."}), 400
        if not (config.ai.enabled and config.ai.model):
            return jsonify({
                "error": "Ingen lokal AI konfigurerad. Sätt ai.enabled/base_url/model i config.yaml."
            }), 400

        context_text = _build_chat_context(config, context_paths, temporary_documents)
        system_prompt = CHAT_SYSTEM_PROMPT.replace("{context}", context_text)
        if skill_slug:
            skill = next((item for item in list_custom_skills(config) if item["slug"] == skill_slug), None)
            if skill is None:
                return jsonify({"error": "Den valda skillen hittades inte."}), 400
            system_prompt = (
                f"AKTIV SKILL: {skill['name']}\n"
                f"BESKRIVNING: {skill['description']}\n"
                f"INSTRUKTIONER:\n{skill['instructions']}\n\n"
                + system_prompt
            )
        full_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            role = m.get("role") if isinstance(m, dict) else None
            content = m.get("content") if isinstance(m, dict) else None
            if role in ("user", "assistant") and content:
                full_messages.append({"role": role, "content": content})

        def generate():
            try:
                client = build_openai_client(config.ai)
            except RuntimeError as exc:
                yield f"[FEL] {exc}"
                return
            try:
                stream = client.chat.completions.create(
                    model=config.ai.model,
                    messages=full_messages,
                    temperature=0.3,
                    stream=True,
                )
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
            except Exception as exc:  # noqa: BLE001 - visas för användaren i chatten
                logger.warning("Chattanrop till lokal AI misslyckades: %s", exc)
                yield f"\n\n[FEL] Kunde inte nå den lokala AI:n: {exc}"

        return Response(stream_with_context(generate()), mimetype="text/plain")

    @app.route("/api/reindex", methods=["POST"])
    def api_reindex():
        pipeline = Pipeline(config)
        try:
            ingest_stats = pipeline.process_all()
        finally:
            pipeline.close()

        return jsonify({
            "ingest": ingest_stats,
            "skills": {"skills": len(list_custom_skills(config)), "documents": 0},
        })

    @app.route("/api/stats")
    def api_stats():
        docs = list_documents(config.paths.output)
        return jsonify({"documents": len(docs), "tags": len(all_tags(docs))})

    return app


def run_gui(config: Config) -> None:
    app = create_app(config)
    logger.info("Startar GUI på http://%s:%s", config.gui.host, config.gui.port)
    app.run(host=config.gui.host, port=config.gui.port, debug=False, threaded=True)
