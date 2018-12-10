#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

# Version 1.0.0

import mock
import requests

from ironic.common import boot_devices
from ironic.common import boot_modes
from ironic.common import exception
from ironic.conductor import task_manager
from ironic.drivers.modules.ibmc import constants as cons
from ironic.drivers.modules.ibmc import mappings
from ironic.drivers.modules.ibmc import utils
from ironic.tests.unit.db import base as db_base
from ironic.tests.unit.db import utils as db_utils
from ironic.tests.unit.objects import utils as obj_utils

INFO_DICT = db_utils.get_test_ibmc_info()


class IBMCManagementTestCase(db_base.DbTestCase):

    def setUp(self):
        super(IBMCManagementTestCase, self).setUp()
        self.config(enabled_hardware_types=['ibmc'],
                    enabled_power_interfaces=['ibmc'],
                    enabled_management_interfaces=['ibmc'],
                    enabled_vendor_interfaces=['ibmc'])
        self.node = obj_utils.create_test_node(
            self.context, driver='ibmc', driver_info=INFO_DICT)

    def test_get_properties(self):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            properties = task.driver.get_properties()
            for prop in utils.COMMON_PROPERTIES:
                self.assertIn(prop, properties)

    @mock.patch.object(utils, 'parse_driver_info', autospec=True)
    def test_validate(self, mock_parse_driver_info):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            task.driver.management.validate(task)
            mock_parse_driver_info.assert_called_once_with(task.node)

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_get_supported_boot_devices(self, mock_get_system):
        get_supported_boot_devices = mock.Mock().get_supported_boot_devices
        get_supported_boot_devices.return_value = (
            list(mappings.BOOT_DEVICE_MAP)
        )
        fake_system = mock.Mock()
        fake_system.get_supported_boot_devices = get_supported_boot_devices
        mock_get_system.return_value = fake_system
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            supported_boot_devices = (
                task.driver.management.get_supported_boot_devices(task))
            mock_get_system.assert_called_once_with(task.node)
            self.assertEqual(sorted(list(mappings.BOOT_DEVICE_MAP_REV)),
                             sorted(supported_boot_devices))

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_set_boot_device(self, mock_get_system):
        fake_system = mock.Mock()
        mock_get_system.return_value = fake_system
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            expected_values = [
                (boot_devices.PXE, cons.BOOT_SOURCE_TARGET_PXE),
                (boot_devices.DISK, cons.BOOT_SOURCE_TARGET_HDD),
                (boot_devices.CDROM, cons.BOOT_SOURCE_TARGET_CD),
                (boot_devices.BIOS, cons.BOOT_SOURCE_TARGET_BIOS_SETUP),
                ('floppy', cons.BOOT_SOURCE_TARGET_FLOPPY),
            ]

            for target, expected in expected_values:
                task.driver.management.set_boot_device(task, target)

                # Asserts
                fake_system.set_system_boot_source.assert_called_once_with(
                    expected, enabled=cons.BOOT_SOURCE_ENABLED_ONCE)
                mock_get_system.assert_called_once_with(task.node)

                # Reset mocks
                fake_system.set_system_boot_source.reset_mock()
                mock_get_system.reset_mock()

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_set_boot_device_persistency(self, mock_get_system):
        fake_system = mock.Mock()
        mock_get_system.return_value = fake_system
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            expected_values = [
                (True, cons.BOOT_SOURCE_ENABLED_CONTINUOUS),
                (False, cons.BOOT_SOURCE_ENABLED_ONCE)
            ]

            for target, expected in expected_values:
                task.driver.management.set_boot_device(
                    task, boot_devices.PXE, persistent=target)

                fake_system.set_system_boot_source.assert_called_once_with(
                    cons.BOOT_SOURCE_TARGET_PXE, enabled=expected)
                mock_get_system.assert_called_once_with(task.node)

                # Reset mocks
                fake_system.set_system_boot_source.reset_mock()
                mock_get_system.reset_mock()

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_set_boot_device_fail(self, mock_get_system):
        fake_system = mock.Mock()
        fake_system.set_system_boot_source.side_effect = (
            requests.exceptions.RequestException
        )
        mock_get_system.return_value = fake_system
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaisesRegex(
                exception.IBMCError, 'IBMC set boot device',
                task.driver.management.set_boot_device, task, boot_devices.PXE)
            fake_system.set_system_boot_source.assert_called_once_with(
                cons.BOOT_SOURCE_TARGET_PXE,
                enabled=cons.BOOT_SOURCE_ENABLED_ONCE)
            mock_get_system.assert_called_once_with(task.node)

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_get_boot_device(self, mock_get_system):
        boot_attribute = {
            'target': cons.BOOT_SOURCE_TARGET_PXE,
            'enabled': cons.BOOT_SOURCE_ENABLED_CONTINUOUS
        }
        fake_system = mock.Mock(boot=boot_attribute)
        mock_get_system.return_value = fake_system
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            response = task.driver.management.get_boot_device(task)
            expected = {'boot_device': boot_devices.PXE,
                        'persistent': True}
            self.assertEqual(expected, response)

    def test_get_supported_boot_modes(self):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            supported_boot_modes = (
                task.driver.management.get_supported_boot_modes(task))
            self.assertEqual(list(mappings.BOOT_MODE_MAP_REV),
                             supported_boot_modes)

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_set_boot_mode(self, mock_get_system):
        boot = {
            'target': mock.ANY,
            'enabled': mock.ANY,
        }
        fake_system = mock.Mock(boot=boot)
        mock_get_system.return_value = fake_system
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            expected_values = [
                (boot_modes.LEGACY_BIOS, cons.BOOT_SOURCE_MODE_BIOS),
                (boot_modes.UEFI, cons.BOOT_SOURCE_MODE_UEFI)
            ]

            for mode, expected in expected_values:
                task.driver.management.set_boot_mode(task, mode=mode)

                # Asserts
                fake_system.set_system_boot_source.assert_called_once_with(
                    mock.ANY, enabled=mock.ANY, mode=expected)
                mock_get_system.assert_called_once_with(task.node)

                # Reset mocks
                fake_system.set_system_boot_source.reset_mock()
                mock_get_system.reset_mock()

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_set_boot_mode_fail(self, mock_get_system):
        boot = {
            'target': mock.ANY,
            'enabled': mock.ANY,
        }
        fake_system = mock.Mock(boot=boot)
        fake_system.set_system_boot_source.side_effect = (
            requests.exceptions.RequestException
        )
        mock_get_system.return_value = fake_system
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaisesRegex(
                exception.IBMCError, 'Setting boot mode',
                task.driver.management.set_boot_mode, task, boot_modes.UEFI)
            fake_system.set_system_boot_source.assert_called_once_with(
                mock.ANY,
                enabled=mock.ANY,
                mode=mappings.BOOT_MODE_MAP_REV[boot_modes.UEFI])
            mock_get_system.assert_called_once_with(task.node)

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_get_boot_mode(self, mock_get_system):
        boot_attribute = {
            'target': cons.BOOT_SOURCE_TARGET_PXE,
            'enabled': cons.BOOT_SOURCE_ENABLED_CONTINUOUS,
            'mode': cons.BOOT_SOURCE_MODE_BIOS,
        }
        fake_system = mock.Mock(boot=boot_attribute)
        mock_get_system.return_value = fake_system
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            response = task.driver.management.get_boot_mode(task)
            expected = boot_modes.LEGACY_BIOS
            self.assertEqual(expected, response)

    def test_get_sensors_data(self):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            self.assertRaises(NotImplementedError,
                              task.driver.management.get_sensors_data, task)

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_inject_nmi(self, mock_get_system):
        fake_system = mock.Mock()
        mock_get_system.return_value = fake_system
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            task.driver.management.inject_nmi(task)
            fake_system.reset_system.assert_called_once_with(cons.RESET_NMI)
            mock_get_system.assert_called_once_with(task.node)

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_inject_nmi_fail(self, mock_get_system):
        fake_system = mock.Mock()
        fake_system.reset_system.side_effect = (
            requests.exceptions.RequestException
        )
        mock_get_system.return_value = fake_system
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaisesRegex(
                exception.IBMCError, 'IBMC inject NMI',
                task.driver.management.inject_nmi, task)
            fake_system.reset_system.assert_called_once_with(
                cons.RESET_NMI)
            mock_get_system.assert_called_once_with(task.node)
