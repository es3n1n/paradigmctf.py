import os

from .api import APIPwnLauncher
from .base import TeamInstanceLauncherBase, current_challenge
from .nc import NCPwnLauncher


LAUNCHER_MODE = os.getenv('LAUNCHER_MODE', 'nc')

PwnChallengeLauncher = {
    'nc': NCPwnLauncher,
    'api': APIPwnLauncher,
}[LAUNCHER_MODE]


__all__ = (
    'APIPwnLauncher',
    'NCPwnLauncher',
    'PwnChallengeLauncher',
    'TeamInstanceLauncherBase',
    'current_challenge',
)
