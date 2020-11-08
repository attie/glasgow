# I2C reference: https://www.nxp.com/docs/en/user-guide/UM10204.pdf

from nmigen.compat import *
from nmigen.compat.genlib.cdc import MultiReg


__all__ = ["I2CInitiator", "I2CTarget"]


from .i2c_nmigen import I2CBus
from .i2c_nmigen import I2CInitiator
from .i2c_compat import I2CTarget

# -------------------------------------------------------------------------------------------------

from .i2c_nmigen import I2CTestbench
from .i2c_nmigen import I2CInitiatorTestbench
from .i2c_nmigen import I2CTargetTestbench
