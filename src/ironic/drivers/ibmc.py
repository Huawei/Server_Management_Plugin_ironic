# TODO(bill.chan) license

from ironic.drivers import generic
from ironic.drivers.modules import noop
from ironic.drivers.modules.ibmc import management as ibmc_mgmt
from ironic.drivers.modules.ibmc import power as ibmc_power
from ironic.drivers.modules.ibmc import vendor as ibmc_vendor


class IBMCHardware(generic.GenericHardware):
    """Huawei iBMC hardware type."""

    @property
    def supported_management_interfaces(self):
        """List of supported management interfaces."""
        return [ibmc_mgmt.IBMCManagement]

    @property
    def supported_power_interfaces(self):
        """List of supported power interfaces."""
        return [ibmc_power.IBMCPower]

    @property
    def supported_vendor_interfaces(self):
        """List of supported vendor interfaces."""
        return [ibmc_vendor.IBMCVendor, noop.NoVendor]
