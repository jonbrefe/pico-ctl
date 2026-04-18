Name:           pico-ctl
Version:        0.2.0
Release:        1%{?dist}
Summary:        All-in-one CLI for managing a Raspberry Pi Pico over USB serial
License:        MIT
URL:            https://github.com/jonbrefe/pico-ctl
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3 >= 3.8
Requires:       python3-pyserial >= 3.5

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools

%description
Upload files, backup, monitor, reset, and inspect a Raspberry Pi Pico
running MicroPython — all from a single pico_ctl command.

%prep
%autosetup

%build
%py3_build

%install
%py3_install
mkdir -p %{buildroot}%{_mandir}/man1
install -m 644 pico_ctl.1 %{buildroot}%{_mandir}/man1/pico_ctl.1

%files
%license LICENSE
%doc README.md
%{_bindir}/pico_ctl
%{_mandir}/man1/pico_ctl.1*
%{python3_sitelib}/pico_ctl.py
%{python3_sitelib}/pico_serial.py
%{python3_sitelib}/__pycache__/pico_ctl*
%{python3_sitelib}/__pycache__/pico_serial*
%{python3_sitelib}/pico_ctl-*.egg-info/
