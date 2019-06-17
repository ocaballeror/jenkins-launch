from setuptools import setup
from launch_jenkins import __version__

setup(
    name="jenkins_launch",
    description="Launch a jenkins job and wait for it to finish",
    version=__version__,
    author="Oscar Caballero",
    author_email="ocaballeror@tutanota.com",
    packages=['launch_jenkins'],
    entry_points={
        'console_scripts': [
            'launch_jenkins=launch_jenkins.launch_jenkins:main'
        ]
    },
    install_requires=[],
    extras_require={
        'dev': [
            'pytest',
            'pytest-cov',
            'flake8'
        ]
    },
)
