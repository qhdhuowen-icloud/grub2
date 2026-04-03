%define anolis_release 21
%global _lto_cflags %{nil}

%undefine _hardened_build
%undefine _package_note_file

%global tarversion 2.12
%undefine _missing_build_ids_terminate_build
%global _configure_gnuconfig_hack 0

%global gnulibversion 9f48fb992a3d7e96610c4ce8be969cff2d61a01b

Name:		grub2
Epoch:		1
Version:	2.12
Release:	%{anolis_release}%{?dist}
Summary:	Bootloader with support for Linux, Multiboot and more
License:	GPLv3+
URL:		http://www.gnu.org/software/grub/
Source0:	https://ftp.gnu.org/gnu/grub/grub-%{tarversion}.tar.xz
Source1:	grub.macros
Source2:	gnulib-%{gnulibversion}.tar.gz
Source3:	99-grub-mkconfig.install
Source4:	http://unifoundry.com/pub/unifont/unifont-13.0.06/font-builds/unifont-13.0.06.pcf.gz
Source5:	theme.tar.bz2
Source6:	gitignore
Source7:	bootstrap
Source8:	bootstrap.conf
Source9:	strtoull_test.c
Source10:	20-grub.install
Source11:	grub.patches
Source12:	sbat.csv.in

%include %{SOURCE1}

BuildRequires:	gcc efi-srpm-macros
BuildRequires:	flex bison binutils python3
BuildRequires:	ncurses-devel xz-devel bzip2-devel
BuildRequires:	freetype-devel
BuildRequires:	fuse-devel
BuildRequires:	rpm-devel rpm-libs
BuildRequires:	autoconf automake device-mapper-devel
BuildRequires:	freetype-devel gettext-devel git
BuildRequires:	texinfo
BuildRequires:	dejavu-sans-fonts
BuildRequires:	help2man
BuildRequires:	systemd
%ifarch %{efi_arch}
BuildRequires:	pesign >= 0.99-8
%endif

Obsoletes:	%{name} <= %{evr}
Obsoletes:	grub < 1:0.98

%if 0%{with_legacy_arch}
Requires:	%{name}-%{legacy_package_arch} = %{evr}
%else
Requires:	%{name}-%{package_arch} = %{evr}
%endif

%global desc \
The GRand Unified Bootloader (GRUB) is a highly configurable and \
customizable bootloader with modular architecture.  It supports a rich \
variety of kernel formats, file systems, computer architectures and \
hardware devices.\
%{nil}

# generate with do-rebase
%include %{SOURCE11}

%description
%{desc}

%package common
Summary:	grub2 common layout
BuildArch:	noarch
Conflicts:	grubby < 8.40
Requires(post): util-linux

%description common
This package provides some directories which are required by various grub2
subpackages.

%package doc
Summary:        Documentation files for %{name}
Requires:       %{name}-common = %{epoch}:%{version}-%{release}
BuildArch:      noarch

%description    doc
The %{name}-doc package contains documentation files for %{name}.

%package tools
Summary:	Support tools for GRUB.
Obsoletes:	%{name}-tools < %{evr}
Requires:	%{name}-common = %{epoch}:%{version}-%{release}
Requires:	gettext-runtime os-prober which file
Requires(pre):	dracut
Requires(post):	dracut

%description tools
%{desc}
This subpackage provides tools for support of all platforms.

%ifarch x86_64
%package tools-efi
Summary:	Support tools for GRUB.
Requires:	gettext-runtime os-prober which file
Requires:	%{name}-common = %{epoch}:%{version}-%{release}
Obsoletes:	%{name}-tools < %{evr}

%description tools-efi
%{desc}
This subpackage provides tools for support of EFI platforms.
%endif

%package tools-minimal
Summary:	Support tools for GRUB.
Requires:	gettext-runtime
Requires:	%{name}-common = %{epoch}:%{version}-%{release}
Obsoletes:	%{name}-tools < %{evr}

%description tools-minimal
%{desc}
This subpackage provides tools for support of all platforms.

%package tools-extra
Summary:	Support tools for GRUB.
Requires:	gettext-runtime os-prober which file
Requires:	%{name}-tools-minimal = %{epoch}:%{version}-%{release}
Requires:	%{name}-common = %{epoch}:%{version}-%{release}
Obsoletes:	%{name}-tools < %{evr}

