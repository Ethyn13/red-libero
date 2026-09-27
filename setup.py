from pathlib import Path

from setuptools import find_packages, setup

root = Path(__file__).parent
studio_requirements = [
    line.strip()
    for line in (root / "requirements/studio.txt").read_text().splitlines()
    if line.strip() and not line.startswith("#")
]

setup(
    name="Red-LIBERO",
    version="0.1.0",
    description="Scene editing, physical risk scenarios, and VLA evaluation for RedVLA",
    long_description=(root / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="RedVLA contributors",
    url="https://ethyn13.github.io/Red-LIBERO/",
    license="MIT",
    license_files=["LICENSE", "NOTICE.md"],
    python_requires=">=3.10",
    packages=find_packages(include=["red_libero", "red_libero.*", "libero", "libero.*"]),
    include_package_data=True,
    install_requires=["numpy==1.26.4", "PyYAML>=6"],
    extras_require={"studio": studio_requirements},
)
