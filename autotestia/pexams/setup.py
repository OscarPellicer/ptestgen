from setuptools import setup, find_packages

setup(
    name="pexams",
    version="0.1.0",
    description="A Python library for generating and correcting exams using Marp and OpenCV.",
    author="AutoTestIA",
    packages=find_packages(),
    install_requires=[
        "opencv-python",
        "numpy",
        "pdf2image",
        "pydantic",
        "marp-cli" 
    ],
    entry_points={
        'console_scripts': [
            'pexams=pexams.main:main',
        ],
    },
)
