# Pexams: Python Exam Generation and Correction

Pexams is a library for generating beautiful exam sheets from simple data structures and automatically correcting them from scans using computer vision. It is similar to R/exams, but written in Python and using [Marp](https://marp.app/) instead of LaTeX. It has the following advantages: 
- It uses Python and Marp, which makes it faster
- It is much easier to install, as it requires only Python and Marp, which are much easier to install than R + LaTeX
- It is easier to customize (it's Python + markdown!)
- It is less prone to compilation errors (again, no LaTeX!)



## Installation

Install the library in editable mode and set up the `pexams` command-line tool.

```bash
pip install -e .
```

For the library to work, you need to install Marp CLI. You can do this in one of two ways:
- **VS Code Extension (if using VS Code or a fork):** Install the "Marp for VS Code" extension. The library will attempt to automatically find the `marp` executable within the extension's installation directory.
- **Global Install:** Install `Node.js` from the [official Node.js website](https://nodejs.org/) and then run `npm install -g @marp-team/marp-cli`.

## Usage

### Command Line

To create a new exam from a set of questions in a Markdown file:

```bash
pexams generate --questions-md <path_to_questions.md> --output-dir <results_directory>
```

To correct a set of scans of an exam:

```bash
pexams correct --scans-pdf <path_to_scans.pdf> --solutions-json <path_to_solutions.json> --output-dir <results_directory>
```

### API

You can also use the Python API to generate and correct exams. For example:

```python
from autotestia.pexams import generate_exams, correct_exams
#TODO
```
