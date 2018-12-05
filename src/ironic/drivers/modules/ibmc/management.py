# TODO(bill.chan) license

from oslo_log import log
import requests

from ironic.common import exception
from ironic.common.i18n import _
from ironic.conductor import task_manager
from ironic.drivers import base
from ironic.drivers.modules.ibmc import constants
from ironic.drivers.modules.ibmc import mappings
from ironic.drivers.modules.ibmc import utils

LOG = log.getLogger(__name__)


class IBMCManagement(base.ManagementInterface):

    def __init__(self):
        """Initialize the iBMC management interface"""
        super(IBMCManagement, self).__init__()

    def get_properties(self):
        """Return the properties of the interface.

        :returns: dictionary of <property name>:<property description> entries.
        """
        return utils.COMMON_PROPERTIES.copy()

    def validate(self, task):
        """Validates the driver information needed by the iBMC driver.

        :param task: A TaskManager instance containing the node to act on.
        :raises: InvalidParameterValue on malformed parameter(s)
        :raises: MissingParameterValue on missing parameter(s)
        """
        utils.parse_driver_info(task.node)

    def get_supported_boot_devices(self, task):
        """Get a list of the supported boot devices.

        :param task: a task from TaskManager.
        :raises: InvalidParameterValue on malformed parameter(s)
        :raises: MissingParameterValue on missing parameter(s)
        :returns: A list with the supported boot devices defined
                  in :mod:`ironic.common.boot_devices`.
        """
        self.validate(task)
        system = utils.get_system(task.node)
        supported_boot_devices = system.get_supported_boot_devices()
        return list(map(mappings.BOOT_DEVICE_MAP.get, supported_boot_devices))

    @task_manager.require_exclusive_lock
    def set_boot_device(self, task, device, persistent=False):
        """Set the boot device for a node.

        :param task: A task from TaskManager.
        :param device: The boot device, one of
                       :mod:`ironic.common.boot_device`.
        :param persistent: Boolean value. True if the boot device will
                           persist to all future boots, False if not.
                           Default: False.
        :raises: InvalidParameterValue on malformed parameter(s)
        :raises: MissingParameterValue on missing parameter(s)
        :raises: IBMCConnectionError when it fails to connect to iBMC
        :raises: IBMCError on an error from the iBMC
        """
        self.validate(task)
        system = utils.get_system(task.node)

        try:
            system.set_system_boot_source(
                mappings.BOOT_DEVICE_MAP_REV[device],
                enabled=mappings.BOOT_DEVICE_PERSISTENT_MAP_REV[persistent])
        except requests.exceptions.RequestException as e:
            error_msg = (_('IBMC set boot device failed for node '
                           '%(node)s. Error: %(error)s') %
                         {'node': task.node.uuid, 'error': e})
            LOG.error(error_msg)
            raise exception.IBMCError(error=error_msg)

    def get_boot_device(self, task):
        """Get the current boot device for a node.

        :param task: A task from TaskManager.
        :raises: InvalidParameterValue on malformed parameter(s)
        :raises: MissingParameterValue on missing parameter(s)
        :raises: IBMCConnectionError when it fails to connect to iBMC
        :raises: IBMCError on an error from the iBMC
        :returns: a dictionary containing:

            :boot_device:
                the boot device, one of :mod:`ironic.common.boot_devices` or
                None if it is unknown.
            :persistent:
                Boolean value or None, True if the boot device persists,
                False otherwise. None if it's disabled.

        """
        self.validate(task)
        system = utils.get_system(task.node)
        boot = system.boot
        target = boot.get('target')
        enabled = boot.get('enabled')

        return {
            'boot_device': mappings.BOOT_DEVICE_MAP.get(target),
            'persistent':
                mappings.BOOT_DEVICE_PERSISTENT_MAP.get(enabled)
        }

    def get_supported_boot_modes(self, task):
        """Get a list of the supported boot modes.

        :param task: A task from TaskManager.
        :returns: A list with the supported boot modes defined
                  in :mode:`ironic.common.boot_modes`. If boot
                  mode support can't be determined, empty list
                  is returned.
        """
        return list(mappings.BOOT_MODE_MAP_REV)

    @task_manager.require_exclusive_lock
    def set_boot_mode(self, task, mode):
        """Set the boot mode for a node.

        Set the boot mode to use on next reboot of the node.

        :param task: A task from TaskManager.
        :param mode: The boot mode, one of
                     :mod:`ironic.common.boot_modes`.
        :raises: InvalidParameterValue on malformed parameter(s)
        :raises: MissingParameterValue on missing parameter(s)
        :raises: IBMCConnectionError when it fails to connect to iBMC
        :raises: IBMCError on an error from the iBMC
        """
        self.validate(task)
        system = utils.get_system(task.node)

        boot_device = system.boot.get('target')
        if not boot_device:
            error_msg = (_('Cannot change boot mode on node %(node)s '
                           'because its boot device is not set.') %
                         {'node': task.node.uuid})
            LOG.error(error_msg)
            raise exception.IBMCError(error_msg)

        boot_override = system.boot.get('enabled')
        if not boot_override:
            error_msg = (_('Cannot change boot mode on node %(node)s '
                           'because its boot source override is not set.') %
                         {'node': task.node.uuid})
            LOG.error(error_msg)
            raise exception.IBMCError(error_msg)

        try:
            system.set_system_boot_source(
                boot_device,
                enabled=boot_override,
                mode=mappings.BOOT_MODE_MAP_REV[mode])
        except requests.exceptions.RequestException as e:
            error_msg = (_('Setting boot mode to %(mode)s '
                           'failed for node %(node)s. Error : %(error)s') %
                         {'node': task.node.uuid, 'mode': mode, 'error': e})
            LOG.error(error_msg)
            raise exception.IBMCError(error=error_msg)

    def get_boot_mode(self, task):
        """Get the current boot mode for a node.

        Provides the current boot mode of the node.

        :param task: A task from TaskManager.
        :raises: InvalidParameterValue on malformed parameter(s)
        :raises: MissingParameterValue on missing parameter(s)
        :raises: IBMCConnectionError when it fails to connect to iBMC
        :returns: The boot mode, one of :mod:`ironic.common.boot_mode` or
                  None if it is unknown.
        """
        self.validate(task)
        system = utils.get_system(task.node)
        return mappings.BOOT_MODE_MAP.get(system.boot.get('mode'))

    def get_sensors_data(self, task):
        """Get sensors data.

        Not implemented for this driver.

        :raises: NotImplementedError
        """
        raise NotImplementedError()

    @task_manager.require_exclusive_lock
    def inject_nmi(self, task):
        """Inject NMI, Non Maskable Interrupt.

        Inject NMI (Non Maskable Interrupt) for a node immediately.

        :param task: A TaskManager instance containing the node to act on.
        :raises: InvalidParameterValue on malformed parameter(s)
        :raises: MissingParameterValue on missing parameter(s)
        :raises: IBMCConnectionError when it fails to connect to iBMC
        :raises: IBMCError on an error from the Sushy library
        """
        self.validate(task)
        system = utils.get_system(task.node)
        try:
            system.reset_system(constants.RESET_NMI)
        except requests.exceptions.RequestException as e:
            error_msg = (_('IBMC inject NMI failed for node %(node)s. '
                           'Error: %(error)s') %
                         {'node': task.node.uuid, 'error': e})
            LOG.error(error_msg)
            raise exception.IBMCError(error=error_msg)
