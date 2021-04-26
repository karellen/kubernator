# -*- coding: utf-8 -*-
#
# Copyright 2021 © Payperless
#


def _main():
    from kubernator import app
    return app.main()


def main():
    from gevent.monkey import patch_all
    patch_all()

    import sys
    sys.exit(_main())


if __name__ == "__main__":
    main()
