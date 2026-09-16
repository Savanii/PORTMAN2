"""SRV02 — service recording numbered SRV1, SRV2, SRV3, ...

The same screen, the same service_records table and the same FIN01 billing
pickup as SRV01; only the record number format and the module code differ, so
everything is shared from modules/SRV01 rather than copied.
"""
from modules.SRV01.views import build_blueprint, MODULE_NAMES

MODULE_INFO = {'code': 'SRV02', 'name': MODULE_NAMES['SRV02']}
bp = build_blueprint(MODULE_INFO['code'])

__all__ = ['bp', 'MODULE_INFO']
