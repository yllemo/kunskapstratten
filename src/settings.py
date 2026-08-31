"""Lokala inställningar för GUI och AI. Inget sparas i webbläsaren."""
from dataclasses import asdict, replace
from urllib.parse import urlparse
from flask import jsonify, request
from .ai_client import build_openai_client
from .registry import atomic_json


def register_settings(app, config):
    config.load_local_settings()

    @app.before_request
    def same_origin_writes():
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                return jsonify(error="Anrop från annan webbplats tillåts inte."), 403

    @app.context_processor
    def site_settings():
        return {"site_title": config.title}

    def validated(data, require_model=True):
        if not isinstance(data, dict) or not isinstance(data.get("ai"), dict):
            raise ValueError("Ogiltiga inställningar.")
        ai = replace(config.ai)
        values = data["ai"]
        for key in ("base_url", "model", "provider", "system_prompt"):
            value = values.get(key, getattr(ai, key))
            if not isinstance(value, str) or len(value) > 50000:
                raise ValueError("Ogiltigt textfält.")
            setattr(ai, key, value.strip())
        if ai.provider not in ("openai", "lmstudio", "ollama"):
            raise ValueError("Okänd leverantör.")
        parsed = urlparse(ai.base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Ange en HTTP/HTTPS-bas-URL utan lösenord eller frågesträng.")
        if require_model and not ai.model:
            raise ValueError("Ange en modell.")
        ai.temperature = float(values.get("temperature", ai.temperature))
        ai.context_window = int(values.get("context_window", ai.context_window))
        if not 0 <= ai.temperature <= 1 or not 256 <= ai.context_window <= 10_000_000:
            raise ValueError("Temperatur måste vara 0–1 och kontextfönster 256–10 000 000.")
        key = values.get("api_key", "")
        if not isinstance(key, str):
            raise ValueError("Ogiltig API-nyckel.")
        if values.get("clear_api_key"):
            ai.api_key = ""
        elif key.strip():
            ai.api_key = key.strip()
        elif (urlparse(ai.base_url).scheme, urlparse(ai.base_url).netloc) != (urlparse(config.ai.base_url).scheme, urlparse(config.ai.base_url).netloc):
            ai.api_key = ""
        ai.enabled = bool(values.get("enabled", ai.enabled))
        return ai

    @app.route("/api/settings", methods=["GET", "POST"])
    def settings_api():
        if request.method == "GET":
            ai = asdict(config.ai)
            ai["has_api_key"] = bool(ai.pop("api_key") not in ("", "not-needed"))
            return jsonify(title=config.title, ai=ai, memory=config.memory())
        data = request.get_json(silent=True)
        try:
            ai = validated(data)
            title = data.get("title", "").strip()
            memory = data.get("memory", "")
            if not title or len(title) > 120 or not isinstance(memory, str) or len(memory) > 200000:
                raise ValueError("Ange en titel (max 120 tecken) och minne (max 200 000 tecken).")
        except (ValueError, TypeError, AttributeError) as exc:
            return jsonify(error=str(exc)), 400
        # Atomiskt byte för båda filerna var för sig; minnesfilen är vanlig Markdown.
        import os
        import tempfile
        config.memory_path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=config.memory_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(memory)
            os.replace(name, config.memory_path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        atomic_json(config.settings_path, {"version": 1, "title": title, "ai": asdict(ai)})
        config.ai = ai
        config.title = title
        return jsonify(ok=True)

    @app.route("/api/settings/<action>", methods=["POST"])
    def settings_connection(action):
        if action not in ("models", "test"):
            return jsonify(error="Okänd åtgärd."), 404
        try:
            ai = validated(request.get_json(silent=True), require_model=action != "models")
            ai.enabled = True
            ai.timeout = 15
            client = build_openai_client(ai)
            try:
                if action == "models":
                    return jsonify(models=sorted(m.id for m in client.models.list()))
                client.chat.completions.create(model=ai.model, messages=[{"role": "user", "content": "Svara OK."}], max_tokens=8, temperature=0)
                return jsonify(ok=True)
            finally:
                client.close()
        except (ValueError, TypeError, AttributeError) as exc:
            return jsonify(error=str(exc)), 400
        except Exception:
            # SDK-fel kan innehålla hemligheter från leverantörens svar.
            return jsonify(error="Anslutningen misslyckades. Kontrollera server, modell och API-nyckel (samt att openai-paketet är installerat)."), 502
