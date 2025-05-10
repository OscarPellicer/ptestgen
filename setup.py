import setuptools

def read_requirements(file_path="requirements.txt"):
    """Reads a requirements file and returns a list of dependencies."""
    with open(file_path, 'r') as f:
        requirements = f.read().splitlines()
    # Filter out comments and empty lines
    return [req for req in requirements if req and not req.startswith('#')]

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="autotestia",
    version="0.1.0",
    author="AutoTestIA Team (Oscar)",
    author_email="oscar.pellicer@uv.es",
    description="AI-powered tool for semi-automatic generation of multiple-choice questions.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/OscarPellicer/AutoTestIA",
    packages=setuptools.find_packages(),
    py_modules=['main'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Education",
        "Topic :: Education",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires='>=3.8',
    install_requires=read_requirements(),
    entry_points={
        'console_scripts': [
            'autotestia=main:main',
            'autotestia_split=autotestia.output_formatter.split_markdown:main',
            'autotestia_correct=autotestia.rexams.correct_exams:main',
        ],
    },
) 