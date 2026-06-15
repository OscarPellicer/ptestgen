from pathlib import Path

from ptestgen.input_parser import parser


class _Extraction:
    def __init__(self, markdown, image_paths=None):
        self.markdown = markdown
        self.image_paths = image_paths or []


class _FakePevaluateUtils:
    @staticmethod
    def read_file_markdown(file_path, image_output_dir=None, image_reference_dir=None, markdown_config=None):
        image_output_dir = Path(image_output_dir)
        image_output_dir.mkdir(parents=True, exist_ok=True)
        figure = image_output_dir / "figure.png"
        figure.write_bytes(b"fake")
        return _Extraction(
            "Text before.\n\n![figure](source_assets/figure.png)\n\nText after.",
            [str(figure)],
        )


def test_parse_input_material_uses_shared_markdown_parser(monkeypatch, tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF fake")
    output_dir = tmp_path / "generated"

    monkeypatch.setattr(parser, "pevaluate_utils", _FakePevaluateUtils)

    markdown, images = parser.parse_input_material(str(source), output_dir=str(output_dir))

    assert "Text before." in markdown
    assert "![figure]" in markdown
    assert len(images) == 1
    assert images[0].endswith("figure.png")


def test_parse_input_material_does_not_return_stale_asset_files(monkeypatch, tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF fake")
    output_dir = tmp_path / "generated"
    assets_dir = output_dir / "source_assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "stale.png").write_bytes(b"old")

    monkeypatch.setattr(parser, "pevaluate_utils", _FakePevaluateUtils)

    _markdown, images = parser.parse_input_material(str(source), output_dir=str(output_dir))

    assert len(images) == 1
    assert images[0].endswith("figure.png")
    assert not any(path.endswith("stale.png") for path in images)
