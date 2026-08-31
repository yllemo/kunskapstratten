"""Explicit, dubbelbekräftad återställning av lokala användarfiler."""
import hashlib
import secrets
import threading
import time
from pathlib import Path

from flask import g, jsonify, request, session
from dataclasses import replace
from .docstore import _cached_document


def _is_link(path):
    return path.is_symlink() or (path.exists() and bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400))


def reset_plan(config):
    """Fastställ exakta mål och neka breda sökvägar, överlapp och länkar."""
    original = [config.paths.output, config.paths.skills, config.paths.processed_archive, config.paths.registry_db.parent]
    protected = [Path(__file__).resolve().parent.parent, Path.home().resolve(), config.paths.inbox.resolve(), config.paths.logs.resolve()]
    roots = []
    for value in original:
        value = Path(value).absolute()
        if any(_is_link(p) for p in [value, *value.parents]):
            raise ValueError('Återställning tillåts inte genom symboliska länkar eller junctions.')
        root = value.resolve()
        if any(root.is_relative_to(p) for p in protected[2:]):
            raise ValueError('Återställningsmappar får inte ligga i inbox eller loggmappen.')
        if root == Path(root.anchor) or any(root == p or root in p.parents for p in protected):
            raise ValueError(f'Osäker återställningsmapp: {root}')
        repo = protected[0]
        if root.is_relative_to(repo) and root.parts[len(repo.parts)] in {'src', 'tests', '.git', '.github', '.venv', '.codex', '.agents'}:
            raise ValueError(f'Programfiler får inte återställas: {root}')
        if any(root == p or root in p.parents or p in root.parents for p in roots):
            raise ValueError('Återställningsmapparna får inte överlappa varandra.')
        if root.exists() and not root.is_dir():
            raise ValueError(f'Inte en katalog: {root}')
        roots.append(root)
    files, directories, counts = [], [], []
    for index, root in enumerate(roots):
        entries = list(root.rglob('*')) if root.exists() else []
        count = 0
        for path in entries:
            if _is_link(path) or not path.resolve().is_relative_to(root):
                raise ValueError(f'Länk/junction upptäcktes i återställningsmålet: {path}')
            if path.is_file() and (index != 0 or path.suffix.lower() == '.md'):
                files.append(path)
                count += 1
            elif path.is_dir() and index != 0:
                directories.append(path)
        counts.append({'path': str(root), 'files': count, 'scope': 'Markdown-filer' if index == 0 else 'Allt innehåll'})
    files.sort()
    stamp = hashlib.sha256()
    for path in files:
        stat = path.stat()
        stamp.update(f'{path}\0{stat.st_size}\0{stat.st_mtime_ns}\0'.encode())
    for path in sorted(directories):
        stamp.update(str(path).encode())
    return files, sorted(directories, key=lambda p: len(p.parts), reverse=True), counts, stamp.hexdigest()


def register_reset(app, config):
    app.secret_key = app.secret_key or secrets.token_hex(32)
    lock = threading.Lock()
    state = {'active': 0, 'resetting': False}
    challenges = {}

    @app.before_request
    def guard_reset():
        if request.endpoint in {'reset_challenge', 'reset_data'}:
            return
        with lock:
            if state['resetting']:
                return jsonify(error='Återställning pågår. Försök igen strax.'), 409
            if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
                state['active'] += 1
                released = False

                def release():
                    nonlocal released
                    with lock:
                        if not released:
                            state['active'] -= 1
                            released = True
                g.reset_release = release

    @app.after_request
    def finish_operation(response):
        release = getattr(g, 'reset_release', None)
        if release:
            if response.is_streamed:
                original = response.response

                def stream():
                    try:
                        yield from original
                    finally:
                        try:
                            if hasattr(original, 'close'):
                                original.close()
                        finally:
                            release()
                response.response = stream()
                response.call_on_close(release)
                g.reset_handoff = True
            else:
                release()
        return response

    @app.teardown_request
    def release_on_error(error):
        if not getattr(g, 'reset_handoff', False) and getattr(g, 'reset_release', None):
            g.reset_release()

    @app.route('/api/reset/challenge', methods=['POST'])
    def reset_challenge():
        try:
            _, _, counts, stamp = reset_plan(config)
        except (ValueError, OSError) as exc:
            return jsonify(error=str(exc)), 400
        owner = session.setdefault('reset_owner', secrets.token_hex(24))
        token = secrets.token_urlsafe(32)
        a, b = secrets.randbelow(9) + 2, secrets.randbelow(9) + 2
        with lock:
            if state['resetting'] or state['active']:
                return jsonify(error='Avsluta pågående import, chatt eller sparning först.'), 409
            for key in list(challenges):
                if challenges[key]['expires'] < time.monotonic() or challenges[key]['owner'] == owner:
                    del challenges[key]
            if len(challenges) >= 100:
                return jsonify(error='För många återställningsförfrågningar. Försök senare.'), 429
            challenges[token] = dict(owner=owner, answer=str(a+b), stamp=stamp, expires=time.monotonic()+300)
        return jsonify(token=token, question=f'{a} + {b} =', targets=counts, total=sum(c['files'] for c in counts))

    @app.route('/api/reset', methods=['POST'])
    def reset_data():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or data.get('confirmed') is not True:
            return jsonify(error='Du måste godkänna raderingen först.'), 400
        token = data.get('token')
        if not isinstance(token, str):
            return jsonify(error='Begär en ny mattefråga.'), 400
        with lock:
            challenge = challenges.get(token)
            if not challenge or challenge['owner'] != session.get('reset_owner'):
                return jsonify(error='Ogiltig bekräftelse. Begär en ny mattefråga.'), 400
            del challenges[token]
            if challenge['expires'] < time.monotonic() or str(data.get('answer', '')).strip() != challenge['answer']:
                return jsonify(error='Fel svar eller utgången fråga. Begär en ny mattefråga.'), 400
            if state['active'] or state['resetting']:
                return jsonify(error='Avsluta pågående import, chatt eller sparning först.'), 409
            state['resetting'] = True
        removed = 0
        try:
            files, directories, _, stamp = reset_plan(config)
            if stamp != challenge['stamp']:
                return jsonify(error='Filerna har ändrats sedan varningen visades. Granska en ny bekräftelse.'), 409
            for path in files:
                # Kontrollera målet igen om ett annat program ändrat en länk.
                if any(_is_link(p) for p in [path, *path.parents]):
                    raise ValueError('En sökväg ändrades under återställningen. Raderingen avbröts.')
                path.unlink()
                removed += 1
            for path in directories:
                path.rmdir()
            config.ai = replace(config._initial_ai)
            config.title = config._initial_title
            _cached_document.cache_clear()
            return jsonify(ok=True, removed=removed)
        except (ValueError, OSError) as exc:
            return jsonify(error=f'Återställningen avbröts efter {removed} raderade filer. {exc}', removed=removed), 500
        finally:
            with lock:
                state['resetting'] = False
