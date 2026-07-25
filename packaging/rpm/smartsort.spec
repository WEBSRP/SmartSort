Name:           smartsort
Version:        1.0.0
Release:        1%{?dist}
Summary:        Intelligent Download Organizer for Linux

License:        GPLv3+
URL:            https://github.com/smartsort-org/SmartSort
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3 >= 3.6
Requires:       python3-pyqt6
Requires:       python3-watchdog
Requires:       python3-notify2
Requires:       libnotify
Requires:       glib2

%description
SmartSort is an offline Linux file automation and organization platform built in Python and PyQt6.
It monitors your Downloads folder in real-time and automatically sorts incoming files into category directories using a dynamic, priority-sorted rule engine.

%prep
%setup -q

%install
rm -rf $RPM_BUILD_ROOT
mkdir -p $RPM_BUILD_ROOT/usr/share/smartsort
mkdir -p $RPM_BUILD_ROOT/usr/bin
mkdir -p $RPM_BUILD_ROOT/usr/share/applications
mkdir -p $RPM_BUILD_ROOT/usr/share/icons/hicolor/scalable/apps
mkdir -p $RPM_BUILD_ROOT/usr/lib/systemd/user

cp -r src config main.py $RPM_BUILD_ROOT/usr/share/smartsort/
cp -r assets $RPM_BUILD_ROOT/usr/share/smartsort/

cat << 'EOF' > $RPM_BUILD_ROOT/usr/bin/smartsort
#!/bin/bash
export PYTHONPATH=/usr/share/smartsort
exec python3 /usr/share/smartsort/main.py "$@"
EOF
chmod 755 $RPM_BUILD_ROOT/usr/bin/smartsort

cp assets/icons/logo.png $RPM_BUILD_ROOT/usr/share/icons/hicolor/scalable/apps/smartsort.png

cat << 'EOF' > $RPM_BUILD_ROOT/usr/share/applications/smartsort.desktop
[Desktop Entry]
Name=SmartSort
Comment=Intelligent Download Organizer
Exec=/usr/bin/smartsort
Icon=smartsort
Terminal=false
Type=Application
Categories=Utility;
Keywords=Organizer;Files;Downloads;
EOF

cat << 'EOF' > $RPM_BUILD_ROOT/usr/lib/systemd/user/smartsort.service
[Unit]
Description=SmartSort File Organizer Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/smartsort --daemon
Restart=on-failure

[Install]
WantedBy=default.target
EOF

%post
gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true
systemctl --user daemon-reload || true

%preun
if [ $1 -eq 0 ] ; then
    systemctl --user stop smartsort.service || true
    systemctl --user disable smartsort.service || true
fi

%postun
gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true
systemctl --user daemon-reload || true

%files
/usr/share/smartsort/
/usr/bin/smartsort
/usr/share/applications/smartsort.desktop
/usr/share/icons/hicolor/scalable/apps/smartsort.png
/usr/lib/systemd/user/smartsort.service

%changelog
* Sat Jul 25 2026 Soumya Ranjan Parida <contact@smartsort-org.com> - 1.0.0-1
- Official v1.0.0 release with XDG compliance and packaging refactor.
