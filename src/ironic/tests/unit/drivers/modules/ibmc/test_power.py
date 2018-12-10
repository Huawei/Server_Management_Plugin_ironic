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

from ironic.common import exception
from ironic.common import states
from ironic.conductor import task_manager
from ironic.drivers.modules.ibmc import constants as cons
from ironic.drivers.modules.ibmc import mappings
from ironic.drivers.modules.ibmc import utils
from ironic.tests.unit.db import base as db_base
from ironic.tests.unit.db import utils as db_utils
from ironic.tests.unit.objects import utils as obj_utils

INFO_DICT = db_utils.get_test_ibmc_info()


@mock.patch('eventlet.greenthread.sleep', lambda _t: None)
class IBMCPowerTestCase(db_base.DbTestCase):

    def setUp(self):
        super(IBMCPowerTestCase, self).setUp()
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
            task.driver.power.validate(task)
            mock_parse_driver_info.assert_called_once_with(task.node)

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_get_power_state(self, mock_get_system):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            expected_values = mappings.GET_POWER_STATE_MAP
            for current, expected in expected_values.items():
                mock_get_system.return_value = mock.Mock(power_state=current)
                self.assertEqual(expected,
                                 task.driver.power.get_power_state(task))
                mock_get_system.assert_called_once_with(task.node)
                mock_get_system.reset_mock()

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_set_power_state(self, mock_get_system):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            expected_values = mappings.SET_POWER_STATE_MAP_REV

            for target, expected in expected_values.items():
                if target in (states.POWER_OFF, states.SOFT_POWER_OFF):
                    final = cons.SYSTEM_POWER_STATE_OFF
                    transient = cons.SYSTEM_POWER_STATE_ON
                else:
                    final = cons.SYSTEM_POWER_STATE_ON
                    transient = cons.SYSTEM_POWER_STATE_OFF

                system_result = [
                    mock.Mock(power_state=transient)
                ] * 3 + [mock.Mock(power_state=final)]
                mock_get_system.side_effect = system_result

                task.driver.power.set_power_state(task, target)

                # Asserts
                system_result[0].reset_system.assert_called_once_with(expected)
                mock_get_system.assert_called_with(task.node)
                self.assertEqual(4, mock_get_system.call_count)

                # Reset mocks
                mock_get_system.reset_mock()

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_set_power_state_not_reached(self, mock_get_system):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.config(power_state_change_timeout=2, group='conductor')

            expected_values = mappings.SET_POWER_STATE_MAP_REV
            for target, expected in expected_values.items():
                fake_system = mock_get_system.return_value
                if target in (states.POWER_OFF, states.SOFT_POWER_OFF):
                    fake_system.power_state = cons.SYSTEM_POWER_STATE_ON
                else:
                    fake_system.power_state = cons.SYSTEM_POWER_STATE_OFF

                self.assertRaises(exception.PowerStateFailure,
                                  task.driver.power.set_power_state,
                                  task, target)

                # Asserts
                fake_system.reset_system.assert_called_once_with(expected)
                mock_get_system.assert_called_with(task.node)

                # Reset mocks
                mock_get_system.reset_mock()

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_set_power_state_fail(self, mock_get_system):
        fake_system = mock_get_system.return_value
        fake_system.reset_system.side_effect = (
            requests.exceptions.RequestException
        )

        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            self.assertRaisesRegex(
                exception.IBMCError, 'IBMC set power state',
                task.driver.power.set_power_state, task, states.POWER_ON)
            fake_system.reset_system.assert_called_once_with(
                cons.RESET_ON)
            mock_get_system.assert_called_once_with(task.node)

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_reboot(self, mock_get_system):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            expected_values = [
                (cons.SYSTEM_POWER_STATE_OFF, cons.RESET_ON),
                (cons.SYSTEM_POWER_STATE_ON, cons.RESET_FORCE_RESTART)
            ]

            for current, expected in expected_values:
                system_result = [
                    # Initial state
                    mock.Mock(power_state=current),
                    # Transient state - powering off
                    mock.Mock(power_state=cons.SYSTEM_POWER_STATE_OFF),
                    # Final state - down powering off
                    mock.Mock(power_state=cons.SYSTEM_POWER_STATE_ON)
                ]
                mock_get_system.side_effect = system_result

                task.driver.power.reboot(task)

                # Asserts
                system_result[0].reset_system.assert_called_once_with(expected)
                mock_get_system.assert_called_with(task.node)
                self.assertEqual(3, mock_get_system.call_count)

                # Reset mocks
                mock_get_system.reset_mock()

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_reboot_not_reached(self, mock_get_system):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            fake_system = mock_get_system.return_value
            fake_system.power_state = cons.SYSTEM_POWER_STATE_OFF

            self.assertRaises(exception.PowerStateFailure,
                              task.driver.power.reboot, task)

            # Asserts
            fake_system.reset_system.assert_called_once_with(cons.RESET_ON)
            mock_get_system.assert_called_with(task.node)

    @mock.patch.object(utils, 'get_system', autospec=True)
    def test_reboot_fail(self, mock_get_system):
        fake_system = mock_get_system.return_value
        fake_system.reset_system.side_effect = (
            requests.exceptions.RequestException
        )

        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=False) as task:
            fake_system.power_state = cons.SYSTEM_POWER_STATE_ON
            self.assertRaisesRegex(
                exception.IBMCError, 'IBMC reboot failed',
                task.driver.power.reboot, task)
            fake_system.reset_system.assert_called_once_with(
                cons.RESET_FORCE_RESTART)
            mock_get_system.assert_called_once_with(task.node)

    def test_get_supported_power_states(self):
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            supported_power_states = (
                task.driver.power.get_supported_power_states(task))
            self.assertEqual(sorted(list(mappings.SET_POWER_STATE_MAP_REV)),
                             sorted(supported_power_states))
