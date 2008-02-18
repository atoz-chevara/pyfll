#!/usr/bin/python -tt

__author__    = 'Kel Modderman'
__copyright__ = '(C) 2008 Kel Modderman <kel@otaku42.de>'
__license__   = 'GPLv2 or any later version'

from configobj import ConfigObj
from optparse import OptionParser
from subprocess import Popen, PIPE

import atexit
import os
import sys
import shutil
import tempfile


def lines2list(lines):
    """Return a list of stripped strings given a group of line
    separated strings"""
    return [s.strip() for s in lines.splitlines() if s]


class Error(Exception):
    """Base class for exceptions in this module."""
    pass


class FLLError(Error):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)


class FLLBuilder:
    conf = None
    opts = None
    pkgs = {}
    temp = None


    def processOpts(self):
        """Process options."""
        if self.opts.v:
            print('Processing options...')

        if self.opts.c:
            if os.path.isfile(self.opts.c):
                self.opts.c = os.path.abspath(self.opts.c)
            else:
                raise FLLError("configuration file does not exist: %s" %
                               self.opts.c)
        else:
            raise FLLError("no configuration files specified on command line")

        if not os.path.isdir(self.opts.b):
            if self.opts.v:
                print(" * creating build dir: %s" % self.opts.b)
            try:
                os.makedirs(self.opts.b)
            except:
                raise FLLError("failed to create build dir %s - %s" %
                               (self.opts.b, sys.exc_info()[0]))

        self.opts.b = os.path.abspath(self.opts.b)

        if not os.path.isdir(self.opts.o):
            if self.opts.v:
                print(" * creating output dir: %s" % self.opts.o)
            try:
                os.makedirs(self.opts.o)
            except:
                raise FLLError("failed to create output dir %s - %s" %
                               (self.opts.o, sys.exc_info()[0]))

        self.opts.o = os.path.abspath(self.opts.o)


    def parseOpts(self):
        """Parse command line arguments."""
        p = OptionParser(usage = 'fll -c <config file> [-b <directory> ' +
                         '-o <directory> -s <directory>] [-dpqv]')

        p.add_option('-b', '--build', dest = 'b', action = 'store',
                     type = 'string', metavar = '<directory>',
                     help = 'Build directory. A large amount of free space ' +
                     'is required.')

        p.add_option('-c', '--config', dest = 'c', action = 'store',
                     type = 'string', metavar = '<config file>',
                     help = 'Configuration file. This option may be used ' +
                     'more than once to process multiple configurations. ' +
                     'A configuration file must be specified.')

        p.add_option('-d', '--debug', dest = 'd', action = 'store_true',
                     help = 'Enable debug mode. Extra output will be ' +
                     'to assist in development. Default: %default')

        p.add_option('-g', '--gid', dest = 'g', action = 'store',
                     type = 'int', metavar = '<group id>',
                     help = 'Group ID of user doing the build. This ' +
                     'should not normally be required, the wrapper script ' +
                     'will take care of this for you.')

        p.add_option('-o', '--output', dest = 'o', action = 'store',
                     type = 'string', metavar = '<directory>',
                     help = 'Output directory, where the product of this ' +
                     'program will be generated.')

        p.add_option('-p', '--preserve', dest = 'p', action = 'store_true',
                     help = 'Preserve build directory. Disable automatic ' +
                     'cleanup of the build area at exit.')

        p.add_option('-n', '--non-root', dest = 'n', action = 'store_true',
                     help = 'Start as noon root user (for debugging).')

        p.add_option('-q', '--quiet', dest = 'v', action = 'store_false',
                     help = 'Enable quiet mode. Only high priority messages ' +
                     'will be generated, such as announcing current')

        p.add_option('-s', '--share', dest = 's', action = 'store',
                     type = 'string', metavar = '<directory>',
                     help = 'Share directory directory containing data ' +
                     'required for the program to function.')

        p.add_option('-u', '--uid', dest = 'u', action = 'store',
                     type = 'int', metavar = '<user id>',
                     help = 'User ID of user doing the build. This ' +
                     'should not normally be required, the wrapper script ' +
                     'will take care of this for you.')

        p.add_option('-v', '--verbose', dest = 'v', action = 'store_true',
                     help = 'Enable verbose mode. All messages will be ' +
                     'generated, such as announcing current operation.')

        p.set_defaults(d = False, b = os.getcwd(), g = os.getgid(), n = False,
                       o = os.getcwd(), p = False, s = '/usr/share/fll/',
                       u = os.getuid(), v = True)

        self.opts = p.parse_args()[0]
        self.processOpts()


    def processConf(self):
        """Process configuration options."""
        if self.opts.v:
            print('Processing configuration options...')

        if len(self.conf['archs'].keys()) < 1:
            host_arch = Popen(["dpkg", "--print-architecture"],
                              stdout=PIPE).communicate()[0].rstrip()
            self.conf['archs'][host_arch] = {}

        for arch in self.conf['archs'].keys():
            if 'linux' not in self.conf['archs'][arch]:
                if arch == 'i386':
                    if os.path.isfile('/etc/sidux-version'):
                        self.conf['archs'][arch]['linux'] = '2.6-sidux-686'
                    else:
                        self.conf['archs'][arch]['linux'] = '2.6-686'
                else:
                    if os.path.isfile('/etc/sidux-version'):
                        self.conf['archs'][arch]['linux'] = '2.6-sidux-' + arch
                    else:
                        self.conf['archs'][arch]['linux'] = '2.6-' + arch

        if len(self.conf['repos'].keys()) < 1:
            raise FLLError("no apt repos were specified in build config")

        for repo in self.conf['repos'].keys():
            for word in ['label', 'uri', 'suite', 'components']:
                if word not in self.conf['repos'][repo]:
                    raise FLLError("no '%s' for apt repo '%s'" % (word, repo))

        if 'profile' not in self.conf['packages']:
            self.conf['packages']['profile'] = 'kde-lite'



    def parseConf(self):
        """Parse build configuration file and return it in a dict."""
        if self.opts.v:
            print("Parsing configuration file...")
            print(" * configuration file: %s" % self.opts.c)

        self.conf = ConfigObj(self.opts.c, interpolation = 'Template')
        self.processConf()

        if self.opts.d:
            print("conf:", self.conf)


    def _processPkgProfile(self, archs, profile, dir):
        """Return a dict, arch string as keys and package list as values."""
        list = {}
        for arch in archs:
            list[arch] = {'debconf': [], 'list': []}

        if self.opts.v:
            print(" * processing profile: %s" % os.path.basename(profile))

        pfile = ConfigObj(profile)

        if 'desc' in pfile and self.opts.v:
            for line in lines2list(pfile['desc']):
                print "     %s" % line

        if 'repos' in pfile:
            for repo in lines2list(pfile['repos']):
                if repo not in self.conf['repos']:
                    raise FLLError("'%s' repo is required " % repo +
                                   "by package module '%s'" %
                                   os.path.basename(profile))

        if 'debconf' in pfile:
            for arch in archs:
                list[arch]['debconf'].extend(lines2list(pfile['debconf']))

        if 'extra_debconf' in self.conf['packages']:
            for arch in archs:
                list[arch]['debconf'].extend(
                    lines2list(self.conf['packages']['extra_debconf']))

        if 'packages' in pfile:
            for arch in archs:
                list[arch]['list'].extend(lines2list(pfile['packages']))

        if 'extra_packages' in self.conf['packages']:
            for arch in archs:
                list[arch]['list'].extend(
                    lines2list(self.conf['packages']['extra_packages']))

        for arch in archs:
            if arch in pfile:
                list[arch]['list'].extend(lines2list(pfile[arch]))

        deps = []
        if 'deps' in pfile:
            deps.extend(lines2list(pfile['deps']))

        if 'extra_deps' in self.conf['packages']:
            deps.extend(lines2list(self.conf['packages']['extra_deps']))

        for dep in deps:
            depfile = os.path.join(dir, 'packages.d', dep)

            if not os.path.isfile(depfile):
                raise FLLError("no such dep file: %s" % depfile)

            if self.opts.v:
                print(" * processing depfile: %s" %
                      os.path.basename(depfile))

            dfile = ConfigObj(depfile)

            if 'desc' in dfile and self.opts.v:
                for line in lines2list(dfile['desc']):
                    print "     %s" % line

            if 'repos' in dfile:
                for repo in lines2list(dfile['repos']):
                    if repo not in self.conf['repos']:
                        raise FLLError("'%s' repo is required " % repo +
                                       "by package module '%s'" %
                                       os.path.basename(depfile))

            if 'debconf' in dfile:
                for arch in archs:
                    list[arch]['debconf'].extend(lines2list(dfile['debconf']))

            if 'packages' in dfile:
                for arch in archs:
                    list[arch]['list'].extend(lines2list(dfile['packages']))

            for arch in archs:
                if arch in dfile:
                    list[arch]['list'].extend(lines2list(dfile[arch]))

        if self.opts.d:
            for arch in archs:
                list[arch]['list'].sort()
                print(" * package list for arch: %s" % arch)
                for p in list[arch]['list']:
                    print("     %s" % p)
                print list[arch]

        return list


    def parsePkgProfile(self):
        """Parse packages profile file(s)."""
        dir = os.path.join(self.opts.s, 'packages')
        file = os.path.join(dir, self.conf['packages']['profile'])

        if not os.path.isfile(file):
            raise FLLError("no such package profile file: %s" % file)

        if self.opts.v:
            print("Processing package profile...")

        self.pkgs = self._processPkgProfile(self.conf['archs'].keys(),
                                            file, dir)


    def stageBuildArea(self):
        """Prepare temporary directory to prepare chroots and stage result."""
        if self.opts.v:
            print('Staging build area...')

        self.temp = tempfile.mkdtemp(prefix = 'fll_', dir = self.opts.b)
        if not self.opts.p:
            atexit.register(self.cleanup)

        for arch in self.conf['archs'].keys():
            os.mkdir(os.path.join(self.temp, arch))
            if self.opts.v:
                print(" * creating directory: %s" %
                      os.path.join(self.temp, arch))

        os.mkdir(os.path.join(self.temp, 'staging'))
        if self.opts.v:
            print(" * creating directory: %s" %
                  os.path.join(self.temp, 'staging'))


    def _umount(self, chrootdir):
        """Umount any mount points in a given chroot directory."""
        umount_list = []
        for line in open("/proc/mounts"):
            (dev, mnt, fs, options, d, p) = line.split()
            if mnt.startswith(chrootdir):
                umount_list.append(mnt)

        umount_list.sort(key=len)
        umount_list.reverse()

        for mpoint in umount_list:
            if self.opts.v:
                print(" * umount %s" % mpoint)
            retv = call(["umount", mpoint])
            if retv != 0:
                raise FLLError("umount failed for: %s" % mpoint)


    def _nuke(self, dir):
        """Nuke directory tree."""
        if self.opts.v:
            print(" * nuking directory: %s" % dir)
        try:
            shutil.rmtree(dir)
        except:
            raise FLLError("unable to remove %s - %s" %
                           (dir, sys.exc_info()[0]))


    def cleanup(self):
        """Clean up the build area."""
        for arch in self.conf['archs'].keys():
            if self.opts.v:
                print("Cleaning up %s chroot..." % arch)
            self._umount(os.path.join(self.temp, arch))
            self._nuke(os.path.join(self.temp, arch))

        if self.opts.v:
            print('Cleaning up temp dir...')
        self._nuke(self.temp)


if __name__ == "__main__":
    try:
        fll = FLLBuilder()

        fll.parseOpts()
        fll.parseConf()

        fll.parsePkgProfile()

        fll.stageBuildArea()
    except FLLError, e:
        print >> sys.stderr, 'E:', e
