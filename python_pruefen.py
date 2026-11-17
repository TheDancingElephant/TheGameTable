"""Hilfe für python_finden.bat: gibt den Pfad dieses Interpreters aus, wenn er für den Spieltisch taugt (3.10+)."""
import sys

if sys.version_info >= (3, 10):
    print(sys.executable)
else:
    sys.exit(1)
