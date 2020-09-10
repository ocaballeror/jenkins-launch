from setuptools import setup
from launch_jenkins import __version__

setup(
    name="launch_jenkins",
    description="Launch a jenkins job and wait for it to finish",
    version=__version__,
    author="Oscar Caballero",
    author_email="ocaballeror@tutanota.com",
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'Environment :: Console',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
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
