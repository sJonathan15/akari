#!/usr/bin/env python3
"""Lanzador de akari para cualquier sistema (también Windows): python bin/akari.py <orden>.
No depende de PYTHONPATH, así sirve igual con el Python embebido de la app de Windows."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from akari.__main__ import main  # noqa: E402

main()
