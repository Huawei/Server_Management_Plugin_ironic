# Server_Management_Plugin_ironic

## I. Plug-in Introduction

The Ironic plug-in is a plug-in integrated in the OpenStack software. It is used to manage Huawei servers. By adding Huawei servers, 
you can implement the OS deployment on servers by using this plug-in.

- Plug-in name: `ironic_driver_for_iBMC`
- Supported version: `OpenStack Rocky`
- Supported device: Huawei rack server `2288H V5`, `CH121 V5 `

## II. Plug-in Functions

- OS deployment
- Boot sequence query

## III. Install/Uninstall iBMC driver 
 
This guide is based on Ubuntu 18.04.
 
### 1. Installing Plug-in

- Connect to the OpenStack Rocky environment.

- download and install  [driver](https://github.com/Huawei/Server_Management_Plugin_ironic)
```bash
$ mkdir ~/ironic-ibmc-driver
$ cd ~/ironic-ibmc-driver
$ curl -O https://raw.githubusercontent.com/huawei/Server_Management_Plugin_ironic/master/release/ironic_driver_for_iBMC.tar.gz
$ tar zxvf ironic_driver_for_iBMC.tar.gz
$ cd ironic_driver_for_iBMC
$ sudo ./install.sh
```   

- Export fake OpenStack authentication info

```bash
$ export OS_URL=http://127.0.0.1:6385
$ export OS_TOKEN=fake
```

- Restart Ironic conductor service

Restart ironic conductor to load ibmc hardware type, then list enabled driver list to validate whether `ibmc` driver is installed successfully. 

```bash
$ sudo systemctl restart ironic-conductor
$ openstack baremetal driver list

+---------------------+----------------+
| Supported driver(s) | Active host(s) |
+---------------------+----------------+
| ibmc                | 192.168.0.10   |
+---------------------+----------------+
```


### 2. Uninstalling driver


``` bash
$ cd ~/ironic-ibmc-driver
$ sudo ./install.sh uninstall	
```


## IV. Deploy Nodes using ibmc driver 

The process below shows how to deploy an ibmc server using `pxe`, we are assuming that you are using a **[standalone Ironic](https://docs.openstack.org/project-install-guide/baremetal/newton/standalone.html)** environment. If your ironic environment is different, you can directly check the creating node segment, that is the only difference between `ibmc` driver than other drivers.


1. Setup baremetal Boot mode

Restart the bare metal server, press F11 to enter the Boot menu of the BIOS, and change the value of Boot Type to `Legacy Boot`.


2. Insure required services is running

```bash
$ systemctl status iscsid
$ systemctl status ironic-api
$ systemctl status ironic-conductor
$ systemctl status nginx
$ systemctl status dnsmasq
```

if services is not runing, use `systemctl start xxx` to run the service.

3. Enrolling node with ibmc driver

Set node's `driver` property to `ibmc` to using the driver.
The following properties specified in the node's `driver_info` property are required:
- `ibmc_address`: https endpoint of ibmc server
- `ibmc_username`: username of ibmc account 
- `ibmc_password`: password of ibmc account 
- `ibmc_verify_ca`: if ibmc_address has the https scheme, the
driver will use a secure (TLS) connection when talking to the iBMC. By default (if this is not set or set to True), the driver will try to verify the host certificates. This can be set to the path of a certificate file or directory with trusted certificates that the driver will use for verification. To disable verifying TLS, set this to False. This is optional.

```bash
$ baremetal_name="your-bare-metal-name"
$ baremetal_deploy_kernel="file:///var/lib/ironic/http/deploy/coreos_production_pxe.vmlinuz"
$ baremetal_deploy_ramdisk="file:///var/lib/ironic/http/deploy/coreos_production_pxe_image-oem.cpio.gz"
$ baremetal_ibmc_addr="https://your-ibmc-server-host"
$ baremetal_ibmc_user="your-ibmc-server-user-account"
$ baremetal_ibmc_pass="your-ibmc-server-user-password"
$  NODE=$(openstack baremetal node create --name "$baremetal_name" \
    --boot-interface "pxe" --deploy-interface "iscsi" \
    --driver "ibmc" \
    --driver-info ibmc_address="$baremetal_ibmc_addr" \
    --driver-info ibmc_username="$baremetal_ibmc_user" \
    --driver-info ibmc_password="$baremetal_ibmc_pass" \
    --driver-info ibmc_verify_ca="False" \
    --driver-info deploy_kernel="$baremetal_deploy_kernel" \
    --driver-info deploy_ramdisk="$baremetal_deploy_ramdisk" \
    -f value -c uuid)
```

4. Creating a Port

Create port for bare metal server node. You can get MAC by: 

Log in to the iBMC WebUI, choose System Info > Network, and view the NIC MAC address information.

```bash
$ baremetal_mac="****" # MAC address of the NIC corresponding to the bare metal server
$ openstack baremetal port create --node $NODE "$baremetal_mac"
```

For Example:

```
$ openstack baremetal port create --node $NODE "58:F9:87:7A:A9:73"
$ openstack baremetal port create --node $NODE "58:F9:87:7A:A9:74"
$ openstack baremetal port create --node $NODE "58:F9:87:7A:A9:75"
$ openstack baremetal port create --node $NODE "58:F9:87:7A:A9:76"
```


5. Configuring the OS Image to be deployed 

```
$ baremetal_image="http://192.168.0.100/images/ubuntu-xenial-16.04.qcow2"
# You can run md5sum /var/lib/ironic/http/images/ubuntu-xenial-16.04.qcow2 to calculate the value.
$ baremetal_image_checksum="f3e563d5d77ed924a1130e01b87bf3ec" 

$ openstack baremetal node set "$NODE" \
  --instance-info image_source="$baremetal_image" \
  --instance-info image_checksum="$baremetal_image_checksum" \
  --instance-info root_gb="10"
```

6. Inspect the created node

Run `node show` to confirm the configurations is all right:

```bash
$ openstack baremetal node show $NODE -f json
```

7. Deploying Node

```
openstack baremetal node manage "$NODE" &&
openstack baremetal node provide "$NODE" &&
openstack baremetal node deploy $NODE 
```


## V. Customer calls provided by ibmc driver 

- Querying vendor specific pass through method:
```
$ openstack baremetal node passthru list $NODE
```

- Querying the boot sequence:

```
$ openstack baremetal node passthru call --http-method GET $NODE boot_up_seq
```

