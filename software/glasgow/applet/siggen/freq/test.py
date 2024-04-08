from ... import *
from . import SigGenFreqApplet


class SigGenFreqAppletTestCase(GlasgowAppletTestCase, applet=SigGenFreqApplet):
    @synthesis_test
    def test_build(self):
        self.assertBuilds(args=[])
