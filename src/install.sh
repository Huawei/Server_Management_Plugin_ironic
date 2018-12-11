#!/bin/bash
set -e

# Usage
function usage {
    echo "Usage: `basename $0` [uninstall]"
	cat <<EOF
	USAGE
		`basename $0` [uninstall]

	DESCRIPTION
		Patch script for ironic ibmc driver.
		
		Patch when no argument supply.
		Uninstall patch when first argument is uninstall
EOF
	exit 1
}

# Whether this operation is patch or uninstall the patch.
# 2: Print usage
# 1: Uninstall the patch
# 0: Patch
IS_PATCH=2

# First argument is operation 
OP="${1}"

if [ -z "$OP" ]
then
	IS_PATCH=0
elif [ "$OP" == "uninstall" ]
then
	IS_PATCH=1
else
	usage
fi

IRONIC_INSTALLED="`pip show ironic --disable-pip-version-check | grep '^Name'`"

# Python dist-packages dir
PY_DIST_DIR="`pip show ironic --disable-pip-version-check | grep '^Location' | cut -d' ' -f2`"
IRONIC_VERSION="`pip show ironic --disable-pip-version-check | grep '^Version' | cut -d' ' -f2`"

# Check required parameters
: ${IRONIC_INSTALLED:?"Ironic not install! Do not patch!"}
: ${PY_DIST_DIR:?"Python dist-packages dir not found! Patch failed!"}
: ${IRONIC_VERSION:?"Can not determine Iroinc version! Patch failed!"}

# Ironic install dir
IRONIC_DIR="$PY_DIST_DIR/ironic"
# Ironic egg info dir
IRONIC_EGG_DIR="$PY_DIST_DIR/ironic-$IRONIC_VERSION.egg-info"

# Create temporary dir, all original file copy in this dir, before modification.
# These files IS for reference only, the script will not recover from these copy
# directly...
TMP_DIR="$PWD/tmp"
mkdir -p $TMP_DIR

# Files and copys path
BAK_SUFFIX=".$(date +%Y%m%d-%H%M%S)"
PATH_CONF_INIT="$IRONIC_DIR/conf/__init__.py"
PATH_CONF_INIT_BAK="$TMP_DIR/__init__.py$BAK_SUFFIX"
PATH_COMMON_EXCEPTION="$IRONIC_DIR/common/exception.py"
PATH_COMMON_EXCEPTION_BAK="$TMP_DIR/exception.py$BAK_SUFFIX"
PATH_ENTRY_POINTS="$IRONIC_EGG_DIR/entry_points.txt"
PATH_ENTRY_POINTS_BAK="$TMP_DIR/entry_points.txt$BAK_SUFFIX"
PATH_IRONIC_CONF="/etc/ironic/ironic.conf"
PATH_IRONIC_CONF_BAK="$TMP_DIR/ironic.conf${BAK_SUFFIX}"
# Patch file
PATCH_FILE="$PWD/ironic_driver_for_iBMC.tar"
# Patch code...
CODE_CONF_INIT='from ironic.conf import ibmc\nibmc.register_opts(CONF)\n\n'
CODE_COMMON_EXCEPTION='class IBMCError(IronicException):\n    _msg_fmt = _("IBMC exception occurred. Error: %(error)s")\n\n\nclass IBMCConnectionError(IBMCError):\n    _msg_fmt = _("IBMC connection failed for node %(node)s: %(error)s")\n\n'
# Patch entry points ...
INTERFACE_MGMT='ironic.hardware.interfaces.management'
INTERFACE_POWER='ironic.hardware.interfaces.power'
INTERFACE_VENDOR='ironic.hardware.interfaces.vendor'
HARDWARE_TYPES='ironic.hardware.types'
IBMC_MGMT='ibmc = ironic.drivers.modules.ibmc.management:IBMCManagement'
IBMC_POWER='ibmc = ironic.drivers.modules.ibmc.power:IBMCPower'
IBMC_VENDOR='ibmc = ironic.drivers.modules.ibmc.vendor:IBMCVendor'
IBMC_HW='ibmc = ironic.drivers.ibmc:IBMCHardware'
# Patch config ...
IRONIC_CFG_HW="enabled_hardware_types"
IRONIC_CFG_MGMT="enabled_management_interfaces"
IRONIC_CFG_POWER="enabled_power_interfaces"
IRONIC_CFG_VENDOR="enabled_vendor_interfaces"