%description tools-extra
%{desc}
This subpackage provides tools for support of all platforms.

%if 0%{with_efi_arch}
%{expand:%define_efi_variant %%{package_arch} -o}
%endif
%if 0%{with_alt_efi_arch}
%{expand:%define_efi_variant %%{alt_package_arch}}
%endif
%if 0%{with_legacy_arch}
%{expand:%define_legacy_variant %%{legacy_package_arch}}
%endif

%if 0%{with_emu_arch}
%package emu
Summary:	GRUB user-space emulation.
Requires:	%{name}-tools-minimal = %{epoch}:%{version}-%{release}

%description emu
%{desc}
This subpackage provides the GRUB user-space emulation support of all platforms.

%package emu-modules
Summary:	GRUB user-space emulation modules.
Requires:	%{name}-tools-minimal = %{epoch}:%{version}-%{release}

%description emu-modules
%{desc}
This subpackage provides the GRUB user-space emulation modules.
%endif

%prep
%do_common_setup
%if 0%{with_efi_arch}
mkdir grub-%{grubefiarch}-%{tarversion}
grep -A100000 '# stuff "make" creates' .gitignore > grub-%{grubefiarch}-%{tarversion}/.gitignore
cp %{SOURCE4} grub-%{grubefiarch}-%{tarversion}/unifont.pcf.gz
sed -e "s,@@VERSION@@,%{version},g" -e "s,@@VERSION_RELEASE@@,%{version}-%{release},g" \
    %{SOURCE12} > grub-%{grubefiarch}-%{tarversion}/sbat.csv
git add grub-%{grubefiarch}-%{tarversion}
%endif
%if 0%{with_alt_efi_arch}
mkdir grub-%{grubaltefiarch}-%{tarversion}
grep -A100000 '# stuff "make" creates' .gitignore > grub-%{grubaltefiarch}-%{tarversion}/.gitignore
cp %{SOURCE4} grub-%{grubaltefiarch}-%{tarversion}/unifont.pcf.gz
git add grub-%{grubaltefiarch}-%{tarversion}
%endif
%if 0%{with_legacy_arch}
mkdir grub-%{grublegacyarch}-%{tarversion}
grep -A100000 '# stuff "make" creates' .gitignore > grub-%{grublegacyarch}-%{tarversion}/.gitignore
cp %{SOURCE4} grub-%{grublegacyarch}-%{tarversion}/unifont.pcf.gz
git add grub-%{grublegacyarch}-%{tarversion}
%endif
%if 0%{with_emu_arch}
mkdir grub-emu-%{tarversion}
grep -A100000 '# stuff "make" creates' .gitignore > grub-emu-%{tarversion}/.gitignore
cp %{SOURCE4} grub-emu-%{tarversion}/unifont.pcf.gz
git add grub-emu-%{tarversion}
%endif
git commit -m "After making subdirs"

%build
%ifarch riscv64
export CFLAGS="%{optflags} -Wno-error=incompatible-pointer-types -Wno-error=implicit-function-declaration -Wno-error=int-conversion"
%endif

%if 0%{with_efi_arch}
%{expand:%do_primary_efi_build %%{grubefiarch} %%{grubefiname} %%{grubeficdname} %%{_target_platform} %%{efi_target_cflags} %%{efi_host_cflags}}
%endif
%if 0%{with_alt_efi_arch}
%{expand:%do_alt_efi_build %%{grubaltefiarch} %%{grubaltefiname} %%{grubalteficdname} %%{_alt_target_platform} %%{alt_efi_target_cflags} %%{alt_efi_host_cflags}}
%endif
%if 0%{with_legacy_arch}
%{expand:%do_legacy_build %%{grublegacyarch}}
%endif
%if 0%{with_emu_arch}
%{expand:%do_emu_build}
%endif
makeinfo --info --no-split -I docs -o docs/grub-dev.info \
	docs/grub-dev.texi
makeinfo --info --no-split -I docs -o docs/grub.info \
	docs/grub.texi
makeinfo --html --no-split -I docs -o docs/grub-dev.html \
	docs/grub-dev.texi
makeinfo --html --no-split -I docs -o docs/grub.html \
	docs/grub.texi

%install
set -e

