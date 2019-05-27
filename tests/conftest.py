import pytest

from launch_jenkins import launch_jenkins


@pytest.fixture
def config():
    backup = launch_jenkins.CONFIG.copy()
    try:
        yield
    finally:
        launch_jenkins.CONFIG = backup
