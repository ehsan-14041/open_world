"""
Blind detection path for Event #3.

Nothing in this package may import H1, the baseline world model, the engine, or any list of
known historical event dates. Detection has to be able to fail — and it can only fail
honestly if it has never seen the answer it is being asked to find.

`tests/test_event_sim_detection.py` asserts that property against the module source rather
than trusting this docstring.
"""