%do_common_install
%if 0%{with_efi_arch}
%{expand:%do_efi_install %%{grubefiarch} %%{grubefiname} %%{grubeficdname}}
%endif
%if 0%{with_alt_efi_arch}
%{expand:%do_alt_efi_install %%{grubaltefiarch} %%{grubaltefiname} %%{grubalteficdname}}
%endif
%if 0%{with_legacy_arch}
%{expand:%do_legacy_install %%{grublegacyarch} %%{alt_grub_target_name} 0%{with_efi_arch}}
%endif
%if 0%{with_emu_arch}
%{expand:%do_emu_install %%{package_arch}}
%endif
rm -f $RPM_BUILD_ROOT%{_infodir}/dir
ln -s %{name}-set-password ${RPM_BUILD_ROOT}/%{_sbindir}/%{name}-setpassword
echo '.so man8/%{name}-set-password.8' > ${RPM_BUILD_ROOT}/%{_datadir}/man/man8/%{name}-setpassword.8
%ifnarch x86_64
rm -vf ${RPM_BUILD_ROOT}/%{_bindir}/%{name}-render-label
rm -vf ${RPM_BUILD_ROOT}/%{_sbindir}/%{name}-bios-setup
rm -vf ${RPM_BUILD_ROOT}/%{_sbindir}/%{name}-macbless
%endif
%{expand:%%do_install_protected_file %{name}-tools-minimal}

%find_lang grub

# Install kernel-install scripts
install -d -m 0755 %{buildroot}%{_prefix}/lib/kernel/install.d/
install -D -m 0755 -t %{buildroot}%{_prefix}/lib/kernel/install.d/ %{SOURCE10}
install -D -m 0755 -t %{buildroot}%{_prefix}/lib/kernel/install.d/ %{SOURCE3}
install -d -m 0755 %{buildroot}%{_sysconfdir}/kernel/install.d/
# Install systemd user service to set the boot_success flag
install -D -m 0755 -t %{buildroot}%{_userunitdir} \
	docs/grub-boot-success.{timer,service}
install -d -m 0755 %{buildroot}%{_userunitdir}/timers.target.wants
ln -s ../grub-boot-success.timer \
	%{buildroot}%{_userunitdir}/timers.target.wants
# Install systemd system-update unit to set boot_indeterminate for offline-upd
install -D -m 0755 -t %{buildroot}%{_unitdir} docs/grub-boot-indeterminate.service
install -d -m 0755 %{buildroot}%{_unitdir}/system-update.target.wants
install -d -m 0755 %{buildroot}%{_unitdir}/reboot.target.wants
ln -s ../grub-boot-indeterminate.service \
	%{buildroot}%{_unitdir}/system-update.target.wants
ln -s ../grub2-systemd-integration.service \
	%{buildroot}%{_unitdir}/reboot.target.wants

%global finddebugroot "%{_builddir}/%{?buildsubdir}/debug"

%global dip RPM_BUILD_ROOT=%{finddebugroot} %{__debug_install_post}
%define __debug_install_post (						\
	mkdir -p %{finddebugroot}/usr					\
	mv ${RPM_BUILD_ROOT}/usr/bin %{finddebugroot}/usr/bin		\
	mv ${RPM_BUILD_ROOT}/usr/sbin %{finddebugroot}/usr/sbin		\
	%{dip}								\
	install -m 0755 -d %{buildroot}/usr/lib/ %{buildroot}/usr/src/	\
	cp -al %{finddebugroot}/usr/lib/debug/				\\\
		%{buildroot}/usr/lib/debug/				\
	cp -al %{finddebugroot}/usr/src/debug/				\\\
		%{buildroot}/usr/src/debug/ )				\
	mv %{finddebugroot}/usr/bin %{buildroot}/usr/bin		\
	mv %{finddebugroot}/usr/sbin %{buildroot}/usr/sbin		\
	%{nil}

%undefine buildsubdir

%pre tools
if [ -f /boot/grub2/user.cfg ]; then
    if grep -q '^GRUB_PASSWORD=' /boot/grub2/user.cfg ; then
	sed -i 's/^GRUB_PASSWORD=/GRUB2_PASSWORD=/' /boot/grub2/user.cfg
    fi
