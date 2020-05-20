[![Gentoo Badge](https://www.gentoo.org/assets/img/badges/gentoo-badge.png)](https://www.gentoo.org)

# Syuppod
> SYnc UPdate POrtage Daemon

Syuppod is a python3 daemon which automate syncing and pretending update
for gentoo portage manager. It intend to be run as a root service using /etc/init.d/ but for debugging puproses 
it can be run in a terminal. Any way, it as to be run as root.

It uses dbus to expose informations to user space tools and it have an already written client (trival).
With this client (syuppo-cli), you can retrieve informations about new update package available, syncing stats.
And many more (also more to come).

I'm using it with [conky](https://github.com/brndnmtthws/conky) to display some informations. But it have no 
dependencies against conky. So it's up to you to do whatever you want to do with these informations and from
whatever program (as long as it use dbus or syuppo-cli output).


## Dependencies

* [python](https://www.python.org/) >= 3.5 (tested: v3.6.x - v3.7.7, recommanded: v3.7.x)
* [pydbus](https://github.com/LEW21/pydbus)
* [numpy](https://numpy.org/)
* [pexpect](https://github.com/pexpect/pexpect)
* [inotify_simple](https://github.com/chrisjbillington/inotify_simple)


## Installation / Usage

1. Clone the repo (--recursive because it have shared libs):
```bash
git clone --recursive https://github.com/Jjeje007/syuppod.git
```
2. Copy the dbus configuration file to authorize dbus request:
```bash
cp syuppod-dbus.conf /usr/share/dbus-1/system.d/
```
3. Install dependencies using emerge or pip.

### If you just want to test it:

1. Run it (i recommand to activate debug):
```bash
./main -d
```

### To use as a daemon:

1. Copy init file:
```bash
cp init /etc/init.d/syuppod
```
2. Edit lines:\
    command=\ 
   To point to: /where/is/your/git/clone/repo/main.py\
   And:\
    command_args=\
   To suit your need, more information:
```bash
./main --help
```
3. Run the daemon:
```bash
/etc/init.d/syuppod start
```

### About logs and debug

Daemon have several logs all located in /var/log/syuppod/\
If you have troubles, check first /var/log/syuppod/stderr.log and /var/log/syuppod/debug.log (if debug is enable: -d)\
But the best way, is running by hand in a terminal (so not using /etc/init.d/).

Daemon and terminal mode write sync and pretend process logs to, respectively:\
/var/log/syuppod/sync.log\
/var/log/syuppod/pretend.log

All logs are autorotate.

### About shared libs

This project use shared libs from git submodule. If you want to automatically pull submodule
when you run 'git pull' in git's folder project then you should run:
```bash
git config --global submodule.recurse true
```
to enable it globally. Or use:
```bash
git pull --recurse-submodules
```
each time.

## Developpement Status

This is a work in progress so i haven't yet planned to make a release.\
The API is still in developpement and it's not yet stabilized.\
My priority is to stabilize daemon API.

## Meta

Venturi Jerôme – jerome.venturi@gmail.com

Distributed under the [GNU gpl v3 license](https://www.gnu.org/licenses/gpl-3.0.html).

## Bugs report

Please open an issue and don't forget to attach logs: stderr.log and debug.log. 

## Contributing

Pull requests and translations are welcome. For major changes, please open an issue first to discuss what you would like to change.

