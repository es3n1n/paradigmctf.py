#!/usr/bin/env python3
from ctf_launchers import PwnChallengeLauncher, current_challenge


class Launcher(PwnChallengeLauncher):
    pass


current_challenge.bind(Launcher(project_location='/challenge/project'))


if __name__ == '__main__':
    current_challenge.run()