elif [ -f %{efi_esp_dir}/user.cfg ]; then
    if grep -q '^GRUB_PASSWORD=' %{efi_esp_dir}/user.cfg ; then
	sed -i 's/^GRUB_PASSWORD=/GRUB2_PASSWORD=/' \
		%{efi_esp_dir}/user.cfg
    fi
elif [ -f /etc/grub.d/01_users ] && \
	grep -q '^password_pbkdf2 root' /etc/grub.d/01_users ; then
    if [ -f %{efi_esp_dir}/grub.cfg ]; then
	grep '^password_pbkdf2 root' /etc/grub.d/01_users | \
		sed 's/^password_pbkdf2 root \(.*\)$/GRUB2_PASSWORD=\1/' \
		> %{efi_esp_dir}/user.cfg
    fi
    if [ -f /boot/grub2/grub.cfg ]; then
	install -m 0600 /dev/null /boot/grub2/user.cfg
	chmod 0600 /boot/grub2/user.cfg
	grep '^password_pbkdf2 root' /etc/grub.d/01_users | \
		sed 's/^password_pbkdf2 root \(.*\)$/GRUB2_PASSWORD=\1/' \
	    > /boot/grub2/user.cfg
    fi
fi

%posttrans common
set -eu

EFI_HOME=%{efi_esp_dir}
GRUB_HOME=/boot/grub2
ESP_PATH=/boot/efi

if ! mountpoint -q ${ESP_PATH}; then
    exit 0 # no ESP mounted, nothing to do
fi

if test ! -f ${EFI_HOME}/grub.cfg; then
    # there's no config in ESP, create one
    grub2-mkconfig -o ${EFI_HOME}/grub.cfg
fi

if grep -q "configfile" ${EFI_HOME}/grub.cfg; then
    exit 0 # already unified, nothing to do
fi

# create a stub grub2 config in EFI
BOOT_UUID=$(grub2-probe --target=fs_uuid ${GRUB_HOME})
GRUB_DIR=$(grub2-mkrelpath ${GRUB_HOME})

cat << EOF > ${EFI_HOME}/grub.cfg.stb
search --no-floppy --fs-uuid --set=dev ${BOOT_UUID}
set prefix=(\$dev)${GRUB_DIR}
export \$prefix
configfile \$prefix/grub.cfg
EOF

if test -f ${EFI_HOME}/grubenv; then
    cp -a ${EFI_HOME}/grubenv ${EFI_HOME}/grubenv.rpmsave
    mv --force ${EFI_HOME}/grubenv ${GRUB_HOME}/grubenv
fi

cp -a ${EFI_HOME}/grub.cfg ${EFI_HOME}/grub.cfg.rpmsave
cp -a ${EFI_HOME}/grub.cfg ${GRUB_HOME}/
mv ${EFI_HOME}/grub.cfg.stb ${EFI_HOME}/grub.cfg

