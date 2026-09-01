from pathlib import Path
from tempfile import TemporaryDirectory
from io import BytesIO
import unittest

from src.config import AIConfig, Config, FrontmatterConfig, PathsConfig
from src.webapp import _slugify, create_app
from src.skillbuilder import list_custom_skills


class WebappFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        paths = PathsConfig(
            inbox=root / "inbox",
            processed_archive=root / "processed",
            output=root / "knowledge",
            images=root / "knowledge" / "images",
            skills=root / "skills",
            registry_db=root / "data" / "registry.db",
            logs=root / "logs",
        )
        self.config = Config(paths=paths, ai=AIConfig(enabled=False), frontmatter=FrontmatterConfig())
        paths.ensure_exist()
        (paths.output / "alpha.md").write_text(
            "---\ntitle: Alfa\ntags: [test]\nsource_type: txt\n---\n\nHemligt sökord i brödtexten.",
            encoding="utf-8",
        )
        self.client = create_app(self.config).test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_full_text_search_and_excerpt(self):
        response = self.client.get("/browse?q=hemligt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Hemligt sökord", response.get_data(as_text=True))

    def test_browse_has_clear_primary_actions_and_controls(self):
        html = self.client.get("/browse").get_data(as_text=True)
        self.assertIn("Kunskapsbanken", html)
        self.assertIn("＋ Nytt dokument", html)
        self.assertIn("⇧ Ladda upp", html)
        self.assertIn('class="search-primary"', html)
        self.assertIn('class="browse-quickbar"', html)
        self.assertIn('class="filter-panel"', html)

    def test_pages_include_svg_favicon(self):
        html = self.client.get("/browse").get_data(as_text=True)
        self.assertIn('rel="icon"', html)
        self.assertIn("favicon.svg", html)
        response = self.client.get("/static/favicon.svg")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<svg", response.data)

    def test_type_filter(self):
        self.assertIn("Alfa", self.client.get("/browse?type=txt").get_data(as_text=True))
        self.assertNotIn("Alfa", self.client.get("/browse?type=pdf").get_data(as_text=True))

    def test_tags_link_to_filtered_browse_from_cards_and_document(self):
        browse_html = self.client.get("/browse").get_data(as_text=True)
        self.assertIn("tag=test", browse_html)
        self.assertIn("Visa artiklar med taggen test", browse_html)
        doc_html = self.client.get("/doc/alpha.md").get_data(as_text=True)
        self.assertIn("tag=test", doc_html)
        self.assertIn("Bläddra bland artiklar med taggen test", doc_html)

    def test_browse_preview_is_available_but_disabled_by_default(self):
        html = self.client.get("/browse").get_data(as_text=True)
        self.assertIn('id="articlePreview"', html)
        self.assertIn('data-enabled="false"', html)
        response = self.client.get("/api/doc-preview/alpha.md")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["title"], "Alfa")
        self.assertIn("title: Alfa", response.get_json()["frontmatter"])

    def test_create_document_and_reject_duplicate(self):
        data = {"title": "Årlig plan", "folder": "Mina projekt", "tags": "plan, viktigt", "body": "Innehåll"}
        response = self.client.post("/new", data=data)
        self.assertEqual(response.status_code, 302)
        created = self.config.paths.output / "mina-projekt" / "arlig-plan.md"
        self.assertTrue(created.exists())
        self.assertIn("viktigt", created.read_text(encoding="utf-8"))
        self.assertEqual(self.client.post("/new", data=data).status_code, 409)
        self.assertFalse((self.config.paths.skills / "SKILL.md").exists())

    def test_editing_document_does_not_generate_skills(self):
        response = self.client.post("/api/doc/alpha.md", json={"content": "# Ändrat\n"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse((self.config.paths.skills / "SKILL.md").exists())

    def test_download_and_path_protection(self):
        response = self.client.get("/doc/alpha.md/download")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertEqual(self.client.get("/doc/../config.yaml/download").status_code, 404)

    def test_document_renders_frontmatter_and_mermaid_support(self):
        (self.config.paths.output / "alpha.md").write_text(
            "---\ntitle: Alfa\n---\n\n- [ ] Öppen\n- [x] Klar\n\n> Viktigt\n\n```mermaid\ngraph TD\nA-->B\n```",
            encoding="utf-8",
        )
        response = self.client.get("/doc/alpha.md")
        html = response.get_data(as_text=True)
        self.assertIn("YAML-frontmatter", html)
        self.assertIn("mermaid@latest", html)
        self.assertIn('class="task-list"', html)
        self.assertIn('type="checkbox"', html)
        self.assertIn('checked="checked"', html)
        self.assertIn("<blockquote>", html)
        self.assertIn('id="mermaidDialog"', html)

    def test_editor_loads_monaco_with_textarea_fallback(self):
        response = self.client.get("/doc/alpha.md/edit")
        html = response.get_data(as_text=True)
        self.assertIn("monaco-editor@latest", html)
        self.assertIn('id="editArea"', html)

    def test_upload_multiple_documents_to_inbox_without_overwrite(self):
        response = self.client.post(
            "/upload",
            data={
                "folder": "Projekt Å",
                "files": [(BytesIO(b"first"), "rapport.txt"), (BytesIO(b"second"), "rapport.txt")],
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        folder = self.config.paths.inbox / "projekt-a"
        self.assertEqual((folder / "rapport.txt").read_bytes(), b"first")
        self.assertEqual((folder / "rapport-2.txt").read_bytes(), b"second")

    def test_upload_rejects_unsupported_extension(self):
        response = self.client.post(
            "/upload", data={"files": (BytesIO(b"bad"), "payload.exe")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse((self.config.paths.inbox / "payload.exe").exists())

    def test_create_processing_skill_with_document_presets(self):
        response = self.client.post(
            "/skills/new",
            data={
                "name": "Min rådgivare",
                "description": "Använd för testfrågor.",
                "instructions": "Läs dokumentet noggrant.",
                "documents": ["alpha.md"],
            },
        )
        self.assertEqual(response.status_code, 302)
        skill_path = self.config.paths.skills / "_custom" / "min-radgivare" / "SKILL.md"
        content = skill_path.read_text(encoding="utf-8")
        self.assertIn("document_paths", content)
        self.assertIn("alpha.md", content)
        self.assertEqual(list_custom_skills(self.config)[0]["document_paths"], ["alpha.md"])
        self.assertIn("Läs dokumentet noggrant", list_custom_skills(self.config)[0]["instructions"])

    def test_edit_custom_skill_code_with_validation(self):
        self.client.post(
            "/skills/new",
            data={"name": "Kodskill", "description": "Före redigering.", "documents": ["alpha.md"]},
        )
        rel_path = "_custom/kodskill/SKILL.md"
        edit_response = self.client.get(f"/skills/edit/{rel_path}")
        self.assertEqual(edit_response.status_code, 200)
        self.assertIn("monaco-editor@latest", edit_response.get_data(as_text=True))

        updated = "---\nname: kodskill\ndescription: Efter redigering.\ncustom: true\n---\n\n# Ny kod\n"
        save_response = self.client.post(f"/api/skill/{rel_path}", json={"content": updated})
        self.assertEqual(save_response.status_code, 200)
        skill_path = self.config.paths.skills / rel_path
        self.assertEqual(skill_path.read_text(encoding="utf-8"), updated)

        invalid = self.client.post(f"/api/skill/{rel_path}", json={"content": "---\nname: x\n---\n"})
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(skill_path.read_text(encoding="utf-8"), updated)

    def test_only_processing_skills_can_be_edited(self):
        self.config.paths.skills.joinpath("SKILL.md").write_text("legacy", encoding="utf-8")
        self.assertEqual(self.client.get("/skills/edit/SKILL.md").status_code, 404)
        self.assertEqual(self.client.get("/skills/edit/../config.yaml").status_code, 404)

    def test_run_skill_selects_documents_at_runtime(self):
        self.client.post(
            "/skills/new",
            data={"name": "Sammanfatta", "description": "Skapa en sammanfattning.", "instructions": "Lista huvudpunkterna."},
        )
        page = self.client.get("/skills/run/sammanfatta")
        self.assertEqual(page.status_code, 200)
        self.assertIn("alpha.md", page.get_data(as_text=True))
        response = self.client.post(
            "/api/skills/run",
            json={"skill": "sammanfatta", "document_paths": ["alpha.md"]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Ingen lokal AI", response.get_json()["error"])

    def test_skill_result_can_be_saved_as_document(self):
        response = self.client.post(
            "/api/skills/save-result",
            json={"skill": "sammanfatta", "title": "Min rapport", "body": "# Resultat\n\nKlart."},
        )
        self.assertEqual(response.status_code, 200)
        target = self.config.paths.output / "skill-resultat" / "min-rapport.md"
        self.assertTrue(target.exists())
        self.assertIn("generated_by_skill", target.read_text(encoding="utf-8"))

    def test_chat_shows_context_meter_and_processing_skills(self):
        self.client.post(
            "/skills/new",
            data={"name": "Granska", "description": "Granska underlaget.", "instructions": "Hitta risker."},
        )
        html = self.client.get("/chat").get_data(as_text=True)
        self.assertIn("Kontextfönster", html)
        self.assertIn("Granska", html)
        self.assertIn('"context_window": 32768', html)

    def test_temporary_chat_file_is_not_persisted(self):
        before_inbox = set(self.config.paths.inbox.rglob("*"))
        before_kb = set(self.config.paths.output.rglob("*"))
        response = self.client.post(
            "/api/chat/temp-file",
            data={"file": (BytesIO("Tillfällig information".encode()), "engang.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["body"], "Tillfällig information")
        self.assertEqual(set(self.config.paths.inbox.rglob("*")), before_inbox)
        self.assertEqual(set(self.config.paths.output.rglob("*")), before_kb)

    def test_slugify_handles_swedish_and_unsafe_characters(self):
        self.assertEqual(_slugify("Årlig plan / 2026"), "arlig-plan-2026")


if __name__ == "__main__":
    unittest.main()
