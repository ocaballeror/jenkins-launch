from launch_jenkins import Session


def test_get_https():
    """
    Test that we can connect to a Jenkins instance over HTTPS.
    """
    session = Session('https://rbalvjenkinf.bas.roche.com')
    session.get_url('https://rbalvjenkinf.bas.roche.com/api/json')