%files common -f grub.lang
%dir %{_libdir}/grub/
%attr(0700,root,root) %dir %{_sysconfdir}/grub.d
%{_prefix}/lib/kernel/install.d/20-grub.install
%{_prefix}/lib/kernel/install.d/99-grub-mkconfig.install
%dir %{_datarootdir}/grub
%exclude %{_datarootdir}/grub/*
%dir /boot/%{name}/themes/
%dir /boot/%{name}/themes/system
%attr(0700,root,root) %dir /boot/grub2
%exclude /boot/grub2/*
%dir %attr(0700,root,root) %{efi_esp_dir}
%exclude %{efi_esp_dir}/*
%ghost %config(noreplace) %verify(not size mode md5 mtime) /boot/grub2/grubenv
%license COPYING

%files doc
%doc THANKS NEWS INSTALL README TODO docs/grub.html docs/grub-dev.html docs/font_char_metrics.png

%files tools-minimal
%{_sbindir}/%{name}-get-kernel-settings
%{_sbindir}/%{name}-probe
%{_sbindir}/%{name}-set-default
%{_sbindir}/%{name}-set*password
%{_bindir}/%{name}-editenv
%{_bindir}/%{name}-mkpasswd-pbkdf2
%{_bindir}/%{name}-mount
%attr(4755, root, root) %{_sbindir}/%{name}-set-bootflag
%attr(0644,root,root) %config(noreplace) /etc/dnf/protected.d/%{name}-tools-minimal.conf

%{_datadir}/man/man3/%{name}-get-kernel-settings*
%{_datadir}/man/man8/%{name}-set-default*
%{_datadir}/man/man8/%{name}-set*password*
%{_datadir}/man/man1/%{name}-editenv*
%{_datadir}/man/man1/%{name}-mkpasswd-*

%ifarch x86_64
%files tools-efi
%{_bindir}/%{name}-glue-efi
%{_bindir}/%{name}-render-label
%{_sbindir}/%{name}-macbless
%{_datadir}/man/man1/%{name}-glue-efi*
%{_datadir}/man/man1/%{name}-render-label*
%{_datadir}/man/man8/%{name}-macbless*
%endif

%files tools
%{_sbindir}/%{name}-mkconfig
%{_sbindir}/%{name}-switch-to-blscfg
%{_sbindir}/%{name}-rpm-sort
%{_sbindir}/%{name}-reboot
%{_bindir}/%{name}-file
%{_bindir}/%{name}-menulst2cfg
%{_bindir}/%{name}-mkimage
%{_bindir}/%{name}-mkrelpath
%{_bindir}/%{name}-script-check
%{_sbindir}/%{name}-install
%{_unitdir}/grub-boot-indeterminate.service
%{_unitdir}/system-update.target.wants
%{_unitdir}/%{name}-systemd-integration.service
%{_unitdir}/reboot.target.wants
%{_unitdir}/systemd-logind.service.d
%{_userunitdir}/grub-boot-success.timer
%{_userunitdir}/grub-boot-success.service
%{_userunitdir}/timers.target.wants
%{_sysconfdir}/grub.d/README
%{_libexecdir}/%{name}

%attr(0644,root,root) %ghost %config(noreplace) %{_sysconfdir}/default/grub
%config %{_sysconfdir}/grub.d/??_*
%{_datarootdir}/grub/*
%exclude %{_datarootdir}/grub/themes
%exclude %{_datarootdir}/grub/*.h
%{_datarootdir}/bash-completion/completions/grub
%{_infodir}/%{name}*
%{_datadir}/man/man?/*

# exclude man pages from tools-extra
%exclude %{_datadir}/man/man8/%{name}-sparc64-setup*
%exclude %{_datadir}/man/man1/%{name}-fstest*
%exclude %{_datadir}/man/man1/%{name}-glue-efi*
%exclude %{_datadir}/man/man1/%{name}-kbdcomp*
%exclude %{_datadir}/man/man1/%{name}-mkfont*
%exclude %{_datadir}/man/man1/%{name}-mklayout*
%exclude %{_datadir}/man/man1/%{name}-mknetdir*
%exclude %{_datadir}/man/man1/%{name}-mkrescue*
%exclude %{_datadir}/man/man1/%{name}-mkstandalone*
%exclude %{_datadir}/man/man1/%{name}-syslinux2cfg*

# exclude man pages from tools-minimal
%exclude %{_datadir}/man/man3/%{name}-get-kernel-settings*
%exclude %{_datadir}/man/man8/%{name}-set-default*
%exclude %{_datadir}/man/man8/%{name}-set*password*
%exclude %{_datadir}/man/man1/%{name}-editenv*
%exclude %{_datadir}/man/man1/%{name}-mkpasswd-*
%exclude %{_datadir}/man/man8/%{name}-macbless*
%exclude %{_datadir}/man/man1/%{name}-render-label*

%if %{with_legacy_arch}
%{_sbindir}/%{name}-install
%ifarch x86_64
%{_sbindir}/%{name}-bios-setup
%else
%exclude %{_sbindir}/%{name}-bios-setup
%exclude %{_datadir}/man/man8/%{name}-bios-setup*
%endif
%exclude %{_sbindir}/%{name}-sparc64-setup
%exclude %{_datadir}/man/man8/%{name}-sparc64-setup*
%exclude %{_sbindir}/%{name}-ofpathname
%exclude %{_datadir}/man/man8/%{name}-ofpathname*
%endif

%files tools-extra
%{_bindir}/%{name}-fstest
%{_bindir}/%{name}-kbdcomp
%{_bindir}/%{name}-mkfont
%{_bindir}/%{name}-mklayout
%{_bindir}/%{name}-mknetdir
%{_bindir}/%{name}-mkrescue
%{_bindir}/%{name}-mkstandalone
%{_bindir}/%{name}-syslinux2cfg
%{_sysconfdir}/sysconfig/grub
%{_datadir}/man/man1/%{name}-mkrescue*
%{_datadir}/man/man1/%{name}-fstest*
%{_datadir}/man/man1/%{name}-kbdcomp*
%{_datadir}/man/man1/%{name}-mkfont*
%{_datadir}/man/man1/%{name}-mklayout*
%{_datadir}/man/man1/%{name}-mknetdir*
%{_datadir}/man/man1/%{name}-mkstandalone*
%{_datadir}/man/man1/%{name}-syslinux2cfg*
%exclude %{_bindir}/%{name}-glue-efi
%exclude %{_sbindir}/%{name}-sparc64-setup
%exclude %{_sbindir}/%{name}-ofpathname
%exclude %{_datadir}/man/man1/%{name}-glue-efi*
%exclude %{_datadir}/man/man8/%{name}-ofpathname*
%exclude %{_datadir}/man/man8/%{name}-sparc64-setup*
%exclude %{_datarootdir}/grub/themes/starfield

%if 0%{with_efi_arch}
%{expand:%define_efi_variant_files %%{package_arch} %%{grubefiname} %%{grubeficdname} %%{grubefiarch} %%{target_cpu_name} %%{grub_target_name}}
%endif
%if 0%{with_alt_efi_arch}
%{expand:%define_efi_variant_files %%{alt_package_arch} %%{grubaltefiname} %%{grubalteficdname} %%{grubaltefiarch} %%{alt_target_cpu_name} %%{alt_grub_target_name}}
%endif
%if 0%{with_legacy_arch}
%{expand:%define_legacy_variant_files %%{legacy_package_arch} %%{grublegacyarch}}
%endif

%if 0%{with_emu_arch}
%files emu
%{_bindir}/%{name}-emu*
%{_datadir}/man/man1/%{name}-emu*

%files emu-modules
%{_libdir}/grub/%{emuarch}-emu/*
%exclude %{_libdir}/grub/%{emuarch}-emu/*.module
%endif

%changelog
* Mon Nov 24 2025 tomcruiseqi <tomcruiseqi@inspur.com> - 1:2.12-21
- Fix CVE-2025-54771

* Thu Nov 20 2025 tomcruiseqi <tomcruiseqi@inspur.com> - 1:2.12-20
- Fix CVE-2025-61661,CVE-2025-61663,CVE-2025-61662,CVE-2025-54770

* Thu Nov 20 2025 mgb01105731 <mgb01105731@alibaba-inc.com> - 2.12-19
- Fix install iso err by uefi

* Mon Oct 27 2025 Yihao Yan <yan.yihao@zte.com.cn> - 2.12-18
- fix patches index

* Wed Oct 23 2025 xinhaitao <xinhaitao@ieisystem.com> -2.12-17
- Add support for riscv64

* Wed Sep 10 2025 Jessica Liu <liu.xuemei1@zte.com.cn> -2.12-16
- Use time register in grub_efi_get_time_ms()

* Tue Aug 26 2025 zjl002254423 <zjl02254423@alibaba-inc.com> -2.12-15
- Fix CVE-2024-56738,CVE-2024-56737,CVE-2024-45774,CVE-2024-45775,CVE-2024-45776,CVE-2024-45777,CVE-2024-45778,CVE-2024-45779,CVE-2024-45780,CVE-2024-45781,CVE-2024-45782,CVE-2024-45783,CVE-2025-0622,CVE-2025-0624,CVE-2025-0677,CVE-2025-0678,CVE-2025-0684,CVE-2025-0685,CVE-2025-0686,CVE-2025-0689,CVE-2025-0690,CVE-2025-1118,CVE-2025-1125

* Tue Jul 29 2025 zjl002254423 <zjl02254423@alibaba-inc.com> -2.12-14
- Fix CVE-2025-0624

* Thu Jun 5 2025 Xue Liu<liuxue@loongson.cn> - 2.12-13
- Disable vector instructions for loongarch

* Fri May 30 2025 yechao-w <wang.yechao255@zte.com.cn> - 2.12-12
- Use proper memory type for kernel allocation

* Tue Jan 14 2025 Xue Liu<liuxue@loongson.cn> - 2.12-11
- Fix the introduced old code
- Clear buffer for screen information 

* Thu Jan 02 2025 hanliyang <hanliyang@hygon.cn> - 2.12-10
- Support use confidential computing provisioned secrets for disk decryption

* Wed Jul 24 2024 Jun He <jun.he@arm.com> - 2.12-9
- Updated cherry-picked NX patche series to fix setting memory attr failure

* Thu May 30 2024 Chang Gao <gc-taifu@linux.alibaba.com> - 2.12-8
- Avoid loongarch specifed patches patched on other arches

* Fri May 24 2024 Juxin Gao <gaojuxin@loongson.cn> - 2.12-7
- Add GRUB_CPU_LOONGARCH64 for loongson platform

* Thu May 23 2024 Xue Liu <liuxue@loongson.cn> - 2.12-6
- Add back-compatibility for linux kernel

* Wed May 15 2024 Kaiqiang Wang <wangkaiqiang@inspur.com> - 2.12-5
- fix CVE-2024-1048

* Mon Apr 22 2024 Chang Gao <gc-taifu@linux.alibaba.com> - 2.12-4
- Revert efi patch on loongarch 

* Mon Apr 15 2024 chench <chench@hygon.cn> -2.12-3
- add hygon tpcm support
- embed hygon tpcm module into kernel.img by default

* Thu Apr 11 2024 Bo Ren <rb01097748@alibaba-inc.com> - 2.12-2
* update patch number

* Thu Apr 11 2024 Liwei Ge <liwei.glw@alibaba-inc.com> - 2.12-1
* update to grub 2.12

* Wed Dec 06 2023 happy_orange <songnannan@linux.alibaba.com> -2.06-14
- rebuild for loongarch

* Wed Sep 06 2023 Yingkun Meng <mengyingkun@loongson.cn> -2.06-13
- loongarch: disable relaxation relocations

* Wed Aug 09 2023 Yingkun Meng <mengyingkun@loongson.cn> -2.06-12
- add support for loongarch

* Wed Aug 09 2023 Yingkun Meng <mengyingkun@loongson.cn> -2.06-11
- fix file installed but unpackaged error

* Wed Jun 28 2023 happy_orange <songnannan@linux.alibaba.com> -2.06-10
- add crashkernel in install

* Thu Mar 02 2023 Chunmei Xu <xuchunmei@linux.alibaba.com> - 2.06-9
- fix remove dtb-xxx dir failed

* Mon Dec 19 2022 Funda Wang <fundawang@yeah.net> - 2.06-8
- Deal with gettext-runtime migration

* Mon Nov 21 2022 yuanhui <yuanhui@linux.alibaba.com> - 2.06-7
- fix the bugs about video readers in grub2
- fix several fuzz issues with invalid dir
- net/netbuff: Block overly large netbuff allocs
- net/ip: do IP fragment maths safely
- net/dns: fix double-free addresses on corrupt DNS response
- net/tftp: fix some bugs about tftp
- net/http: fix OOB write for split http headers
- fs/f2fs: fix some bugs og f2fs
- fix some bugs of grub_min() and grub_max()
- add the DOS header struct and fix some bad naming
- set page permissions for loaded modules
- grub_fs_probe(): dprint errors from filesystems
- BLS: create /etc/kernel/cmdline during mkconfig
- font: Fix some errors about fonts
- fbutil: Fix integer overflow

* Mon Oct 17 2022 Chunmei Xu <xuchunmei@linux.alibaba.com> - 2.06-6
- fix bls config update failed because of grub-rpm-sort

* Fri Sep 30 2022 mgb01105731 <mgb01105731@alibaba-inc.com> - 2.06-5
- add doc package

* Wed Mar 23 2022 Chunmei Xu <xuchunmei@linux.alibaba.com> - 2.06-4
- optimise Conflicts version of grubby

* Wed Mar 23 2022 forrest_ly <flin@linux.alibaba.com> - 2.06-3
- Build pc-modules on x86-64

* Tue Mar 22 2022 Chunmei Xu <xuchunmei@linux.alibaba.com> - 2.06-2
- change to use fuse3

* Fri Mar 11 2022 forrest_ly <flin@linux.alibaba.com> - 2.06-1 
- Init for Anolis OS 23
