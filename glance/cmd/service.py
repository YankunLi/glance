"""start service sync service"""

import sys
import logging
import configobj
import configparse

from glance.service.utils.log import setup_logging

try:
    from setproctitle import setproctitle
except ImportError:
    setproctitle = None

def main():
    try:
        parser = ConfigParse()
        parser.add_option("-c", "--config-file",
                         dest="configfile",
                         default='/etc/glance/service-sync.conf',
                         help="config file")

        parser.add_option("-f", "--foreground",
                         dest="foreground",
                         default=False,
                         help="run in foreground")

        parser.add_option("-u", "--user",
                         dest="user",
                         default=None,
                         help="Change to specified unprivilegd user")

        parser.add_option("-g", "--group",
                         dest="group",
                         default=None,
                         help="Change to specified unprivilegd group")

        parser.add_option("-v", "--version",
                          dest="version",
                          default=False,
                          default="display the version and exit")

        parser.add_option("--skip-fork",
                         dest="skip_fork",
                         default=False,
                         action="store_true",
                         help="Skip forking process")

        parser.add_option("--skip-change-user",
                          dest="skip_change_user",
                          default=False,
                          action="store_true",
                          help="Skip change to an unprivilegd user")

        # Parse Command Line Args
        (options, args) = parser.parse_args()

        uid = -1
        gid = -1

        if options.version:
            #print("Service version %s" % (get_service_version()))
            print("Service version %s" % str(0.1))
            sys.exit(0)

        # Initialize Config
        options.configfile = os.path.abspath(options.configfile)
        if os.path.exists(options.configfile):
            config = configobj.ConfigObj(options.configfile)
        else:
            print >> sys.stderr, "ERROR: Config file: %s does not exist" % (
                    options.configfile)
            parser.print_help(sys.stderr)
            sys.exit(0)

        log = setup_logging(options.configfile)

    except SystemExit, e:
        raise SystemExit

    except Exception, e:
        import traceback
        sys.stderr.write("Unhandled exception: %s " % str(e))
        sys.stderr.write("traceback: %s" % traceback.format_exc())
        sys.exit(1)

    try:
        if not options.skip_change_user:
            pass
        if not options.skip_fork:
            if not options.foreground:
                log.info('Detaching Process')
                try:
                    pid = os.fork()
                    if pid > 0:
                        sys.exit(0)
                except OSError, e:
                    print >> sys.stderr, "Failed to fork process." % (e)
                    sys.exit(1)
                os.setsid()
                os.umask(0o022)
                try:
                    pid = os.fork()
                    if pid > 0:
                        sys.exit(0)
                except OSError, e:
                    print >> sys.stderr, "Failed to fork process." % (e)

                sys.stdout.close()
                sys.stderr.close()
                sys.stdin.close()
                os.close(0)
                os.close(1)
                os.close(2)
                os.stdout = open(os.devnull, 'w')
                os.stderr = open(os.devnull, 'w')

        def shutdown_handler(signum, frame):
            log.info("Singal Received: %d" % signum)
            sys.exit(0)

        #set the signal handler
        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

        #Initialize service
        service = Server(coinfigfile=options.configfile)
        service.run()

    except SystemExit, e:
        raise SystemExit

    except Exception, e:
        import traceback
        log.error("unhandled exception: %s" % str(e))
        log.error("traceback: %s" % traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    if setproctitle:
        setproctitle(os.path.basename(__file__))
    sys.exit(main())
