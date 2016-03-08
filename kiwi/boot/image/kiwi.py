# Copyright (c) 2015 SUSE Linux GmbH.  All rights reserved.
#
# This file is part of kiwi.
#
# kiwi is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# kiwi is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with kiwi.  If not, see <http://www.gnu.org/licenses/>
#
from tempfile import mkdtemp

from ...defaults import Defaults
from ...data.sync import DataSync
from ...system.prepare import SystemPrepare
from ...system.profile import Profile
from ...system.setup import SystemSetup
from ...logger import log
from ...archive.cpio import ArchiveCpio
from ...data.compress import Compress
from ...path import Path
from .base import BootImageBase


class BootImageKiwi(BootImageBase):
    """
        Implements preparation and creation of kiwi boot(initrd) images
        The kiwi initrd is a customized first boot initrd which allows
        to control the first boot an appliance. The kiwi initrd replaces
        itself after first boot by the result of dracut.
    """
    def prepare(self):
        """
            prepare new root system suitable to create an initrd from it
        """
        self.load_boot_xml_description()
        boot_image_name = self.boot_xml_state.xml_data.get_name()

        self.import_system_description_elements()

        log.info('Preparing boot image')
        system = SystemPrepare(
            xml_state=self.boot_xml_state,
            root_dir=self.boot_root_directory,
            allow_existing=True
        )
        manager = system.setup_repositories()
        system.install_bootstrap(
            manager
        )
        system.install_system(
            manager
        )

        profile = Profile(self.boot_xml_state)
        profile.add('kiwi_initrdname', boot_image_name)

        defaults = Defaults()
        defaults.to_profile(profile)

        setup = SystemSetup(
            self.boot_xml_state,
            self.get_boot_description_directory(),
            self.boot_root_directory
        )
        setup.import_shell_environment(profile)
        setup.import_description()
        setup.import_overlay_files(
            follow_links=True
        )
        setup.call_config_script()

        system.pinch_system(
            manager=manager, force=True
        )

        setup.call_image_script()
        setup.create_init_link_from_linuxrc()

    def create_initrd(self, mbrid=None):
        if self.is_prepared():
            log.info('Creating initrd cpio archive')
            # we can't simply exclude boot when building the archive
            # because the file boot/mbrid must be preserved. Because of
            # that we create a copy of the boot directory and remove
            # everything in boot/ except for boot/mbrid. The original
            # boot directory should not be changed because we rely
            # on other data in boot/ e.g the kernel to be available
            # for the entire image building process
            self.temp_boot_root_directory = mkdtemp()
            data = DataSync(
                self.boot_root_directory + '/',
                self.temp_boot_root_directory
            )
            data.sync_data(
                options=['-z', '-a']
            )
            boot_directory = self.temp_boot_root_directory + '/boot'
            Path.wipe(boot_directory)
            if mbrid:
                log.info(
                    '--> Importing mbrid: %s', mbrid.get_id()
                )
                Path.create(boot_directory)
                image_identifier = boot_directory + '/mbrid'
                mbrid.write(image_identifier)

            cpio = ArchiveCpio(self.initrd_file_name)
            # the following is a list of directories which were needed
            # during the process of creating an image but not when the
            # image is actually booting with this initrd
            exclude_from_archive = [
                '/var/cache', '/image', '/usr/lib/grub2'
            ]
            cpio.create(
                source_dir=self.temp_boot_root_directory,
                exclude=exclude_from_archive
            )
            log.info(
                '--> xz compressing archive'
            )
            compress = Compress(self.initrd_file_name)
            compress.xz()
            self.initrd_filename = compress.compressed_filename
