[![Gentoo Badge](https://www.gentoo.org/assets/img/badges/gentoo-badge.png)](https://www.gentoo.org)

# Syuppo
> SYnc UPdate POrtage

Syuppo is a python3 daemon (syuppod) / client (syuppoc) which automate sync and calculate how many packages to update
for gentoo portage manager. Syuppod is intend to be run as service using /etc/init.d/ and it run as an unprivileged system user (syuppod)
and use sudo to gain root access (only for sync).

Syuppod uses dbus to expose informations to user space tools and syuppoc can retrieve informations 
about new update package available, syncing stats.
And many more (also more to come).

I use syuppoc to feed a desktop widget, but it has no dependency on any particular one. It is up
to you to do whatever you want to do with these informations and from whatever program
(as long as it use dbus or syuppoc output).


## Dependencies

* [python](https://www.python.org/) >= 3.8
* [dbus-fast](https://github.com/bluetooth-devices/dbus-fast)
* [PyGObject](https://gitlab.gnome.org/GNOME/pygobject)
* [babel](https://github.com/python-babel/babel)
* [numpy](https://numpy.org/)
* [pexpect](https://github.com/pexpect/pexpect)
* [inotify_simple](https://github.com/chrisjbillington/inotify_simple)

`portage` is needed as well, but it comes with the distribution rather than from PyPI,
so it is not listed as a package dependency.

For **inotify_simple** an ebuild can be found in [Jjeje007-overlay](https://github.com/Jjeje007/Jjeje007-overlay).

## Installation

Use syuppod ebuild found in [Jjeje007-overlay](https://github.com/Jjeje007/Jjeje007-overlay). It will install all dependencies.

## Usage

Run the daemon:

```
/etc/init.d/syuppod start
```

## About logs and debug

Syuppod have several logs all located in `/var/log/syuppod/`\

Debug output is written only when the daemon is started with `-d`.

Syuppod write sync and pretend process logs to, respectively:\
`/var/log/syuppod/sync.log`\
`/var/log/syuppod/pretend.log`

All logs are autorotate.

## Developpement Status

This is a work in progress so i haven't yet planned to make a release.\
Syuppod API is stabilized.\

## Meta

Venturi Jerôme – jerome.venturi@gmail.com

Distributed under the [GNU gpl v3 license](https://www.gnu.org/licenses/gpl-3.0.html).

## Bugs report

Please open an issue and don't forget to attach logs: messages (syslog), stderr.log and debug.log. 

## Contributing

Pull requests and translations are welcome. For major changes, please open an issue first to discuss what you would like to change.
