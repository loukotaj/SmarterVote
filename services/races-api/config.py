import os

from constants import DEFAULT_DATA_DIR

DATA_DIR = os.getenv("DATA_DIR", DEFAULT_DATA_DIR)
