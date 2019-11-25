from launch_jenkins import get_url


def test_get_https():
    """
    Test that we can connect to a Jenkins instance over HTTPS.
    """
    get_url('https://rbalvjenkinf.bas.roche.com/api/json')
