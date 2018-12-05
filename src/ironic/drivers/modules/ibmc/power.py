# TODO(bill.chan) license
from oslo_log import log
import requests

from ironic.common import exception
from ironic.common.i18n import _
from ironic.common import states
from ironic.conductor import task_manager
from ironic.conductor import utils as cond_utils
from ironic.drivers import base
from ironic.drivers.modules.ibmc import mappings
from ironic.drivers.modules.ibmc import utils

LOG = log.getLogger(__name__)

TARGET_STATE_MAP = {
    states.REBOOT: states.POWER_ON,
    states.SOFT_REBOOT: states.POWER_ON,
    states.SOFT_POWER_OFF: states.POWER_OFF,
}


class IBMCPower(base.PowerInterface):

    def __init__(self):
        """Initialize the iBMC power interface."""
        super(IBMCPower, self).__init__()

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

    def get_power_state(self, task):
        """Get the current power state of the task's node.

        :param task: A TaskManager instance containing the node to act on.
        :returns: A power state. One of :mod:`ironic.common.states`.
        :raises: InvalidParameterValue on malformed parameter(s)
        :raises: MissingParameterValue on missing parameter(s)
        :raises: IBMCConnectionError when it fails to connect to iBMC
        :raises: IBMCError on an error from the iBMC
        """
        self.validate(task)
        system = utils.get_system(task.node)
        return mappings.GET_POWER_STATE_MAP.get(system.power_state)

    @task_manager.require_exclusive_lock
    def set_power_state(self, task, power_state, timeout=None):
        """Set the power state of the task's node.

        :param task: A TaskManager instance containing the node to act on.
        :param power_state: Any power state from :mod:`ironic.common.states`.
        :param timeout: Time to wait for the node to reach the requested state.
        :raises: InvalidParameterValue on malformed parameter(s)
        :raises: MissingParameterValue if a required parameter is missing.
        :raises: IBMCConnectionError when it fails to connect to iBMC
        :raises: IBMCError on an error from the iBMC
        """
        self.validate(task)
        system = utils.get_system(task.node)
        try:
            system.reset_system(
                mappings.SET_POWER_STATE_MAP_REV.get(power_state))
        except requests.exceptions.RequestException as e:
            error_msg = (_('IBMC set power state failed for node '
                           '%(node)s. Error: %(error)s') %
                         {'node': task.node.uuid, 'error': e})
            LOG.error(error_msg)
            raise exception.IBMCError(error=error_msg)

        target_state = TARGET_STATE_MAP.get(power_state, power_state)
        cond_utils.node_wait_for_power_state(task, target_state,
                                             timeout=timeout)

    @task_manager.require_exclusive_lock
    def reboot(self, task, timeout=None):
        """Perform a hard reboot of the task's node.

        :param task: A TaskManager instance containing the node to act on.
        :param timeout: Time to wait for the node to become powered on.
        :raises: InvalidParameterValue on malformed parameter(s)
        :raises: MissingParameterValue if a required parameter is missing.
        :raises: IBMCConnectionError when it fails to connect to iBMC
        :raises: IBMCError on an error from the iBMC
        """
        self.validate(task)
        system = utils.get_system(task.node)
        current_power_state = (
            mappings.GET_POWER_STATE_MAP.get(system.power_state)
        )

        try:
            if current_power_state == states.POWER_ON:
                system.reset_system(
                    mappings.SET_POWER_STATE_MAP_REV.get(states.REBOOT))
            else:
                system.reset_system(
                    mappings.SET_POWER_STATE_MAP_REV.get(states.POWER_ON))
        except requests.exceptions.RequestException as e:
            error_msg = (_('IBMC reboot failed for node %(node)s. '
                           'Error: %(error)s') % {'node': task.node.uuid,
                                                  'error': e})
            LOG.error(error_msg)
            raise exception.IBMCError(error=error_msg)

        cond_utils.node_wait_for_power_state(task, states.POWER_ON,
                                             timeout=timeout)

    def get_supported_power_states(self, task):
        """Get a list of the supported power states.

        :param task: A TaskManager instance containing the node to act on.
            Not used by this driver at the moment.
        :returns: A list with the supported power states defined
                  in :mod:`ironic.common.states`.
        """
        return list(mappings.SET_POWER_STATE_MAP_REV)
