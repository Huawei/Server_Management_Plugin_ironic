# TODO(bill.chan) license

from ironic.conductor import task_manager
from ironic.drivers.modules import iscsi_deploy
from ironic.drivers.modules import noop
from ironic.drivers.modules import pxe
from ironic.drivers.modules.ibmc import management as ibmc_mgmt
from ironic.drivers.modules.ibmc import power as ibmc_power
from ironic.drivers.modules.ibmc import vendor as ibmc_vendor
from ironic.tests.unit.db import base as db_base
from ironic.tests.unit.objects import utils as obj_utils


class IBMCHardwareTestCase(db_base.DbTestCase):

    def setUp(self):
        super(IBMCHardwareTestCase, self).setUp()
        self.config(enabled_hardware_types=['ibmc'],
                    enabled_power_interfaces=['ibmc'],
                    enabled_management_interfaces=['ibmc'],
                    enabled_vendor_interfaces=["ibmc"])

    def test_default_interfaces(self):
        node = obj_utils.create_test_node(self.context, driver='ibmc')
        with task_manager.acquire(self.context, node.id) as task:
            self.assertIsInstance(task.driver.management,
                                  ibmc_mgmt.IBMCManagement)
            self.assertIsInstance(task.driver.power,
                                  ibmc_power.IBMCPower)
            self.assertIsInstance(task.driver.boot, pxe.PXEBoot)
            self.assertIsInstance(task.driver.deploy, iscsi_deploy.ISCSIDeploy)
            self.assertIsInstance(task.driver.console, noop.NoConsole)
            self.assertIsInstance(task.driver.raid, noop.NoRAID)
            self.assertIsInstance(task.driver.vendor, ibmc_vendor.IBMCVendor)
