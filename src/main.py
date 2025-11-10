import asyncio
from viam.module.module import Module
try:
    from models.calibration_webapp_with_watcher import CalibrationWebAppWithWatcher
    models = [CalibrationWebAppWithWatcher]
except ModuleNotFoundError:
    # when running as local module with run.sh
    from .models.calibration_webapp_with_watcher import CalibrationWebAppWithWatcher
    models = [CalibrationWebAppWithWatcher]


if __name__ == '__main__':
    asyncio.run(Module.run_with_models(*models))
