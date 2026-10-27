"""akari (明かり): cápsulas de escritorio para Linux y Windows con el uso de Claude Code / Codex,
la batería de tus periféricos y tus habilidades de IA."""

import os

VERSION = "0.1.0"
PUERTO = int(os.environ.get("AKARI_PUERTO") or 47830)     # otro puerto solo para pruebas
