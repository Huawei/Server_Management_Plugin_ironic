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
import os
import datetime

from oslo_log import log
from oslo_utils import excutils
from oslo_utils import strutils
import retrying
import rfc3986
import requests
import six

from ironic.common import exception
from ironic.common.i18n import _
from ironic.conf import CONF
from ironic.drivers.modules.ibmc import constants

LOG = log.getLogger(__name__)

REQUIRED_PROPERTIES = {
    'ibmc_address': _('The URL address to the iBMC controller. It must '
                      'include the authority portion of the URL. '
                      'If the scheme is missing, https is assumed. '
                      'For example: https://mgmt.vendor.com. Required'),
    'ibmc_username': _('User account with admin/server-profile access '
                       'privilege. Required'),
    'ibmc_password': _('User account password. Required.'),
}

OPTIONAL_PROPERTIES = {
    'ibmc_system_id': _('IBMC system id For example: 1. If not specify, '
                        'defaults to the first one system. Optional'),
    'ibmc_verify_ca': _('Either a Boolean value, a path to a CA_BUNDLE '
                        'file or directory with certificates of trusted '
                        'CAs. If set to True the driver will verify the '
                        'host certificates; if False the driver will '
                        'ignore verifying the SSL certificate. If it\'s '
                        'a path the driver will use the specified '
                        'certificate or one of the certificates in the '
                        'directory. Defaults to True. Optional'),
}

COMMON_PROPERTIES = REQUIRED_PROPERTIES.copy()
COMMON_PROPERTIES.update(OPTIONAL_PROPERTIES)


def parse_driver_info(node):
    """Parse the information required for Ironic to connect to iBMC.

    :param node: an Ironic node object
    :returns: dictionary of parameters
    :raises: InvalidParameterValue on malformed parameter(s)
    :raises: MissingParameterValue on missing parameter(s)
    """
    driver_info = node.driver_info or {}
    missing_info = [key for key in REQUIRED_PROPERTIES
                    if not driver_info.get(key)]
    if missing_info:
        raise exception.MissingParameterValue(_(
            'Missing the following iBMC properties in node '
            '%(node)s driver_info: %(info)s') % {'node': node.uuid,
                                                 'info': missing_info})

    # Validate the iBMC address
    address = driver_info['ibmc_address']
    try:
        parsed = rfc3986.uri_reference(address)
    except TypeError:
        raise exception.InvalidParameterValue(
            _('Invalid iBMC address %(address)s set in '
              'driver_info/ibmc_address on node %(node)s') %
            {'address': address, 'node': node.uuid})

    if not parsed.scheme or not parsed.authority:
        address = 'https://%s' % address
        parsed = rfc3986.uri_reference(address)
    if not parsed.is_valid(require_scheme=True, require_authority=True):
        raise exception.InvalidParameterValue(
            _('Invalid iBMC address %(address)s set in '
              'driver_info/iBMC_address on node %(node)s') %
            {'address': address, 'node': node.uuid})

    # Check if verify_ca is a Boolean or a file/directory in the file-system
    verify_ca = driver_info.get('ibmc_verify_ca', True)
    if isinstance(verify_ca, six.string_types):
        if os.path.isdir(verify_ca) or os.path.isfile(verify_ca):
            pass
        else:
            try:
                verify_ca = strutils.bool_from_string(verify_ca, strict=True)
            except ValueError:
                raise exception.InvalidParameterValue(
                    _('Invalid value type set in driver_info/'
                      'ibmc_verify_ca on node %(node)s. '
                      'The value should be a Boolean or the path '
                      'to a file/directory, not "%(value)s"'
                      ) % {'value': verify_ca, 'node': node.uuid})
    elif isinstance(verify_ca, bool):
        # If it's a boolean it's grand, we don't need to do anything
        pass
    else:
        raise exception.InvalidParameterValue(
            _('Invalid value type set in driver_info/ibmc_verify_ca '
              'on node %(node)s. The value should be a Boolean or the path '
              'to a file/directory, not "%(value)s"') % {'value': verify_ca,
                                                         'node': node.uuid})
    return {'address': address,
            'system_id': driver_info.get('ibmc_system_id'),
            'username': driver_info.get('ibmc_username'),
            'password': driver_info.get('ibmc_password'),
            'verify_ca': verify_ca,
            'node_uuid': node.uuid}


