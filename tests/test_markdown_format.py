"""ptestgen reads questions.md with the pexams parser and keeps code, images and math on export."""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import cv2
import numpy as np

from ptestgen import artifacts

REPO_ROOT = Path(__file__).resolve().parents[1]

FORMAT_MD = textwrap.dedent("""\
    # Questions for Manual Review

    ## code_q
    **Careful:** what does this print?

    ```python
    ## not a header
    - not an option
    print(x_1 * y_2)
    ```
    * `2`
    * $x_1$

    ## main_img
    > ![Image for question](img/fig.png)
    Main image below, and $$\\frac{a_1}{b_2}$$ display math.
    * yes
    * no

    ## open_q {type=open lines=4}
    > ![w:30mm right|A figure](img/fig.png)
    Explain ![h:10mm](img/fig.png) this.
    Second line, cost \\$5.

    **Answer area:**
    lines: 6

    **Expected answer:**
    Something.
    """)


def _write_exam(tmp_path):
    (tmp_path / "img").mkdir()
    image = np.full((100, 150, 3), 255, np.uint8)
    image[5:-5, 5:-5] = (255, 0, 0)
    cv2.imwrite(str(tmp_path / "img" / "fig.png"), image)
    md_path = tmp_path / "exam.md"
    md_path.write_text(FORMAT_MD, encoding="utf-8")
    return md_path


def test_read_questions_md_handles_code_bold_and_images(tmp_path):
    questions = artifacts.read_questions_md(str(_write_exam(tmp_path)))

    assert list(questions) == ["code_q", "main_img", "open_q"]
    code_q = questions["code_q"]
    assert code_q.text.startswith("**Careful:**")
    assert "## not a header" in code_q.text and "- not an option" in code_q.text
    assert code_q.options == ["`2`", "$x_1$"]

    main_img = questions["main_img"]
    assert main_img.image_reference is None  # the old image line is an ordinary image below the text
    assert main_img.text.endswith("display math.\n\n![Image for question](img/fig.png)")

    open_q = questions["open_q"]
    assert open_q.image_reference is None
    assert open_q.text.startswith("![w:30mm right|A figure](img/fig.png) Explain ![h:10mm](img/fig.png) this.")
    assert "Answer area" not in open_q.text
    assert open_q.answer_lines == 6
    assert open_q.expected_answer == "Something."


def test_export_pexams_keeps_code_images_and_math(tmp_path):
    md_path = _write_exam(tmp_path)

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "main.py"), "export", "pexams", str(md_path), "--num-models", "1", "--keep-html"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    out_dir = tmp_path / "exam_pexams_output"
    questions = {q["original_id"]: q for q in json.loads((out_dir / "exam_model_1_questions.json").read_text(encoding="utf-8"))["questions"]}
    assert "```python" in questions["code_q"]["text"]
    assert questions["main_img"]["image_source"] is None
    assert questions["main_img"]["text"].endswith(f"![Image for question]({(tmp_path / 'img' / 'fig.png').as_uri()})")

    html = (out_dir / "exam_model_1.html").read_text(encoding="utf-8")
    assert "<pre>" in html and "## not a header" in html
    assert 'alt="A figure" class="pexams-img-right" style="width: 30mm;" src="file://' in html
    assert 'style="height: 10mm; width: auto;"' in html
    assert r'<span class="arithmatex">\[\frac{a_1}{b_2}\]</span>' in html
    assert r'<span class="arithmatex">\(x_1\)</span>' in html
    assert "&#36;5" in html
    areas = json.loads((out_dir / "open_answer_areas.json").read_text(encoding="utf-8"))
    assert [a["original_id"] for a in areas] == ["open_q"]