# Check environment correctness
function check_envir {
    # Check files, which need modification, whether in consistent state
    # Code ...
    local EX_CONF_INIT=$(grep -E "^from ironic.conf import ibmc" $PATH_CONF_INIT || :)
    local EX_COMMON_EXCEPTION=$(grep -E "^class IBMCError" $PATH_COMMON_EXCEPTION || :)
    # Entry points ...
    local EX_EP_IBMC_HW=$(grep -E "^$IBMC_HW" $PATH_ENTRY_POINTS || :)
    local EX_EP_IBMC_MGMT=$(grep -E "^$IBMC_MGMT" $PATH_ENTRY_POINTS || :)
    local EX_EP_IBMC_POWER=$(grep -E "^$IBMC_POWER" $PATH_ENTRY_POINTS || :)
    local EX_EP_IBMC_VENDOR=$(grep -E "^$IBMC_VENDOR" $PATH_ENTRY_POINTS || :)
    # Config ...
    local EX_CFG_IBMC_HW=$(grep -E "^$IRONIC_CFG_HW=.*ibmc.*" $PATH_IRONIC_CONF || :)
    local EX_CFG_IBMC_MGMT=$(grep -E "^$IRONIC_CFG_MGMT=.*ibmc.*" $PATH_IRONIC_CONF || :)
    local EX_CFG_IBMC_POWER=$(grep -E "^$IRONIC_CFG_POWER=.*ibmc.*" $PATH_IRONIC_CONF || :)
    local EX_CFG_IBMC_VENDOR=$(grep -E "^$IRONIC_CFG_VENDOR=.*ibmc.*" $PATH_IRONIC_CONF || :)

    # Files that are not in consistent state
    local EX_FILES
    if [ ! -z "$EX_CONF_INIT" ]
    then
        EX_FILES[${#EX_FILES[@]}]='\n'
        EX_FILES[${#EX_FILES[@]}]=$PATH_CONF_INIT
    fi
    if [ ! -z "$EX_COMMON_EXCEPTION" ]
    then
        EX_FILES[${#EX_FILES[@]}]='\n'
        EX_FILES[${#EX_FILES[@]}]=$PATH_COMMON_EXCEPTION
    fi
    if [ ! -z "$EX_EP_IBMC_HW" -o ! -z "$EX_EP_IBMC_POWER" -o \
         ! -z "$EX_EP_IBMC_VENDOR" -o ! -z "$EX_EP_IBMC_MGMT" ]
    then
        EX_FILES[${#EX_FILES[@]}]='\n'
        EX_FILES[${#EX_FILES[@]}]=$PATH_ENTRY_POINTS
    fi
    if [ ! -z "$EX_CFG_IBMC_HW" -o ! -z "$EX_CFG_IBMC_MGMT" -o \
         ! -z "$EX_CFG_IBMC_POWER" -o ! -z "$EX_CFG_IBMC_VENDOR" ]
    then
        EX_FILES[${#EX_FILES[@]}]='\n'
        EX_FILES[${#EX_FILES[@]}]=$PATH_IRONIC_CONF
    fi

    if [ ! "${#EX_FILES[@]}" -gt "0" ]
    then
        return 0
    else
        echo -e "Patch failed!

Following files may have iBMC related configuration or codes. 
You could uninstall this script to erase iBMC related configuration or codes,
or check aginst these files then update manually.
        ${EX_FILES[@]}
        "
        exit 1
    fi
}

# Replace or append ibmc related config
function config {
    local OPTION_STR="$1"

    ENABLED_STR=$(grep -E "^$OPTION_STR=" $PATH_IRONIC_CONF || :)
    IBMC_TYPE="ibmc"
    ENABLED=$(echo $ENABLED_STR | grep -E "ibmc" || :)
    if [ ! -z "$ENABLED" ]
    then
        return # Already enabled ibmc related config
    fi

    if [ ! -z "$ENABLED_STR" ]
    then
        sed -i -r -e "s/$ENABLED_STR/${ENABLED_STR},${IBMC_TYPE}/" $PATH_IRONIC_CONF
    else
        # option not exist
        echo "$OPTION_STR=$IBMC_TYPE" >> $PATH_IRONIC_CONF
    fi
}

function make_copy {
    # Make copy, for reference only...
    cp $PATH_CONF_INIT $PATH_CONF_INIT_BAK
    cp $PATH_COMMON_EXCEPTION $PATH_COMMON_EXCEPTION_BAK
    cp $PATH_IRONIC_CONF $PATH_IRONIC_CONF_BAK
    cp $PATH_ENTRY_POINTS $PATH_ENTRY_POINTS_BAK
}

# Patch function 
function patch {
    # Check environment first, ensure the environment is iBMC not related
    check_envir

    make_copy

    # Extract added patch files to Python dist-packages
    tar -xf $PATCH_FILE -C $PY_DIST_DIR

    # Add iBMC related conf
    printf "\n%b" "$CODE_CONF_INIT" >> $PATH_CONF_INIT

    # Add iBMC related exceptions
    printf "\n%b" "$CODE_COMMON_EXCEPTION" >> $PATH_COMMON_EXCEPTION

    # Modify ironic egg info entry_points.txt
    sed -i -r -e "s/(\[$INTERFACE_MGMT\])/\1\n$IBMC_MGMT/" $PATH_ENTRY_POINTS
    sed -i -r -e "s/(\[$INTERFACE_POWER\])/\1\n$IBMC_POWER/" $PATH_ENTRY_POINTS
    sed -i -r -e "s/(\[$INTERFACE_VENDOR\])/\1\n$IBMC_VENDOR/" $PATH_ENTRY_POINTS
    sed -i -r -e "s/(\[$HARDWARE_TYPES\])/\1\n$IBMC_HW/" $PATH_ENTRY_POINTS

    # Enabled ibmc related config
    config "enabled_hardware_types"
    config "enabled_management_interfaces"
    config "enabled_power_interfaces"
    config "enabled_vendor_interfaces"

    echo "Patch done!"
}

# Undo patch function
function undo_patch {
    make_copy

    # Remove iBMC related configuration and codes...
    # Code ...
    local TMP=${CODE_CONF_INIT//\(/\\(}
    TMP=${TMP//\)/\\)}
    perl -0777 -i -pe "s/$TMP//g" $PATH_CONF_INIT

    TMP=${CODE_COMMON_EXCEPTION//\(/\\(}
    TMP=${TMP//\)/\\)}
    perl -0777 -i -pe "s/$TMP//g" $PATH_COMMON_EXCEPTION
    # Entry points ...
    sed -i -r -e "s/^$IBMC_HW//" $PATH_ENTRY_POINTS
    sed -i -r -e "s/^$IBMC_MGMT//" $PATH_ENTRY_POINTS
    sed -i -r -e "s/^$IBMC_POWER//" $PATH_ENTRY_POINTS
    sed -i -r -e "s/^$IBMC_VENDOR//" $PATH_ENTRY_POINTS
    # Config ...
    # Ironic don't allow some option value be empty list (empty string).
    # In case option value become empty list after uninstall, 
    #+ we leave comma there intentionally
    sed -i -r -e "s/^($IRONIC_CFG_HW=.*)(ibmc)(.*)/\1\3/" $PATH_IRONIC_CONF
    sed -i -r -e "s/^($IRONIC_CFG_MGMT=.*)(ibmc)(.*)/\1\3/" $PATH_IRONIC_CONF
    sed -i -r -e "s/^($IRONIC_CFG_POWER=.*)(ibmc)(.*)/\1\3/" $PATH_IRONIC_CONF
    sed -i -r -e "s/^($IRONIC_CFG_VENDOR=.*)(ibmc)(.*)/\1\3/" $PATH_IRONIC_CONF

    echo "Uninstall patch done!"
}

if [ "$IS_PATCH" -eq "0" ]
then
    patch
elif [ "$IS_PATCH" -eq "1" ]
then
    undo_patch
else
    usage
fi