class SessionCache(object):
    """Cache of HTTP sessions credentials"""
    MAX_SESSIONS = 1000

    sessions = collections.OrderedDict()

    def __init__(self, driver_info):
        self._driver_info = driver_info
        self._session_key = tuple(
            self._driver_info.get(key)
            for key in ('address', 'username', 'verify_ca')
        )

    def __enter__(self):
        try:
            return self.sessions[self._session_key]

        except KeyError:
            conn = IBMCService(
                self._driver_info['address'],
                username=self._driver_info['username'],
                password=self._driver_info['password'],
                verify_ca=self._driver_info['verify_ca']
            )

            self._expire_oldest_session()

            self.sessions[self._session_key] = conn

            return conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Give up the service when error occurred and exception is
        #  raised from requests lib
        if isinstance(exc_val, requests.exceptions.RequestException):
            self.sessions.pop(self._session_key, None)

    def _expire_oldest_session(self):
        """Expire oldest session"""
        if len(self.sessions) >= self.MAX_SESSIONS:
            session_keys = list(self.sessions)
            session_key = session_keys[0]
            self.sessions.pop(session_key, None)


def get_system(node):
    """Get a iBMC System that represents a node.

    :param node: An Ironic node object
    :raises: IBMCConnectionError when it fails to connect to iBMC
    :raises: IBMCError if the System is not registered in iBMC
    """
    driver_info = parse_driver_info(node)
    address = driver_info['address']
    system_id = driver_info['system_id']

    def _get_system():
        try:
            with SessionCache(driver_info) as conn:
                return conn.get_system(system_id)

        except requests.exceptions.RequestException as e:
            if (e.response is not None and e.response.status_code and
                    e.response.status_code == 404):
                # If it is a resource not found error, then log about
                #  the error, and re-raise a not-to-retry error
                LOG.error('The iBMC System "%(system)s" was not found for '
                          'node %(node)s. Error %(error)s',
                          {'system': system_id, 'node': node.uuid, 'error': e})
                raise exception.IBMCError(error=e)
            else:
                # Every other exceptions raise from requests lib,
                #  we need to retry the request
                LOG.warning('For node %(node)s, got a connection error from '
                            'iBMC at address "%(address)s" when fetching '
                            'System "%(system)s". Error: %(error)s',
                            {'system': system_id, 'address': address,
                             'node': node.uuid, 'error': e})
                raise exception.IBMCConnectionError(node=node.uuid, error=e)

    try:
        return _get_system()
    except exception.IBMCConnectionError as e:
        with excutils.save_and_reraise_exception():
            LOG.error('Failed to connect to iBMC at %(address)s for '
                      'node %(node)s. Error: %(error)s',
                      {'address': address, 'node': node.uuid, 'error': e})


class IBMCService(object):

    def __init__(self, address, username, password, verify_ca=True,
                 root_prefix='/redfish/v1'):
        """A class representing an iBMC RootService.

        :param address: IBMC address
        :param username: IBMC username
        :param password: IBMC password
        :param verify_ca: SSL Verification. Defaults to True
        :param root_prefix: The default URL prefix. This part includes
            the root service and version. Defaults to /redfish/v1
        """
        self._address = address
        self._username = username
        self._password = password
        self._verify_ca = verify_ca
        self._conn = IBMCConnector(verify_ca)

        root_service_url = '%s%s' % (address, root_prefix)
        r = self._conn.make_req('GET', root_service_url)
        json = r.json()

        self._systems_path = _load_from_json(
            json, ['Systems', '@odata.id'])
        self._session_service_path = _load_from_json(
            json, ['SessionService', '@odata.id'])
        self._ibmc_session = IBMCSession(self._conn,
                                         self._session_service_url(),
                                         self._username,
                                         self._password)
        self._conn.set_ibmc_session(self._ibmc_session)

    def _session_service_url(self):
        return '%s%s' % (self._address, self._session_service_path)

    def get_system(self, system_id=None):
        """Get IBMC System

        :param system_id: IBMC System identifier. If None,
            use first system
        :returns: IBMCSystem
        """
        return IBMCSystem(self._conn, system_id, self._address,
                          self._systems_path)


