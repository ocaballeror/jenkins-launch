from setuptools import setup

setup(
    name="jenkins_launch",
    description="Launch a jenkins job and wait for it to finish",
    version="1.0",
    author="Oscar Caballero",
    author_email="ocaballeror@tutanota.com",
    packages=['launch_jenkins'],
    install_requires=['requests'],
    entry_points={
        'console_scripts': [
            'launch_jenkins=launch_jenkins.launch_jenkins:main'
        ]
    },
)
