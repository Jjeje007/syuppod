[![Gentoo Badge](https://www.gentoo.org/assets/img/badges/gentoo-badge.png)](https://www.gentoo.org)

# Syuppo
> SYnc UPdate POrtage

Syuppo is a python3 daemon (syuppod) / client (syuppoc) which automate sync and calculate how many packages to update
for gentoo portage manager. Syuppod is intend to be run as service using /etc/init.d/. Since git commit id 5b75f3f5b1eac2954be4380bc03d8871f5c2e2fb, it run as an unprivileged system user (syuppod)
and use sudo to gain root access (only for sync).

Syuppod uses dbus to expose informations to user space tools and syuppoc can retrieve informations 
about new update package available, syncing stats.
And many more (also more to come).

You can use syuppoc, for exemple, with [conky](https://github.com/brndnmtthws/conky) to display some informations. But it's up 
to you to do whatever you want to do with these informations and from whatever program 
(as long as it use dbus or syuppoc output).


## Dependencies

* [python](https://www.python.org/) >= 3.5 (tested: v3.6.x - v3.7.7, recommanded: v3.7.x)
* [pydbus](https://github.com/LEW21/pydbus)
* [numpy](https://numpy.org/)
* [pexpect](https://github.com/pexpect/pexpect)
* [inotify_simple](https://github.com/chrisjbillington/inotify_simple)

For **pydbus** and **inotify_simple** ebuilds can be found in [Jjeje007-overlay](https://github.com/Jjeje007/Jjeje007-overlay).

## Installation

# 'TODO'

1. Clone the repo:
```
git clone https://github.com/Jjeje007/syuppod.git
```
2. Copy the dbus configuration file to authorize dbus requests:
```
cp syuppod-dbus.conf /usr/share/dbus-1/system.d/
```
3. Install dependencies using emerge.

4. Starting with git commit id 5b75f3f5b1eac2954be4380bc03d8871f5c2e2fb, syuppod now run as an dedicated
system user which belong to portage group. So don't use pip to install packages otherwise it will complain
about missing module and program won't start. 
You have to use ebuilds: the only ebuilds not in the tree are **pydbus** and **inotify_simple** which can be founded, for exemple
from [Jjeje007-overlay](https://github.com/Jjeje007/Jjeje007-overlay).

Also, the only command that needs root rights is `emerge --sync` and now the program use `sudo` to run it.
You have to configure it using `/etc/sudoers` and grant access to user: **syuppod** using **NOPASSWD** and running **emerge --sync**,
here is an configuration exemple:
> Cmnd_Alias      DAEMON =        /usr/bin/emerge --sync\
> syuppod localhost = NOPASSWD: DAEMON

For more informations on how to use sudo see [gentoo wiki](https://wiki.gentoo.org/wiki/Sudo).

## Usage

For the moment, init file is responsible to take care of creating/checking folders and rights.
After developpement phase, theses processes could be dedicated to ebuild.

1. Copy init file:
```
cp init /etc/init.d/syuppod
```
2. Edit lines:\
    `command=` to point to: `/where/is/your/git/clone/repo/main.py`\
   And:\
    `command_args=` to suit your need, more information: `./main --help`
    Enable debug for the first run is recommanded: `-d`
3. Run the daemon:
```
/etc/init.d/syuppod start
```

## About logs and debug

Syuppod have several logs all located in `/var/log/syuppod/`\

Starting with git commit id: e1079ebd0f4a4b8b65fdf9ebfd448e02c7fc9e66, new logging process have been added
to catch almost all error. Unfortunately, it introduce a more complex log flow. 
The earliest errors are redirect to syslog first. So if you encounter any issues you should first check `/var/log/messages`.
Then: `/var/log/syuppod/stderr.log` and `/var/log/syuppod/debug.log` (if debug is enable: `-d`).

Syuppod write sync and pretend process logs to, respectively:\
`/var/log/syuppod/sync.log`\
`/var/log/syuppod/pretend.log`

All logs are autorotate.

## Developpement Status

This is a work in progress so i haven't yet planned to make a release.\
Syuppod API is still in developpement and it's not yet stabilized.\

## Meta

Venturi Jerôme – jerome.venturi@gmail.com

Distributed under the [GNU gpl v3 license](https://www.gnu.org/licenses/gpl-3.0.html).

## Bugs report

Please open an issue and don't forget to attach logs: messages (syslog), stderr.log and debug.log. 

## Contributing

Pull requests and translations are welcome. For major changes, please open an issue first to discuss what you would like to change.

