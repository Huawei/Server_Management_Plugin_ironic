# TODO(bill.chan) license

from oslo_config import cfg

from ironic.common.i18n import _

opts = [
    cfg.IntOpt('connection_attempts',
               min=1,
               default=5,
               help=_('Maximum number of attempts to try to connect '
                      'to iBMC')),
    cfg.IntOpt('connection_retry_interval',
               min=1,
               default=4,
               help=_('Number of seconds to wait between attempts to '
                      'connect to iBMC'))
]


def register_opts(conf):
    conf.register_opts(opts, group='ibmc')
