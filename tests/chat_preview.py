"""Isolerad manuell UI-testserver, utan riktiga AI-anrop eller användardata.

Kör med: python -m tests.chat_preview (eller direkt med repo i PYTHONPATH).
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from src.config import AIConfig, Config, FrontmatterConfig, PathsConfig
from src.webapp import create_app

SAMPLE = '''Här är ett **diagram** och lite kod:

```mermaid
flowchart LR
    A[Dokument] --> B[Kunskapsbank]
    B --> C[Sammanfattning]
```

```python
def hälsa(namn):
    return f"Hej {namn}!"
```

<img src=x onerror="alert('xss')">
<script>alert('xss')</script>
[Osäker länk](javascript:alert(1))
'''


class FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        question = kwargs['messages'][-1]['content']
        source = '```mermaid\nthis is invalid\n```' if 'felaktigt' in question else SAMPLE
        for start in range(0, len(source), 35):
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=source[start:start+35]))])


if __name__ == '__main__':
    with TemporaryDirectory(prefix='kunskapstratten-chat-preview-') as directory:
        root = Path(directory)
        config = Config(PathsConfig(inbox=root/'inbox', processed_archive=root/'processed',
            output=root/'kb', images=root/'kb/images', skills=root/'skills',
            registry_db=root/'data/registry.json', logs=root/'logs'), AIConfig(), FrontmatterConfig())
        config.paths.ensure_exist()
        (config.paths.output/'demo.md').write_text('# Demodokument\nTestunderlag för skill.',encoding='utf-8')
        from src.skillbuilder import create_custom_skill
        create_custom_skill(config,name='Demoskill',description='Visa diagram och kod.',instructions='Sammanfatta underlaget.')
        with patch('src.webapp.build_openai_client', return_value=FakeClient()):
            create_app(config).run(host='127.0.0.1', port=5055)
