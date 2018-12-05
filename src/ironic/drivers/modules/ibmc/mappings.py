# TODO(bill.chan) license

from ironic.common import boot_devices
from ironic.common import boot_modes
from ironic.common import states
from ironic.drivers.modules.ibmc import constants
from ironic.drivers.modules.ibmc import utils

# Set power state mapping
SET_POWER_STATE_MAP = {
    constants.RESET_ON: states.POWER_ON,
    constants.RESET_FORCE_OFF: states.POWER_OFF,
    constants.RESET_FORCE_RESTART: states.REBOOT,
    constants.RESET_FORCE_POWER_CYCLE: states.SOFT_REBOOT,
    constants.RESET_GRACEFUL_SHUTDOWN: states.SOFT_POWER_OFF
}

SET_POWER_STATE_MAP_REV = utils.revert_dictionary(SET_POWER_STATE_MAP)

# Get power state mapping

GET_POWER_STATE_MAP = {
    constants.SYSTEM_POWER_STATE_ON: states.POWER_ON,
    constants.SYSTEM_POWER_STATE_OFF: states.POWER_OFF,
}

# Boot device mapping
BOOT_DEVICE_MAP = {
    constants.BOOT_SOURCE_TARGET_NONE: 'none',
    constants.BOOT_SOURCE_TARGET_PXE: boot_devices.PXE,
    constants.BOOT_SOURCE_TARGET_FLOPPY: 'floppy',
    constants.BOOT_SOURCE_TARGET_CD: boot_devices.CDROM,
    constants.BOOT_SOURCE_TARGET_HDD: boot_devices.DISK,
    constants.BOOT_SOURCE_TARGET_BIOS_SETUP: boot_devices.BIOS,
}

BOOT_DEVICE_MAP_REV = utils.revert_dictionary(BOOT_DEVICE_MAP)

# Boot mode mapping
BOOT_MODE_MAP = {
    constants.BOOT_SOURCE_MODE_BIOS: boot_modes.LEGACY_BIOS,
    constants.BOOT_SOURCE_MODE_UEFI: boot_modes.UEFI,
}

BOOT_MODE_MAP_REV = utils.revert_dictionary(BOOT_MODE_MAP)

# Boot device persistent mapping
BOOT_DEVICE_PERSISTENT_MAP = {
    constants.BOOT_SOURCE_ENABLED_ONCE: False,
    constants.BOOT_SOURCE_ENABLED_CONTINUOUS: True,
    constants.BOOT_SOURCE_ENABLED_DISABLED: None,
}

BOOT_DEVICE_PERSISTENT_MAP_REV = utils.revert_dictionary(BOOT_DEVICE_PERSISTENT_MAP)
