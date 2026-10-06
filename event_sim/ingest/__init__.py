"""
Ingestion of external historical datasets.

Deliberately separate from the simulator: nothing here imports the engine, so a dataset can
be audited and profiled without any possibility of a model result influencing how it is
read.
"""
