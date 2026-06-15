from .interface_main import Interface

try:
    from .interface_pyqt5 import InterfacePyQt5
except ImportError:
    InterfacePyQt5 = None

__all__ = ["Interface", "InterfacePyQt5"]