class IBMCConnector(object):
    # Default timeout in seconds for requests connect and read
    # http://docs.python-requests.org/en/master/user/advanced/#timeouts
    _DEFAULT_TIMEOUT = 30

    def __init__(self, verify=True):
        self._session = requests.Session()
        self._session.verify = verify
        self._session.headers.update({
            'Content-Type': 'application/json',
        })
        self._ibmc_session = None

    def set_ibmc_session(self, ibmc_session):
        self._ibmc_session = ibmc_session
        self._session.headers.update({
            'X-Auth-Token': self._ibmc_session.token,
        })

    def renew_ibmc_session(self):
        """Renew ibmc session, when expired"""
        self._ibmc_session.create()
        self._session.headers.update({
            'X-Auth-Token': self._ibmc_session.token,
        })

    def _get_resource_etag(self, url):
        r = self.make_req('GET', url)
        etag = r.headers.get('Etag') or r.headers.get('etag')
        if not etag:
            msg = 'Can not get resource[%s] etag' % url
            raise exception.IBMCError(msg)
        return etag

    @retrying.retry(
        retry_on_exception=(
                lambda e: isinstance(e, requests.exceptions.RequestException)),
        stop_max_attempt_number=CONF.ibmc.connection_attempts,
        wait_fixed=CONF.ibmc.connection_retry_interval * 1000)
    def make_req(self, method, url, json=None, headers=None):
        try:
            return self._make_req(method, url, json=json,
                                  headers=headers)
        except requests.exceptions.RequestException as e:
            if (e.response is not None and e.response.status_code and
                    e.response.status_code == 401):
                # Session expired, renew session then retry
                self.renew_ibmc_session()
                # Re merge session settings
                # req = requests.Request(method, url, json=json, headers=headers)
                # prepped = self._session.prepare_request(req)
                # r = self._session.send(prepped)
                # r.raise_for_status()
                return self._make_req(method, url, json=json,
                                      headers=headers)
            else:
                raise e

    def _make_req(self, method, url, json=None, headers=None):
        # If method is PATCH or PUT, get resource's etag first
        if method.lower() in ['patch', 'put']:
            etag = self._get_resource_etag(url)
            headers = headers or {}
            headers.update({'If-Match': etag})

        LOG.info('IBMC request: %(method)s, %(url)s', {
            'method': method,
            'url': url,
        })
        req = requests.Request(method, url, json=json, headers=headers)
        prepped = self._session.prepare_request(req)
        try:
            r = self._session.send(prepped, timeout=self._DEFAULT_TIMEOUT)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            if (e.response is not None and e.response.status_code and
                    e.response.status_code >= 500):
                # If it's server error, then log about the error,
                # and re-raise a not-to-retry error
                msg = ('IBMC server error: method: [%s], url: [%s], %s' %
                       (method, url, e.response.text))
                raise exception.IBMCError(error=msg)
            else:
                try:
                    ext_info = _load_from_json(
                        e.response.json(),
                        ['error', '@Message.ExtendedInfo'],
                        ignore_missing=True)
                    reason = (ext_info[0].get('Message')
                              if len(ext_info) else ext_info)
                except Exception:
                    reason = ''

                # Simply log about the exception, and re-raise to the
                #  outer try-catch, let it determine whether to retry
                #  the request
                msg = ('IBMC request error: method: [%s], url: [%s], '
                       'body: %s, headers: %s, reason: %s' % (
                           method, url, json, headers, reason
                       ))
                LOG.error(msg)
                raise e


class IBMCSession(object):

    def __init__(self, conn, url, username, password):
        """A class representing iBMC session object

        :param conn: requests.Session
        :param url: IBMC Session Service url
        :param username: IBMC username
        :param password: IBMC password
        """
        self._conn = conn
        self._url = url
        self._username = username
        self._password = password
        self._id = None
        self._token = None
        self._expire_at = None
        self.create()

    def create(self):
        json = {
            'UserName': self._username,
            'Password': self._password
        }
        create_session_url = '%s/Sessions' % self._url
        r = self._conn.make_req('POST', create_session_url, json=json)
        # TODO (Bill.Chan): Remove useless property `id` and `expire_at`
        #  at next release. Cause some old version iBMC API response is
        #  incompatible with spec
        id = _load_from_json(r.json(), 'Id')
        token = r.headers.get('X-Auth-Token')

        # get session timeout from session service
        r = self._conn.make_req('GET', self._url,
                                headers={'X-Auth-Token': token})
        session_timeout = _load_from_json(r.json(),
                                          'SessionTimeout')

        # minus 60 seconds, in case session expire early
        delta = datetime.timedelta(seconds=session_timeout - 60)
        expire_at = datetime.datetime.now() + delta

        self._id = id
        self._token = token
        self._expire_at = expire_at

    @property
    def token(self):
        return self._token

    @property
    def expire_at(self):
        return self._expire_at

    # TODO(Bill.Chan): Deprecated. Need to remove at next release
    def is_valid(self):
        expire_at = self._expire_at or datetime.datetime.now()
        return (self._id and self._token and
                expire_at < datetime.datetime.now())


