from setuptools import setup

setup(
    name="jenkins_launch",
    description="Launch a jenkins job and wait for it to finish",
    version="2.1",
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
