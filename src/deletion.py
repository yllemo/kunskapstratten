"""Avgränsad, bekräftad radering från Markdown-redigerarna."""
import hashlib
import threading
from pathlib import Path

from flask import jsonify, request

from .citations import original_path
from .docstore import load_document, list_documents
from .registry import Registry
from .reset import _is_link


def register_deletion(app, config):
    lock = threading.Lock()

    def plan(kind, relpath):
        root = (config.paths.output if kind == 'doc' else config.paths.skills).resolve()
        path = root / relpath
        if '..' in Path(relpath).parts or not path.resolve().is_relative_to(root):
            raise ValueError('Ogiltig sökväg.')
        if any(_is_link(p) for p in [path, *path.parents]):
            raise ValueError('Radering via länkar eller junctions tillåts inte.')
        path = path.resolve()
        if not path.is_file() or path.suffix != '.md':
            raise FileNotFoundError('Filen hittades inte.')
        if kind == 'skill' and (path.name != 'SKILL.md' or path.relative_to(root).parts[0] != '_custom'):
            raise ValueError('Endast egna skills kan raderas.')
        doc = load_document(root, path)
        original = original_path(config, doc)
        if original:
            if any(_is_link(p) for p in [original, *original.parents]):
                raise ValueError('Originalet ligger i en länkad mapp.')
            # Ett original kan vara delat: radera då inte någon fil utan besked.
            for other_root in (config.paths.output, config.paths.skills):
                for other in list_documents(other_root):
                    if other.path.resolve() != path and original_path(config, other) == original:
                        raise ValueError('Originalet används även av ett annat dokument eller en skill. Ta bort den delade source_file-kopplingen före radering.')
        targets = list(dict.fromkeys([path] + ([original] if original else [])))
        stamp = hashlib.sha256()
        for target in targets:
            stat = target.stat()
            stamp.update(f'{target}\0{stat.st_size}\0{stat.st_mtime_ns}\0'.encode())
        return path, targets, stamp.hexdigest()

    @app.route('/api/delete/<kind>/<path:relpath>', methods=['GET', 'DELETE'])
    def delete_item(kind, relpath):
        if kind not in {'doc', 'skill'}:
            return jsonify(error='Ogiltig filtyp.'), 404
        with lock:
            try:
                path, targets, version = plan(kind, relpath)
                if request.method == 'GET':
                    return jsonify(version=version, files=[p.name for p in targets])
                data = request.get_json(silent=True) or {}
                if data.get('confirm') is not True or data.get('version') != version:
                    return jsonify(error='Bekräftelse saknas eller filerna har ändrats. Försök igen.'), 409
                # Endast exakta verifierade filer, aldrig rekursiv katalogradering.
                for target in reversed(targets):
                    target.unlink()
                Registry(config.paths.registry_db).remove_output(path)
                return jsonify(ok=True)
            except FileNotFoundError as exc:
                return jsonify(error=str(exc)), 404
            except ValueError as exc:
                return jsonify(error=str(exc)), 400
            except OSError:
                app.logger.exception('Radering misslyckades')
                return jsonify(error='Raderingen kunde inte slutföras. Kontrollera filrättigheter; vissa filer kan redan ha tagits bort.'), 500
