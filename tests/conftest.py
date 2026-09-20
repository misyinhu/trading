"""Configure pytest markers for all test cases."""


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: End-to-end test marker")
    config.addinivalue_line("markers", "l1: L1 smoke tests - UI element visibility")
    config.addinivalue_line("markers", "l2: L2 state transition tests - AC paths")
    config.addinivalue_line(
        "markers", "l3: L3 critical path tests - end-to-end journeys"
    )
    config.addinivalue_line(
        "markers", "critical_path: Critical path test (subset of L3)"
    )
    config.addinivalue_line(
        "markers", "ac: Acceptance criteria marker (e.g., ac_al_us1_1)"
    )
    config.addinivalue_line("markers", "us: User story marker (e.g., us_al_us1)")
    config.addinivalue_line(
        "markers", "happy_path: Happy path scenario - core functionality"
    )
    config.addinivalue_line("markers", "edge: Edge case scenario - boundary conditions")
    config.addinivalue_line("markers", "error: Error handling scenario - failure cases")
    config.addinivalue_line(
        "markers", "tab_state_isolation: Tab state transition tests"
    )
    config.addinivalue_line("markers", "tc: Test case marker with TC ID argument")
