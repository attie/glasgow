from ... import *
from . import SigGenPatternApplet


class SigGenPatternAppletTestCase(GlasgowAppletTestCase, applet=SigGenPatternApplet):
    @synthesis_test
    def test_build(self):
        self.assertBuilds(args=[])
