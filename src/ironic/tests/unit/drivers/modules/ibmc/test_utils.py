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

import collections
import copy
import os

import mock
import requests

from ironic.common import exception
from ironic.drivers.modules.ibmc import utils as ibmc_utils
from ironic.tests.unit.db import base as db_base
from ironic.tests.unit.db import utils as db_utils
from ironic.tests.unit.objects import utils as obj_utils

INFO_DICT = db_utils.get_test_ibmc_info()


class IBMCUtilsTestCase(db_base.DbTestCase):

    def setUp(self):
        super(IBMCUtilsTestCase, self).setUp()
        # Default configurations
        self.config(enabled_hardware_types=['ibmc'],
                    enabled_power_interfaces=['ibmc'],
                    enabled_management_interfaces=['ibmc'])
        # Redfish specific configurations
        self.config(connection_attempts=1, group='ibmc')
        self.node = obj_utils.create_test_node(
            self.context, driver='ibmc', driver_info=INFO_DICT)
        self.parsed_driver_info = {
            'address': 'https://example.com',
            'system_id': '/redfish/v1/Systems/FAKESYSTEM',
            'username': 'username',
            'password': 'password',
            'verify_ca': True,
            'node_uuid': self.node.uuid
        }

    def test_parse_driver_info(self):
        response = ibmc_utils.parse_driver_info(self.node)
        self.assertEqual(self.parsed_driver_info, response)

    def test_parse_driver_info_default_scheme(self):
        self.node.driver_info['ibmc_address'] = 'example.com'
        response = ibmc_utils.parse_driver_info(self.node)
        self.assertEqual(self.parsed_driver_info, response)

    def test_parse_driver_info_default_scheme_with_port(self):
        self.node.driver_info['ibmc_address'] = 'example.com:42'
        self.parsed_driver_info['address'] = 'https://example.com:42'
        response = ibmc_utils.parse_driver_info(self.node)
        self.assertEqual(self.parsed_driver_info, response)

    def test_parse_driver_info_missing_info(self):
        for prop in ibmc_utils.REQUIRED_PROPERTIES:
            self.node.driver_info = INFO_DICT.copy()
            self.node.driver_info.pop(prop)
            self.assertRaises(exception.MissingParameterValue,
                              ibmc_utils.parse_driver_info, self.node)

    def test_parse_driver_info_invalid_address(self):
        for value in ['/banana!', 42]:
            self.node.driver_info['ibmc_address'] = value
            self.assertRaisesRegex(exception.InvalidParameterValue,
                                   'Invalid iBMC address',
                                   ibmc_utils.parse_driver_info, self.node)

    @mock.patch.object(os.path, 'isdir', autospec=True)
    def test_parse_driver_info_path_verify_ca(self,
                                              mock_isdir):
        mock_isdir.return_value = True
        fake_path = '/path/to/a/valid/CA'
        self.node.driver_info['ibmc_verify_ca'] = fake_path
        self.parsed_driver_info['verify_ca'] = fake_path

        response = ibmc_utils.parse_driver_info(self.node)
        self.assertEqual(self.parsed_driver_info, response)
        mock_isdir.assert_called_once_with(fake_path)

    @mock.patch.object(os.path, 'isfile', autospec=True)
    def test_parse_driver_info_valid_capath(self, mock_isfile):
        mock_isfile.return_value = True
        fake_path = '/path/to/a/valid/CA.pem'
        self.node.driver_info['ibmc_verify_ca'] = fake_path
        self.parsed_driver_info['verify_ca'] = fake_path

        response = ibmc_utils.parse_driver_info(self.node)
        self.assertEqual(self.parsed_driver_info, response)
        mock_isfile.assert_called_once_with(fake_path)

    def test_parse_driver_info_invalid_value_verify_ca(self):
        # Integers are not supported
        self.node.driver_info['ibmc_verify_ca'] = 123456
        self.assertRaisesRegex(exception.InvalidParameterValue,
                               'Invalid value type',
                               ibmc_utils.parse_driver_info, self.node)

    def test_parse_driver_info_valid_string_value_verify_ca(self):
        for value in ('0', 'f', 'false', 'off', 'n', 'no'):
            self.node.driver_info['ibmc_verify_ca'] = value
            response = ibmc_utils.parse_driver_info(self.node)
            parsed_driver_info = copy.deepcopy(self.parsed_driver_info)
            parsed_driver_info['verify_ca'] = False
            self.assertEqual(parsed_driver_info, response)

        for value in ('1', 't', 'true', 'on', 'y', 'yes'):
            self.node.driver_info['ibmc_verify_ca'] = value
            response = ibmc_utils.parse_driver_info(self.node)
            self.assertEqual(self.parsed_driver_info, response)

    def test_parse_driver_info_invalid_string_value_verify_ca(self):
        for value in ('xyz', '*', '!123', '123'):
            self.node.driver_info['ibmc_verify_ca'] = value
            self.assertRaisesRegex(exception.InvalidParameterValue,
                                   'The value should be a Boolean',
                                   ibmc_utils.parse_driver_info, self.node)

    @mock.patch.object(ibmc_utils, 'IBMCService', autospec=True)
    @mock.patch('ironic.drivers.modules.ibmc.utils.'
                'SessionCache.sessions', {})
    def test_get_system(self, mock_service):
        fake_conn = mock_service.return_value
        fake_system = fake_conn.get_system.return_value
        response = ibmc_utils.get_system(self.node)
        self.assertEqual(fake_system, response)
        fake_conn.get_system.assert_called_once_with(
            '/redfish/v1/Systems/FAKESYSTEM')

    @mock.patch.object(ibmc_utils, 'IBMCService', autospec=True)
    @mock.patch('ironic.drivers.modules.ibmc.utils.'
                'SessionCache.sessions', {})
    def test_get_system_resource_not_found(self, mock_service):
        fake_conn = mock_service.return_value
        response = requests.Response()
        response.status_code = 404
        fake_conn.get_system.side_effect = (
            requests.exceptions.RequestException(response=response)
        )

        self.assertRaises(exception.IBMCError,
                          ibmc_utils.get_system, self.node)
        fake_conn.get_system.assert_called_once_with(
            '/redfish/v1/Systems/FAKESYSTEM')

    @mock.patch.object(ibmc_utils, 'IBMCService', autospec=True)
    @mock.patch('ironic.drivers.modules.ibmc.utils.'
                'SessionCache.sessions', {})
    def test_auth_auto(self, mock_service):
        ibmc_utils.get_system(self.node)
        mock_service.assert_called_with(
            self.parsed_driver_info['address'],
            username=self.parsed_driver_info['username'],
            password=self.parsed_driver_info['password'],
            verify_ca=True)

    @mock.patch.object(ibmc_utils, 'IBMCService', autospec=True)
    @mock.patch('ironic.drivers.modules.ibmc.utils.'
                'SessionCache.sessions', {})
    def test_ensure_session_reuse(self, mock_service):
        ibmc_utils.get_system(self.node)
        ibmc_utils.get_system(self.node)
        self.assertEqual(1, mock_service.call_count)

    @mock.patch.object(ibmc_utils, 'IBMCService', autospec=True)
    def test_ensure_new_session_address(self, mock_service):
        self.node.driver_info['ibmc_address'] = 'http://bmc.foo'
        ibmc_utils.get_system(self.node)
        self.node.driver_info['ibmc_address'] = 'http://bmc.bar'
        ibmc_utils.get_system(self.node)
        self.assertEqual(2, mock_service.call_count)

    @mock.patch.object(ibmc_utils, 'IBMCService', autospec=True)
    def test_ensure_new_session_username(self, mock_service):
        self.node.driver_info['ibmc_username'] = 'foo'
        ibmc_utils.get_system(self.node)
        self.node.driver_info['ibmc_username'] = 'bar'
        ibmc_utils.get_system(self.node)
        self.assertEqual(2, mock_service.call_count)

    @mock.patch.object(ibmc_utils, 'IBMCService', autospec=True)
    @mock.patch('ironic.drivers.modules.ibmc.utils.'
                'SessionCache.MAX_SESSIONS', 10)
    @mock.patch('ironic.drivers.modules.ibmc.utils.SessionCache.sessions',
                collections.OrderedDict())
    def test_expire_old_sessions(self, mock_service):
        for num in range(20):
            self.node.driver_info['ibmc_username'] = 'foo-%d' % num
            ibmc_utils.get_system(self.node)

        self.assertEqual(mock_service.call_count, 20)
        self.assertEqual(len(ibmc_utils.SessionCache.sessions), 10)