class IBMCSystem:
    _BOOT_SEQUENCE_MAP = {
        'HardDiskDrive': 'Hdd',
        'DVDROMDrive': 'Cd',
        'PXE': 'Pxe',
    }

    def __init__(self, conn, id, address, systems_path):
        """A class representing iBMC System object.

        :param conn: IBMCConnector
        :param id: IBMC System identifier. If None, use first system.
        :param address: IBMC address
        :param systems_path: IBMC Systems path
        """
        self._conn = conn
        self._address = address
        self._systems_path = systems_path
        self._real_id = None
        self._json = None
        self._boot = None
        self._reset_path = None
        self._power_state = None
        self._bios_path = None

        if not id:
            r = self._conn.make_req('GET', self._systems_url())
            systems = _load_from_json(r.json(), 'Members')
            if not systems:
                raise exception.IBMCError(error='No system available')
            self._real_id = _load_from_json(systems[0], '@odata.id')
        else:
            self._real_id = id

        self.get()

    @property
    def id(self):
        return self._real_id

    @property
    def power_state(self):
        return self._power_state

    def _systems_url(self):
        return '%s%s' % (self._address, self._systems_path)

    def _system_url(self):
        return '%s%s' % (self._address, self._real_id)

    def _bios_url(self):
        return '%s%s' % (self._address, self._bios_path)

    def get(self):
        r = self._conn.make_req('GET', self._system_url())

        self._json = r.json()
        self._power_state = _load_from_json(self._json, 'PowerState')
        self._boot = _load_from_json(self._json, 'Boot')
        self._reset_path = _load_from_json(
            self._json,
            ['Actions', '#ComputerSystem.Reset', 'target'])
        self._bios_path = _load_from_json(self._json,
                                          ['Bios', '@odata.id'],
                                          ignore_missing=True)

    @property
    def boot(self):
        mode = _load_from_json(self._boot,
                               'BootSourceOverrideMode')
        target = _load_from_json(self._boot,
                                 'BootSourceOverrideTarget')
        enabled = _load_from_json(self._boot,
                                  'BootSourceOverrideEnabled')
        return {
            'target': target,
            'enabled': enabled,
            'mode': mode
        }

    @property
    def bios(self):
        r = self._conn.make_req('GET', self._bios_url())
        return _load_from_json(r.json(), 'Attributes')

    def set_system_boot_source(self, device, mode=None,
                               enabled=constants.BOOT_SOURCE_ENABLED_ONCE):
        """Set system boot source

        :param device: Boot device
        :param mode: Boot mode
        :param enabled: The frequency, whether to set it for the next
            reboot only (BOOT_SOURCE_ENABLED_ONCE) or persistent to all
            future reboots (BOOT_SOURCE_ENABLED_CONTINUOUS) or disabled
            (BOOT_SOURCE_ENABLED_DISABLED).
        """
        json = {
            'Boot': {
                'BootSourceOverrideTarget': device,
                'BootSourceOverrideEnabled': enabled,
            }
        }
        if mode:
            json['Boot']['BootSourceOverrideMode'] = mode

        self._conn.make_req('PATCH', self._system_url(), json=json)
        LOG.debug('Set boot device for iBMC finished')

    def get_supported_boot_devices(self):
        supported_boot_device = _load_from_json(
            self._boot,
            'BootSourceOverrideTarget@Redfish.AllowableValues')
        return supported_boot_device

    def reset_system(self, reset_type):
        """Restart a server

        :param reset_type: Reset type
        """
        json = {
            'ResetType': reset_type
        }
        url = '%s%s' % (self._address, self._reset_path)
        self._conn.make_req('POST', url, json=json)

    @property
    def boot_sequence(self):
        seq = _load_from_json(
            self._json,
            ['Oem', 'Huawei', 'BootupSequence'],
            ignore_missing=True)
        if not seq:
            attrs = self.bios
            keys = [k for k in attrs.keys()
                    if k.lower().startswith('boottypeorder')]
            seq = [attrs.get(t) for t in sorted(keys)]
            seq = self._boot_seq_v5tov3(seq)
        return seq

    def _boot_seq_v5tov3(self, boot_types):
        return [self._BOOT_SEQUENCE_MAP.get(t, t) for t in boot_types]


def _load_from_json(json, path, ignore_missing=False):
    """Load field from json.

    :param json: JSON object.
    :param path: Field path, string or string array. For example
        'Systems' will get field value from json.get('Systems'),
        ['Systems', 'data'] will get field value from
        json.get('Systems').get('data')
    :param ignore_missing: Ignore missing attribute
    :raises IBMCError: When no such attribute exists.
    :returns: Field value
    """
    if isinstance(path, six.string_types):
        path = [path]
    name = path[-1]
    body = json
    for path_item in path[:-1]:
        body = body.get(path_item) or {}

    if name not in body:
        if not ignore_missing:
            err_msg = _('Missing attribute %s, json: %s' % ('/'.join(path), json))
            raise exception.IBMCError(error=err_msg)
        else:
            return None

    return body[name]


def revert_dictionary(d):
    return {v: k for k, v in d.items()}
